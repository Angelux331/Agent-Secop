from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agent.config import REPORTS_DIR, TOP_N_REPORTE, MIN_SCORE

def build_report(analisis: list[dict], run_meta: dict) -> Path:
    # Ordenar por score
    ranked = sorted(analisis, key=lambda x: x.get("score", 0), reverse=True)
    ranked = [a for a in ranked if a.get("score", 0) >= MIN_SCORE][:TOP_N_REPORTE]

    ts = datetime.now().strftime("%Y-%m-%d")
    path = REPORTS_DIR / f"reporte_secop_{ts}.md"

    lines = []
    lines.append(f"# Reporte SECOP II — {ts}")
    lines.append("")
    lines.append(f"- Procesos fetch: **{run_meta.get('fetched', 0)}**")
    lines.append(f"- Analizados con IA: **{run_meta.get('analyzed', 0)}**")
    lines.append(f"- Relevantes (score ≥ {MIN_SCORE}): **{len(ranked)}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not ranked:
        lines.append("_No hay oportunidades por encima del umbral hoy._")
    else:
        for i, a in enumerate(ranked, 1):
            reqs = a.get("requisitos")
            docs = a.get("documentos")
            try:
                reqs_l = json.loads(reqs) if isinstance(reqs, str) else (reqs or [])
            except Exception:
                reqs_l = [str(reqs)]
            try:
                docs_l = json.loads(docs) if isinstance(docs, str) else (docs or [])
            except Exception:
                docs_l = [str(docs)]

            lines.append(f"## {i}. Score {a.get('score')}/10 — {a.get('entidad') or 'Entidad N/D'}")
            lines.append("")
            lines.append(f"**ID:** `{a.get('proceso_id')}`  ")
            if a.get("valor") is not None:
                lines.append(f"**Valor est.:** ${a.get('valor'):,.0f} COP  ")
            if a.get("url"):
                lines.append(f"**URL:** {a.get('url')}  ")
            lines.append("")
            lines.append(f"**Objeto:** {a.get('objeto')}")
            lines.append("")
            lines.append(f"**Por qué importa:** {a.get('motivo_score') or ''}")
            lines.append("")
            lines.append("### Resumen")
            lines.append(a.get("resumen") or "")
            lines.append("")
            lines.append("### Requisitos principales")
            for r in reqs_l:
                lines.append(f"- {r}")
            lines.append("")
            lines.append("### Documentos a reunir")
            for d in docs_l:
                lines.append(f"- [ ] {d}")
            lines.append("")
            if a.get("riesgos"):
                lines.append("### Riesgos")
                for r in a["riesgos"]:
                    lines.append(f"- {r}")
                lines.append("")
            lines.append(f"**Siguiente paso:** {a.get('siguiente_paso') or 'Revisar pliego en SECOP II'}")
            lines.append("")
            lines.append("---")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path