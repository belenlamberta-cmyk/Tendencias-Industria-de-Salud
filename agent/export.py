#!/usr/bin/env python3
"""Exporta los resultados verificados al formato que lee el dashboard: docs/data/trends.json
Solo usa datos ya guardados (nada se inventa aca). Uso: python agent/export.py"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P, RAWF = ROOT / "data" / "processed", ROOT / "data" / "raw"
TAX = json.loads((Path(__file__).parent / "taxonomy.json").read_text(encoding="utf-8"))

def rd(p):
    p = Path(p)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []

def main():
    tf = P / "translations_es.json"
    TR = json.loads(tf.read_text(encoding="utf-8")) if tf.exists() else {"items": {}, "quotes": {}}
    trends, seen = [], set()
    for t in rd(P / "verified_trends.jsonl"):
        k = (t["url"], t["technology"].strip().lower())
        if k in seen: continue
        seen.add(k)
        trends.append({k2: t.get(k2) for k2 in ("technology", "category", "horizon", "hype_phase", "justification", "quote", "companies", "countries",
                                                 "amounts", "url", "source", "title", "published", "evidence_level", "region", "flags", "status", "method")})
        it = TR["items"].get(t["url"], {})   # traduccion al espanol (la cita original se conserva para verificar)
        trends[-1].update({"title_es": it.get("title_es"), "resumen_es": it.get("resumen_es"), "quote_es": TR["quotes"].get(t.get("quote"))})
    raw, ext, log = rd(RAWF / "raw_items.jsonl"), rd(P / "extractions.jsonl"), rd(P / "verification_log.jsonl")
    runs = rd(RAWF / "run_log.jsonl")
    vt = rd(P / "verified_trends.jsonl"); proposed = len(vt) + sum(1 for l in log if l.get("action") == "descartada")
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_items": len(raw), "candidates": len(rd(P / "candidates.jsonl")), "items_processed_by_llm": len(ext), "items_processed_by_rules": len(rd(P / "extractions_rules.jsonl")), "items_processed_by_claude": len(rd(P / "extractions_claude.jsonl")),
        "trends_proposed": proposed, "trends_verified": len(trends),
        "verification": dict(Counter(l["action"] for l in log)),
        "sources_raw": dict(Counter(r["source"] for r in raw)),
        "models_used": dict(Counter(e.get("model", "?") for e in ext)),
        "last_collection": runs[-1] if runs else None,
        "categories": {k: v["label"] for k, v in TAX["categories"].items()},
        "hype_phases": TAX["hype_phases"], "horizons": TAX["horizons"],
    }
    out = ROOT / "docs" / "data" / "trends.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "trends": trends}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Exportado: {len(trends)} tendencias verificadas ({proposed} propuestas) -> {out}")

if __name__ == "__main__":
    main()
