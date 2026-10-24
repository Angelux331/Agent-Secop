"""
Genera el reporte diario Markdown a partir de los análisis de la IA.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.config import MIN_SCORE, REPORTS_DIR, TOP_N_REPORTE

def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
            if parsed is not None:
                return [str(parsed)]
        except Exception:
            pass
        return [s]
    return [str(value)]

def _clean_url(url: Any) -> str:
    if url is None:
        return ""
    if isinstance(url, dict):
        for k in ("url", "href", "link", "value"):
            if url.get(k):
                return _clean_url(url.get(k))
        return ""

    s = str(url).strip()
    if not s or s.lower() in {"none", "null", "nan"}:
        return ""

    if s.startswith("http://") or s.startswith("https://"):
        m = re.match(r"https?://[^\s\"'<>}\\]]+", s)
        return m.group(0) if m else s

    if "http" in s:
        m = re.search(r"https?://[^\s\"'<>}\\]]+", s)
        if m:
            return m.group(0)
    return s

def _fmt_money(valor: Any) -> str:
    try:
        if valor is None or valor == "":
            return "N/D"
        return f"${float(valor):,.0f} COP"
    except Exception:
        return str(valor)

def _render_item(lines: list[str], i: int, a: dict) -> None:
    reqs_l = _as_list(a.get("requisitos"))
    docs_l = _as_list(a.get("documentos"))
    riesgos_l = _as_list(a.get("riesgos"))
    url = _clean_url(a.get("url"))

    entidad = a.get("entidad") or "Entidad N/D"
    score = a.get("score", 0)

    lines.append(f"## {i}. Score {score}/10 — {entidad}")
    lines.append("")
    lines.append(f"**ID:** `{a.get('proceso_id')}`  ")
    lines.append(f"**Valor est.:** {_fmt_money(a.get('valor'))}  ")
    if url:
        lines.append(f"**URL:** {url}  ")
    else:
        lines.append("**URL:** N/D (buscar el ID en SECOP II)  ")
    lines.append("")
    lines.append(f"**Objeto:** {a.get('objeto') or 'N/D'}")
    lines.append("")
    lines.append(f"**Por qué importa:** {a.get('motivo_score') or 'N/D'}")
    lines.append("")
    lines.append("### Resumen")
    lines.append(a.get("resumen") or "_Sin resumen_")
    lines.append("")

    lines.append("### Requisitos principales")
    if reqs_l:
        for r in reqs_l:
            lines.append(f"- {r}")
    else:
        lines.append("- _No especificados en el análisis_")
    lines.append("")

    lines.append("### Documentos a reunir")
    if docs_l:
        for d in docs_l:
            ds = str(d).strip()
            if ds.startswith("[ ]"):
                lines.append(f"- {ds}")
            else:
                lines.append(f"- [ ] {ds}")
    else:
        lines.append("- [ ] Revisar pliego completo en SECOP II")
    lines.append("")

    if riesgos_l:
        lines.append("### Riesgos")
        for r in riesgos_l:
            lines.append(f"- {r}")
        lines.append("")

    lines.append(
        f"**Siguiente paso:** {a.get('siguiente_paso') or 'Revisar pliego en SECOP II'}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

def build_report(analisis: list[dict], run_meta: dict) -> Path:
    all_sorted = sorted(
        analisis,
        key=lambda x: float(x.get("score") or 0),
        reverse=True,
    )
    relevantes = [
        a for a in all_sorted if float(a.get("score") or 0) >= float(MIN_SCORE)
    ][: int(TOP_N_REPORTE)]

    # Casi relevantes: bajo umbral pero con algo de señal
    casi = [
        a
        for a in all_sorted
        if float(MIN_SCORE) > float(a.get("score") or 0) >= 3.0
    ][:10]

    ts = datetime.now().strftime("%Y-%m-%d")
    path = REPORTS_DIR / f"reporte_secop_{ts}.md"

    lines: list[str] = []
    lines.append(f"# Reporte SECOP II — {ts}")
    lines.append("")
    lines.append(f"- Procesos fetch: **{run_meta.get('fetched', 0)}**")
    lines.append(f"- Analizados con IA: **{run_meta.get('analyzed', 0)}**")
    lines.append(f"- Relevantes (score ≥ {MIN_SCORE}): **{len(relevantes)}**")
    lines.append(f"- Casi relevantes (3 ≤ score < {MIN_SCORE}): **{len(casi)}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## Oportunidades relevantes")
    lines.append("")
    if not relevantes:
        lines.append("_Ninguna por encima del umbral en este lote._")
        lines.append("")
    else:
        for i, a in enumerate(relevantes, 1):
            _render_item(lines, i, a)

    if casi:
        lines.append("## Casi relevantes (revisión manual)")
        lines.append("")
        for i, a in enumerate(casi, 1):
            _render_item(lines, i, a)

    if not relevantes and not casi and all_sorted:
        lines.append("## Todos los analizados (debug)")
        lines.append("")
        for i, a in enumerate(all_sorted, 1):
            _render_item(lines, i, a)
    elif not all_sorted:
        lines.append("_No hubo análisis en esta corrida._")
        lines.append("")
        lines.append(
            "Revisa API key/modelo, `MAX_PROCESOS_IA`, keywords o si todo ya estaba en la DB."
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path