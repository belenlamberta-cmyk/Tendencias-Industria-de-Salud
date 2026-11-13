#!/usr/bin/env python3
"""Clasificador por REGLAS (sin IA). Identifica tecnologias de un catalogo cerrado en cada documento candidato.

- La cita textual es una frase copiada del propio documento (por construccion es literal).
- El horizonte y la fase del ciclo de expectativas se estiman con reglas simples y explicitas (abajo, RULES_DOC).
  Son una HEURISTICA, no una clasificacion de Gartner ni un juicio de IA.
- Escribe data/processed/extractions_rules.jsonl con el mismo formato que la extraccion con Gemini,
  asi el verificador y el tablero los tratan igual (la verificacion contra el texto crudo se aplica igual).

Uso:  python agent/rules.py            (procesa todos los candidatos)
      python agent/rules.py selftest
"""
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CAT = json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))["technologies"]
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

RULES_DOC = [
    ("R1 desilusion", "Fase 'Trough of Disillusionment', horizonte corto: el texto habla de fracasos o retrocesos (failed, setback, discontinued, withdrawn, halted)."),
    ("R2 meseta", "Fase 'Plateau of Productivity', horizonte corto: el texto habla de estandar establecido (standard of care, widely adopted, routinely used, gold standard, commercially available)."),
    ("R3 aprobacion", "Fase 'Slope of Enlightenment', horizonte corto: aprobacion o autorizacion regulatoria (approved, clearance, authorization)."),
    ("R4 ensayo fase 3", "Fase 'Slope of Enlightenment', horizonte corto: ensayo clinico en fase 3."),
    ("R5 ensayo fase 2", "Fase 'Slope of Enlightenment', horizonte mediano: ensayo clinico en fase 2."),
    ("R6 ensayo fase 1", "Fase 'Innovation Trigger', horizonte mediano: ensayo clinico en fase 1 o temprano."),
    ("R7 expectativas altas", "Fase 'Peak of Inflated Expectations', horizonte mediano: lenguaje de promesa fuerte (revolution, breakthrough, game-changing, unprecedented, paradigm shift)."),
    ("R8 preclinico", "Fase 'Innovation Trigger', horizonte largo: etapa preclinica o de prueba de concepto (in vitro, mouse/mice, proof-of-concept, preclinical)."),
    ("R9 desafios", "Fase 'Slope of Enlightenment', horizonte mediano: el texto describe desafios, limitaciones o barreras para su adopcion."),
    ("R10 por defecto", "Fase 'Innovation Trigger', horizonte mediano: sin otras señales; preprints y papers de metodos nuevos."),
]

P = lambda s: re.compile(s, re.I)
R_FAIL = P(r"\b(failed|failure|setback|discontinu\w+|withdr[ae]w\w*|halted|terminated early|shut down|layoffs?)\b")
R_STD = P(r"standard of care|widely adopted|routinely used|routine clinical|gold standard|well[- ]established|commercially available")
R_APPR = P(r"\b(approved|approval|fda clearance|cleared by|authori[sz]ation|authori[sz]ed)\b")
R_PH3 = P(r"phase\s*(3|iii)\b")
R_PH2 = P(r"phase\s*(2|ii)\b")
R_PH1 = P(r"phase\s*(1|i)\b|early[- ]phase|first[- ]in[- ]human")
R_HYPE = P(r"revolution\w*|breakthrough|game[- ]chang\w+|unprecedented|paradigm shift")
R_PRE = P(r"\bin vitro\b|\bmouse\b|\bmice\b|\bmurine\b|proof[- ]of[- ]concept|preclinical")
R_CHAL = P(r"\b(challenges?|limitations?|barriers?|bottlenecks?|hurdles?)\b")

COUNTRIES = ["Argentina", "Brazil", "Chile", "Mexico", "Colombia", "United States", "Canada", "United Kingdom", "Germany", "France", "Spain", "Italy", "Netherlands",
             "Switzerland", "Sweden", "Denmark", "Norway", "Finland", "Belgium", "Austria", "Ireland", "Portugal", "Poland", "China", "Japan", "South Korea", "India",
             "Singapore", "Taiwan", "Israel", "Australia", "Saudi Arabia", "South Africa", "Egypt", "Turkey", "Russia", "Iran", "Pakistan"]
COMPANIES = ["Illumina", "10x Genomics", "Thermo Fisher", "Roche", "Genentech", "Novartis", "Pfizer", "Moderna", "BioNTech", "Regeneron", "AstraZeneca", "GSK", "Sanofi",
             "Merck", "Johnson & Johnson", "Eli Lilly", "Bayer", "Amgen", "Gilead", "AbbVie", "Takeda", "Vertex", "Google", "DeepMind", "Isomorphic Labs", "NVIDIA",
             "Microsoft", "Amazon Web Services", "Recursion", "Insilico Medicine", "Ginkgo Bioworks", "Twist Bioscience", "CRISPR Therapeutics", "Beam Therapeutics",
             "Intellia", "Editas", "Oxford Nanopore", "Pacific Biosciences", "Agilent", "Danaher", "Tecan", "Hamilton", "Opentrons", "Benchling", "Emerald Cloud Lab", "Strateos"]
AMOUNT = re.compile(r"(?:US\$|\$|€|£)\s?\d[\d.,]*(?:\s?(?:million|billion|bn|M|B)\b)?")

def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]

def hits(tech, text):
    return sum(len(re.findall(p, text, re.I)) for p in tech["patterns"])

def best_quote(tech, title, text):
    """Frase del texto con mas coincidencias; si no hay, el titulo. Siempre una subcadena literal."""
    best, score = None, 0
    for s in sentences(text):
        n = hits(tech, s)
        w = len(s.split())
        if n > score and 6 <= w:
            best, score = s, n
    if not best and len(title.split()) >= 6 and hits(tech, title): best = title.strip()
    if not best: return None
    words = best.split(" ")
    return " ".join(words[:40]) if len(words) > 40 else best

def horizon_phase(it, blob):
    st = it.get("source_type", "")
    if R_FAIL.search(blob): return "corto", "Trough of Disillusionment", "R1 desilusion"
    if R_STD.search(blob): return "corto", "Plateau of Productivity", "R2 meseta"
    if st in ("regulacion", "noticia") and R_APPR.search(blob): return "corto", "Slope of Enlightenment", "R3 aprobacion"
    if st == "ensayo" and R_PH3.search(blob): return "corto", "Slope of Enlightenment", "R4 ensayo fase 3"
    if st == "ensayo" and R_PH2.search(blob): return "mediano", "Slope of Enlightenment", "R5 ensayo fase 2"
    if st == "ensayo" and R_PH1.search(blob): return "mediano", "Innovation Trigger", "R6 ensayo fase 1"
    if R_HYPE.search(blob): return "mediano", "Peak of Inflated Expectations", "R7 expectativas altas"
    if R_PRE.search(blob): return "largo", "Innovation Trigger", "R8 preclinico"
    if R_CHAL.search(blob) and st in ("paper", "noticia", "regulacion"): return "mediano", "Slope of Enlightenment", "R9 desafios"
    return "mediano", "Innovation Trigger", "R10 por defecto"

def literal_hits(names, blob):
    return [n for n in names if re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", blob)]

def classify(it, max_techs=2, min_hits=2):
    title, text = it.get("title", ""), it.get("text", "")
    blob = title + " " + text
    scored = []
    for t in CAT:
        n = hits(t, text) + 3 * hits(t, title)
        if n >= min_hits: scored.append((n, t))
    scored.sort(key=lambda x: -x[0])
    out = []
    for n, t in scored[:max_techs]:
        q = best_quote(t, title, text)
        if not q: continue
        hz, ph, rule = horizon_phase(it, blob)
        out.append({"technology": t["name"], "category": t["category"], "horizon": hz, "hype_phase": ph,
                    "justification": f"Estimación por regla automática (sin IA), {rule}: el texto menciona esta tecnología {n} vez/veces con las palabras clave del catálogo. Horizonte y fase son heurísticos.",
                    "quote": q, "companies": literal_hits(COMPANIES, blob), "countries": literal_hits(COUNTRIES, blob),
                    "amounts": list(dict.fromkeys(m.strip() for m in AMOUNT.findall(blob)))[:3], "rule": rule})
    return out

def main():
    cands = [json.loads(l) for l in (PROC / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] if (PROC / "candidates.jsonl").exists() else []
    rows, n_tr = [], 0
    for it in cands:
        tr = classify(it)
        n_tr += len(tr)
        rows.append({"item_id": it["id"], "model": "reglas-v1", "extracted_at": NOW(), "result": {"trends": tr}, "error": None})
    PROC.mkdir(parents=True, exist_ok=True)
    with open(PROC / "extractions_rules.jsonl", "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Reglas: {len(cands)} documentos analizados | {n_tr} tendencias propuestas -> {PROC/'extractions_rules.jsonl'}")

def selftest():
    it = {"id": "a", "source": "pubmed", "source_type": "paper", "url": "https://x.org/a", "title": "Digital twin technology in cardiovascular care",
          "text": "Rapid advances in artificial intelligence have accelerated the emergence of digital twin technology in precision healthcare. Challenges remain around interoperability and evidence. Researchers in Finland and Illumina collaborated and raised $50 million."}
    tr = classify(it)
    assert tr and tr[0]["technology"] == "Gemelos digitales", tr
    t = tr[0]
    assert t["quote"] in it["text"] or t["quote"] in it["title"], "cita literal"
    assert t["hype_phase"] == "Slope of Enlightenment" and t["horizon"] == "mediano" and t["rule"] == "R9 desafios", t
    assert "Finland" in t["countries"] and "Illumina" in t["companies"] and "$50 million" in t["amounts"], t
    it2 = dict(it, id="b", text="We show in mice that base editing corrects the mutation in vitro. Base editing is a promising approach.", title="Base editing in a mouse model")
    t2 = classify(it2)[0]
    assert t2["technology"].startswith("Edición de bases") and t2["horizon"] == "largo" and t2["rule"] == "R8 preclinico", t2
    assert classify({"id": "c", "source_type": "paper", "title": "Hospital parking", "text": "Nothing relevant here at all, really."}) == []
    print("SELFTEST OK (reglas)")

if __name__ == "__main__":
    selftest() if len(sys.argv) > 1 and sys.argv[1] == "selftest" else main()
