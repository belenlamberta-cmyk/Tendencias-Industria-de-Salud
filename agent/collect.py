#!/usr/bin/env python3
"""Etapa 1 - Recolector. Solo biblioteca estandar (no hay que instalar nada).
Uso:  python collect.py            -> corre todas las fuentes
      python collect.py --days 30  -> ventana de dias
      python collect.py --selftest -> prueba los parsers con ejemplos locales
Guarda en ../data/raw/raw_items.jsonl (un item por linea, sin duplicados) y
../data/raw/run_log.jsonl (que fuente respondio y cuantos items trajo)."""
import argparse, hashlib, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
UA = {"User-Agent": "radar-salud-tp/1.0 (trabajo practico universitario)"}
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def item(source, stype, url, title, text, published, query="", region="global"):
    return {"id": hashlib.sha1(url.encode()).hexdigest()[:16], "source": source, "source_type": stype,
            "url": url, "title": (title or "").strip(), "text": re.sub(r"\s+", " ", text or "").strip()[:4000],
            "published": published or "", "retrieved_at": NOW(), "query": query, "region": region}

def strip_tags(s): return re.sub(r"<[^>]+>", " ", s or "")

# ---------- parsers (reciben texto de la respuesta, devuelven items) ----------
def parse_pubmed(esearch_json, efetch_xml, q, region="global"):
    out = []
    root = ET.fromstring(efetch_xml)
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext(".//PMID")
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        abst = " ".join("".join(a.itertext()) for a in art.findall(".//AbstractText"))
        y = art.findtext(".//PubDate/Year") or art.findtext(".//PubDate/MedlineDate") or ""
        if pmid and title:
            out.append(item("pubmed", "paper", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", title, abst, y, q, region))
    return out

def parse_clinicaltrials(js, q):
    out = []
    for s in json.loads(js).get("studies", []):
        p = s.get("protocolSection", {})
        nct = p.get("identificationModule", {}).get("nctId")
        if not nct: continue
        t = p.get("identificationModule", {}).get("briefTitle", "")
        summ = p.get("descriptionModule", {}).get("briefSummary", "")
        phase = ",".join(p.get("designModule", {}).get("phases", []) or [])
        status = p.get("statusModule", {}).get("overallStatus", "")
        d = p.get("statusModule", {}).get("lastUpdatePostDateStruct", {}).get("date", "")
        out.append(item("clinicaltrials", "ensayo", f"https://clinicaltrials.gov/study/{nct}", t,
                        f"[Fase: {phase or 's/d'}; Estado: {status}] {summ}", d, q))
    return out

def abstract_from_inverted(inv):
    if not inv: return ""
    pos = {}
    for w, idxs in inv.items():
        for i in idxs: pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))

def parse_openalex(js, q, region="global"):
    out = []
    for w in json.loads(js).get("results", []):
        url = w.get("doi") or w.get("id")
        if not url or not w.get("title"): continue
        out.append(item("openalex", "paper", url, w["title"], abstract_from_inverted(w.get("abstract_inverted_index")),
                        w.get("publication_date", ""), q, region))
    return out

def parse_medrxiv(js, topics):
    out = []
    low = [t.lower() for t in topics]
    kw = {w for t in low for w in t.split() if len(w) > 4}
    for r in json.loads(js).get("collection", []):
        blob = (r.get("title", "") + " " + r.get("abstract", "")).lower()
        if any(k in blob for k in kw):
            out.append(item("medrxiv", "preprint", "https://doi.org/" + r["doi"], r.get("title"), r.get("abstract"), r.get("date"), "filtro por palabras"))
    return out

def parse_arxiv(xml, q):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(xml).findall("a:entry", ns):
        url = e.findtext("a:id", namespaces=ns)
        out.append(item("arxiv", "preprint", url, e.findtext("a:title", namespaces=ns), e.findtext("a:summary", namespaces=ns), (e.findtext("a:published", namespaces=ns) or "")[:10], q))
    return out

def parse_rss(xml, src):
    out = []
    root = ET.fromstring(xml)
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        link = it.findtext("link") or ""
        if not link:
            l = it.find("{http://www.w3.org/2005/Atom}link")
            link = l.get("href") if l is not None else ""
        title = it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or ""
        desc = strip_tags(it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or "")
        pub = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}updated") or ""
        if link: out.append(item(src["id"], src["type"], link.strip(), title, desc, pub, "rss", src.get("region", "global")))
    return out

# ---------- recolectores ----------
def run_pubmed(topics, days):
    out = []
    for q0 in topics + ["AR::" + x for x in topics]:
        ar = q0.startswith("AR::"); q = q0[4:] if ar else q0
        term = f"({q}) AND Argentina[Affiliation]" if ar else q
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        ids = json.loads(fetch(base + "esearch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "term": term, "retmax": 8 if ar else 15, "sort": "date", "datetype": "pdat", "reldate": days, "retmode": "json"})))["esearchresult"]["idlist"]
        time.sleep(0.4)
        if ids:
            xml = fetch(base + "efetch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))
            out += parse_pubmed(None, xml, q, "Argentina" if ar else "global")
            time.sleep(0.4)
    return out

def run_clinicaltrials(topics, days):
    out = []
    for q in topics:
        u = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({"query.term": q, "pageSize": 15, "sort": "LastUpdatePostDate:desc"})
        out += parse_clinicaltrials(fetch(u), q)
    return out

def run_openalex(topics, days):
    out = []
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for q in topics:
        for ar in (False, True):
            flt = f"from_publication_date:{since}" + (",institutions.country_code:AR" if ar else "")
            u = "https://api.openalex.org/works?" + urllib.parse.urlencode({"search": q, "filter": flt, "per-page": 8 if ar else 15, "sort": "cited_by_count:desc"})
            out += parse_openalex(fetch(u), q, "Argentina" if ar else "global")
    return out

def run_medrxiv(topics, days):
    d2 = datetime.now(); d1 = d2 - timedelta(days=min(days, 14))
    js = fetch(f"https://api.medrxiv.org/details/medrxiv/{d1:%Y-%m-%d}/{d2:%Y-%m-%d}/0")
    return parse_medrxiv(js, topics)

def run_arxiv(topics, days):
    out = []
    for q in topics:
        u = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": "all:" + q, "max_results": 10, "sortBy": "submittedDate", "sortOrder": "descending"})
        out += parse_arxiv(fetch(u), q); time.sleep(3)
    return out

API = {"pubmed": run_pubmed, "clinicaltrials": run_clinicaltrials, "openalex": run_openalex, "medrxiv": run_medrxiv, "arxiv": run_arxiv}

def save(items):
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / "raw_items.jsonl"
    have = set()
    if f.exists():
        have = {json.loads(l)["id"] for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}
    new = [i for i in items if i["id"] not in have]
    with f.open("a", encoding="utf-8") as fh:
        for i in new: fh.write(json.dumps(i, ensure_ascii=False) + "\n")
    return len(new)

def main(days):
    cfg = json.loads((Path(__file__).parent / "sources.json").read_text(encoding="utf-8"))
    log, allitems = [], []
    jobs = [(s["id"], lambda s=s: API[s["id"]](cfg["topics"], days)) for s in cfg["api_sources"]]
    for s in cfg["rss_sources"]:
        if s.get("enabled") is False: log.append({"source": s["id"], "ok": False, "n": 0, "note": "deshabilitada (URL pendiente)"}); continue
        jobs.append((s["id"], lambda s=s: parse_rss(fetch(s["url"]), s)))
    for sid, job in jobs:
        try:
            its = job(); allitems += its
            log.append({"source": sid, "ok": True, "n": len(its)})
        except Exception as e:
            log.append({"source": sid, "ok": False, "n": 0, "note": f"{type(e).__name__}: {e}"})
    new = save(allitems)
    with (RAW / "run_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"run_at": NOW(), "days": days, "nuevos": new, "fuentes": log}, ensure_ascii=False) + "\n")
    print(f"{'FUENTE':16}{'ESTADO':8}ITEMS")
    for l in log: print(f"{l['source']:16}{'OK' if l['ok'] else 'FALLA':8}{l['n']}  {l.get('note','')}")
    print(f"\nItems nuevos guardados: {new}  ->  {RAW/'raw_items.jsonl'}")

def selftest():
    pm = '<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>T pubmed</ArticleTitle><Abstract><AbstractText>abs uno</AbstractText></Abstract><Journal><JournalIssue><PubDate><Year>2026</Year></PubDate></JournalIssue></Journal></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
    ct = json.dumps({"studies": [{"protocolSection": {"identificationModule": {"nctId": "NCT01", "briefTitle": "Ensayo X"}, "descriptionModule": {"briefSummary": "resumen"}, "designModule": {"phases": ["PHASE2"]}, "statusModule": {"overallStatus": "RECRUITING", "lastUpdatePostDateStruct": {"date": "2026-10-01"}}}}]})
    oa = json.dumps({"results": [{"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x", "title": "Paper OA", "publication_date": "2026-10-02", "abstract_inverted_index": {"hola": [0], "mundo": [1]}}]})
    mr = json.dumps({"collection": [{"title": "CRISPR editing study", "abstract": "gene editing", "doi": "10.1101/abc", "date": "2026-10-03"}, {"title": "Otro tema", "abstract": "nada", "doi": "10.1101/zzz", "date": "2026-10-03"}]})
    ax = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1</id><title>AX t</title><summary>s</summary><published>2026-10-04T00:00:00Z</published></entry></feed>'
    rs = '<rss><channel><item><title>Noticia</title><link>https://ex.com/n1</link><description>&lt;p&gt;Hola&lt;/p&gt;</description><pubDate>Mon, 02 Nov 2026</pubDate></item></channel></rss>'
    tests = [("pubmed", parse_pubmed(None, pm, "q"), 1), ("clinicaltrials", parse_clinicaltrials(ct, "q"), 1), ("openalex", parse_openalex(oa, "q"), 1),
             ("medrxiv(filtra)", parse_medrxiv(mr, ["CRISPR gene editing"]), 1), ("arxiv", parse_arxiv(ax, "q"), 1), ("rss", parse_rss(rs, {"id": "x", "type": "noticia"}), 1)]
    ok = True
    for n, r, exp in tests:
        good = len(r) == exp and all(i["url"].startswith("http") and i["title"] for i in r)
        ok &= good; print(("OK   " if good else "FALLA"), n, len(r))
    assert parse_openalex(oa, "q")[0]["text"] == "hola mundo"
    print("\nSELFTEST", "OK" if ok else "FALLO"); sys.exit(0 if ok else 1)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=30); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest() if a.selftest else main(a.days)
