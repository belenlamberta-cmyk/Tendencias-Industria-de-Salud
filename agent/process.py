#!/usr/bin/env python3
"""Etapa 2 - Filtro, extraccion con Gemini y VERIFICACION.
  python process.py filter [--max 250]
  python process.py extract [--limit 40] [--model auto]
  python process.py verify
  python process.py selftest
Regla: Gemini solo puede usar el texto del item. Todo lo que no se pueda comprobar contra el texto crudo se descarta o se marca, y queda en verification_log.jsonl."""
import socket, argparse, json, os, re, sys, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAWF = ROOT / "data" / "raw" / "raw_items.jsonl"
PROC = ROOT / "data" / "processed"
TAX = json.loads((Path(__file__).parent / "taxonomy.json").read_text(encoding="utf-8"))
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

def read_jsonl(p):
    p = Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
def write_jsonl(p, rows, mode="w"):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, mode, encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
def norm(s):
    s = unicodedata.normalize("NFKC", s or "").casefold()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()

# ---------------- 1. FILTRO ----------------
def score_item(it):
    title, body = norm(it["title"]), norm(it["text"])
    cats, score = {}, 0
    for cid, c in TAX["categories"].items():
        hits = 0
        for k in c["keywords"]:
            if re.search(r"\b" + re.escape(k) + r"\b", title): hits += 2
            elif re.search(r"\b" + re.escape(k) + r"\b", body): hits += 1
        if hits: cats[cid] = hits; score += hits
    return score, cats

def filter_items(items, max_items=250, min_score=2, per_source=60):
    keep, out = [], []
    for it in items:
        s, cats = score_item(it)
        if s >= min_score: keep.append({**it, "prefilter_score": s, "prefilter_categories": cats})
        else: out.append({"id": it["id"], "url": it["url"], "source": it["source"], "reason": f"score {s} < {min_score}"})
    keep.sort(key=lambda x: -x["prefilter_score"])
    final, cnt = [], {}
    for it in keep:
        if cnt.get(it["source"], 0) >= per_source or len(final) >= max_items:
            out.append({"id": it["id"], "url": it["url"], "source": it["source"], "reason": "tope por fuente/total"}); continue
        cnt[it["source"]] = cnt.get(it["source"], 0) + 1; final.append(it)
    return final, out

def cmd_filter(a):
    items = read_jsonl(RAWF)
    final, out = filter_items(items, a.max)
    write_jsonl(PROC / "candidates.jsonl", final); write_jsonl(PROC / "excluded.jsonl", out)
    by = {}
    for i in final: by[i["source"]] = by.get(i["source"], 0) + 1
    print(f"Crudos: {len(items)} | candidatos: {len(final)} | excluidos: {len(out)}"); print("Por fuente:", by)

# ---------------- 2. EXTRACCION (Gemini) ----------------
API = "https://generativelanguage.googleapis.com/v1beta/"
def rank_models(models):
    """Ordena modelos flash: primero los estables, luego lite, al final preview/omni (que suelen NO estar en el plan gratuito)."""
    bad = re.compile(r"image|tts|live|audio|embed|thinking|exp|robotics|computer")
    out = []
    for m in models:
        name = m["name"].split("/")[-1]
        if "flash" not in name or "generateContent" not in m.get("supportedGenerationMethods", []) or bad.search(name): continue
        rank = 2 if re.search(r"preview|omni", name) else (1 if "lite" in name else 0)
        out.append((rank, name))
    out.sort(key=lambda x: (x[0], [-ord(c) for c in x[1]]))   # rank asc, nombre desc (versiones nuevas primero)
    return [n for _, n in out]

def list_models(key):
    req = urllib.request.Request(API + "models?pageSize=200", headers={"x-goog-api-key": key})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["models"]

def http_msg(e):
    try: return json.loads(e.read())["error"]["message"][:220]
    except Exception: return str(e)

def pick_model(key, tries=6):
    """Prueba los modelos candidatos con un pedido minimo y devuelve el primero que responde."""
    cands = rank_models(list_models(key))
    if not cands: raise RuntimeError("No encontre modelos flash disponibles; fijalo con --model")
    for name in cands[:tries]:
        try:
            gemini_call('Responde solo este JSON: {"ok": true}', name, key)
            print(f"  [OK]    {name}"); return name
        except urllib.error.HTTPError as e: print(f"  [FALLA] {name}: HTTP {e.code} - {http_msg(e)}")
        except Exception as e: print(f"  [FALLA] {name}: {type(e).__name__}: {e}")
        time.sleep(2)
    raise RuntimeError("Ningun modelo respondio. Revisa la clave/cuota en aistudio.google.com (Rate limits) o fija uno con --model")

def gemini_call(prompt, model, key, timeout=45):
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    req = urllib.request.Request(API + f"models/{model}:generateContent", data=json.dumps(body).encode(),
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return r["candidates"][0]["content"]["parts"][0]["text"]

def build_prompt(it):
    cats = "; ".join(f'{k} ({v["label"]})' for k, v in TAX["categories"].items())
    return f"""Sos un analista que ayuda a decidir que tecnologias incorporar en un laboratorio de investigacion en salud/biotecnologia (tipo CONICET).
REGLAS ESTRICTAS:
- Usa SOLO el texto de abajo. No uses conocimiento propio ni inventes datos.
- Si el texto no trata una tecnologia o tendencia relevante para un laboratorio de investigacion, devolve {{"trends": []}}.
- Maximo 2 tendencias. Cada una DEBE incluir "quote": una cita copiada EXACTAMENTE del texto (8 a 40 palabras, sin modificar).
- companies, countries y amounts: solo si aparecen literalmente en el texto; si no, listas vacias.
- horizon y hype_phase son tu JUICIO: justificalo en una frase ("justification") apoyada en el texto.
Valores permitidos: category = {cats}; horizon = UNA sola palabra: corto | mediano | largo (corto=0-2 anios, mediano=2-5, largo=5-10+; escribi solo la palabra, sin parentesis ni numeros); hype_phase = {" | ".join(TAX["hype_phases"])}.
Responde SOLO JSON con esta forma: {{"trends":[{{"technology":"","category":"","horizon":"","hype_phase":"","justification":"","quote":"","companies":[],"countries":[],"amounts":[]}}]}}

TITULO: {it['title']}
FUENTE: {it['source']} ({it['source_type']})
TEXTO: {it['text']}"""

class QuotaExhausted(Exception): pass

def call_with_fallback(prompt, models, key, dead):
    """Prueba los modelos en orden. 429 (cuota) -> marca el modelo como agotado hoy y sigue con otro. 503 (alta demanda) -> reintenta una vez y pasa al siguiente."""
    last = "sin modelos disponibles"
    for name in [m for m in models if m not in dead]:
        for attempt in range(2):
            try: return gemini_call(prompt, name, key), name
            except urllib.error.HTTPError as e:
                last = f"{name}: HTTP {e.code} {http_msg(e)}"
                if e.code == 429: dead.add(name); print(f"  [cuota agotada] {name} -> sigo con otro modelo"); break
                if e.code == 503 and attempt == 0: time.sleep(10); continue
                if e.code == 503: break
                raise
            except (TimeoutError, socket.timeout, ConnectionError, urllib.error.URLError) as e:
                last = f"{name}: {type(e).__name__} {e}"
                print(f"  [sin respuesta] {name} ({type(e).__name__}) -> " + ("reintento" if attempt == 0 else "lo descarto en esta corrida y sigo con otro"))
                if attempt == 1: dead.add(name)
                time.sleep(3); continue
    raise QuotaExhausted(last)

def cmd_extract(a):
    keys = [os.environ[n].strip() for n in ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 6)] if os.environ.get(n, "").strip()]
    if not keys: sys.exit("Falta GEMINI_API_KEY (en Colab: Secretos -> GEMINI_API_KEY).")
    key = keys[0]; print(f"Claves disponibles: {len(keys)}")
    if a.model == "auto":
        print("Modelos candidatos para tu clave:")
        try: models = rank_models(list_models(key))[:6]
        except Exception as e:
            print(f"No pude consultar la lista de modelos ({type(e).__name__}: {e}). Se reintenta en la proxima corrida."); return
        for m in models: print("  -", m)
    else: models = [a.model]
    good_keys, key_models = [], {}
    for n_k, k in enumerate(keys, 1):
        ok = []
        for m in models:
            try: gemini_call('Responde solo este JSON: {"ok": true}', m, k, timeout=20); ok.append(m); print(f"  [clave {n_k}] responde {m}")
            except urllib.error.HTTPError as e: print(f"  [clave {n_k}] descartado {m}: HTTP {e.code} {http_msg(e)[:120]}")
            except Exception as e: print(f"  [clave {n_k}] descartado {m}: {type(e).__name__}")
            if len(ok) >= 3: break
        if ok: good_keys.append(k); key_models[k] = ok
        else: print(f"  [clave {n_k}] sin modelos disponibles hoy: la salteo")
    if not good_keys: print("Ninguna clave pudo usar ningun modelo (cuota agotada o demora de Gemini). Se reintenta en la proxima corrida."); return
    keys = good_keys
    cands = read_jsonl(PROC / "candidates.jsonl"); done = {r["item_id"] for r in read_jsonl(PROC / "extractions.jsonl")}
    todo = [c for c in cands if c["id"] not in done][: a.limit]
    print(f"Pendientes: {len([c for c in cands if c['id'] not in done])} | esta corrida: {len(todo)}")
    deads, ki, n_ok = [set() for _ in keys], 0, 0
    t0 = time.time()
    for n, it in enumerate(todo, 1):
        if time.time() - t0 > 25 * 60: print("Limite de 25 minutos alcanzado: se retoma en la proxima corrida."); break
        txt = None; fatal = False
        while ki < len(keys):
            try: txt, used = call_with_fallback(build_prompt(it), key_models[keys[ki]], keys[ki], deads[ki]); break
            except QuotaExhausted as e:
                ki += 1; print(f"  [clave {ki} agotada] " + ("paso a la siguiente clave" if ki < len(keys) else ""))
            except Exception as e:
                print(f"  [error inesperado] {type(e).__name__}: {e} -> salteo este item"); fatal = True; break
        if fatal: continue
        if txt is None:
            print("Todas las claves/modelos agotaron su cuota o estan saturados. Se retoma en la proxima corrida."); break
        res, err = None, None
        try: res = json.loads(txt)
        except Exception as ex: err = f"JSON invalido: {ex}"
        write_jsonl(PROC / "extractions.jsonl", [{"item_id": it["id"], "model": used, "extracted_at": NOW(), "result": res, "error": err}], "a"); n_ok += 1
        if n % 10 == 0: print(f"  {n}/{len(todo)}")
        time.sleep(a.sleep)
    print(f"Items procesados en esta corrida: {n_ok}")

# ---------------- 3. VERIFICACION ----------------
def nums(s): return re.findall(r"\d[\d.,]*\d|\d", s or "")

def canon_enum(value, allowed, prefix=False):
    v = norm(str(value or ""))
    for a in allowed:
        if v == norm(a) or (prefix and re.match(r"\s*" + re.escape(norm(a)) + r"\b", v)): return a
    return None

def verify_trend(t, it):
    """Devuelve (trend_limpio o None, lista de problemas)."""
    log, blob = [], norm(it["title"] + " " + it["text"])
    def P(problem, action): log.append({"item_id": it["id"], "url": it["url"], "technology": t.get("technology", ""), "problem": problem, "action": action})
    t = dict(t)
    for field, allowed, pre in (("horizon", TAX["horizons"], True), ("hype_phase", TAX["hype_phases"], False), ("category", list(TAX["categories"]), False)):
        c0 = canon_enum(t.get(field), allowed, pre)
        if c0 and c0 != t.get(field): P(f"{field} con formato distinto ('{t.get(field)}' -> '{c0}')", "normalizado"); t[field] = c0
    q = norm(t.get("quote", ""))
    if len(q.split()) < 6: P("cita ausente o muy corta", "descartada"); return None, log
    if q not in blob: P("la cita NO aparece en el texto crudo (posible alucinacion)", "descartada"); return None, log
    if t.get("category") not in TAX["categories"]: P(f"categoria invalida: {t.get('category')}", "descartada"); return None, log
    if t.get("horizon") not in TAX["horizons"]: P(f"horizonte invalido: {t.get('horizon')}", "descartada"); return None, log
    if t.get("hype_phase") not in TAX["hype_phases"]: P(f"fase invalida: {t.get('hype_phase')}", "descartada"); return None, log
    if not str(t.get("technology", "")).strip(): P("sin nombre de tecnologia", "descartada"); return None, log
    c = dict(t)
    for field in ("companies", "countries"):
        keep = []
        for v in t.get(field, []) or []:
            if norm(v) in blob: keep.append(v)
            else: P(f"{field}: '{v}' no figura en el texto", "quitado")
        c[field] = keep
    am = []
    for v in t.get("amounts", []) or []:
        if all(n in (it["title"] + " " + it["text"]) for n in nums(v)) and nums(v): am.append(v)
        else: P(f"monto '{v}' no figura en el texto", "quitado")
    c["amounts"] = am
    flags = []
    if str(it.get("published", ""))[:4].isdigit() and int(str(it["published"])[:4]) > datetime.now().year:
        flags.append("fecha_futura"); P(f"fecha de publicacion futura ({it['published']})", "marcado")
    c.update({"item_id": it["id"], "url": it["url"], "source": it["source"], "published": it.get("published", ""),
              "title": it["title"], "evidence_level": TAX["evidence_level"].get(it["source_type"], "s/d"),
              "region": it.get("region", "global"), "flags": flags, "status": "parcial" if any(l["action"] == "quitado" for l in log) else "verificado"})
    return c, log

def cmd_verify(a):
    raw = {i["id"]: i for i in read_jsonl(RAWF)}
    ok, logs, n_tr, n_err = [], [], 0, 0
    gem = read_jsonl(PROC / "extractions.jsonl")
    cla = read_jsonl(PROC / "extractions_claude.jsonl")   # analisis hecho por Claude (IA) a pedido del grupo
    rul = read_jsonl(PROC / "extractions_rules.jsonl")
    # prioridad: Claude > Gemini > reglas. Un documento revisado por Claude no se completa con reglas;
    # si Gemini ya propuso la misma categoria para el mismo documento, se omite la regla.
    reviewed = {e["item_id"] for e in cla}
    gem_keys = {(e["item_id"], t.get("category")) for e in gem if e.get("result") for t in (e["result"].get("trends") or [])}
    for method, exts in (("claude", cla), ("ia", gem), ("reglas", rul)):
        for e in exts:
            if e.get("error") or not e.get("result"): n_err += 1; continue
            if method == "reglas" and e["item_id"] in reviewed: continue
            for t in e["result"].get("trends", []) or []:
                if method == "reglas" and (e["item_id"], t.get("category")) in gem_keys: continue
                n_tr += 1
                c, lg = verify_trend(t, raw[e["item_id"]]) if e["item_id"] in raw else (None, [{"item_id": e["item_id"], "problem": "item no esta en el crudo", "action": "descartada"}])
                logs += lg
                if c: c["method"] = method; ok.append(c)
    write_jsonl(PROC / "verified_trends.jsonl", ok); write_jsonl(PROC / "verification_log.jsonl", logs)
    desc = sum(1 for l in logs if l["action"] == "descartada")
    print(f"Tendencias propuestas (IA + reglas): {n_tr} | verificadas: {len(ok)} (Claude: {sum(1 for c in ok if c['method']=='claude')}, Gemini: {sum(1 for c in ok if c['method']=='ia')}, reglas: {sum(1 for c in ok if c['method']=='reglas')}) | descartadas: {desc} | items con error: {n_err}")
    print(f"Problemas registrados: {len(logs)}  -> {PROC/'verification_log.jsonl'}")

# ---------------- autoprueba ----------------
def selftest():
    items = [{"id": "a", "url": "https://x.org/a", "title": "CRISPR base editing advances", "text": "x", "source": "pubmed", "source_type": "paper"},
             {"id": "b", "url": "https://x.org/b", "title": "Hospital parking rules", "text": "nothing relevant here", "source": "who_news", "source_type": "regulacion"}]
    f, o = filter_items(items); assert [i["id"] for i in f] == ["a"] and o[0]["id"] == "b", "filtro"
    it = {"id": "i1", "url": "https://x.org/1", "title": "Acme raises funds", "source": "stat", "source_type": "noticia", "published": "2027-01-01",
          "text": "Acme Bio raised $50 million to scale its autonomous laboratory platform in Argentina and Chile this year."}
    good = {"technology": "Laboratorio autonomo", "category": "automatizacion_lab", "horizon": "corto", "hype_phase": "Innovation Trigger", "justification": "j",
            "quote": "Acme Bio raised $50 million to scale its autonomous laboratory platform", "companies": ["Acme Bio", "FakeCorp"], "countries": ["Argentina"], "amounts": ["$50 million", "$900 million"]}
    c, lg = verify_trend(good, it)
    assert c and c["companies"] == ["Acme Bio"] and c["amounts"] == ["$50 million"] and c["status"] == "parcial" and "fecha_futura" in c["flags"], "limpieza"
    bad = dict(good, quote="Acme Bio raised $90 million to dominate the entire laboratory market worldwide")
    c2, lg2 = verify_trend(bad, it); assert c2 is None and "alucin" in lg2[0]["problem"], "cita falsa"
    c3, _ = verify_trend(dict(good, horizon="ayer"), it); assert c3 is None, "enum"
    ms = [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]} for n in
          ["gemini-omni-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash", "gemini-2.5-flash-image", "gemini-2.5-pro", "gemini-live-flash"]]
    r = rank_models(ms); assert r[0] == "gemini-3-flash" and r[-1] == "gemini-omni-flash-preview" and "gemini-2.5-flash-image" not in r and "gemini-2.5-pro" not in r, r
    c4, lg4 = verify_trend(dict(good, horizon="mediano (2-5)", hype_phase="innovation trigger"), it)
    assert c4 and c4["horizon"] == "mediano" and c4["hype_phase"] == "Innovation Trigger" and any(l["action"] == "normalizado" for l in lg4), "normalizacion"
    import io
    calls = []
    def fake(prompt, model, key):
        calls.append(model)
        if model == "A": raise urllib.error.HTTPError("u", 429, "q", {}, io.BytesIO(b'{"error":{"message":"quota"}}'))
        return '{"trends": []}'
    global gemini_call
    real, gemini_call = gemini_call, fake
    try:
        dead = set(); out, used = call_with_fallback("p", ["A", "B"], "k", dead)
        assert used == "B" and dead == {"A"}, "rotacion"
        out, used = call_with_fallback("p", ["A", "B"], "k", dead); assert calls[-1] == "B" and "A" not in calls[2:], "no reintenta modelo agotado"
    finally: gemini_call = real
    print("SELFTEST OK (rotacion de modelos al agotarse la cuota, normalizacion de horizonte, ranking de modelos sin preview/omni primero, filtro, cita falsa descartada, entidades/montos inventados quitados, fecha futura marcada)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["filter", "extract", "verify", "selftest"])
    ap.add_argument("--max", type=int, default=250); ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--model", default="auto"); ap.add_argument("--sleep", type=float, default=4.5)
    a = ap.parse_args(); {"filter": cmd_filter, "extract": cmd_extract, "verify": cmd_verify, "selftest": lambda _: selftest()}[a.cmd](a)
