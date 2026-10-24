from __future__ import annotations

import logging
from datetime import datetime, timezone

from agent.config import MAX_PROCESOS_IA, load_empresa
from agent.db import already_analyzed, init_db, log_run, save_analisis
from agent.grok_analyzer import analyze_proceso, reset_auth_flag
from agent.reporter import build_report
from agent.secop_client import fetch_recent_procesos, prefilter

logger = logging.getLogger(__name__)

def run_daily_job() -> str:
    init_db()
    reset_auth_flag()
    started = datetime.now(timezone.utc).isoformat()
    empresa = load_empresa()

    procesos = fetch_recent_procesos(limit=300)
    fetched = len(procesos)

    nuevos = [p for p in procesos if not already_analyzed(p["proceso_id"])]
    candidatos = prefilter(nuevos, empresa)[:MAX_PROCESOS_IA]

    logger.info(
        "Fetch=%s | nuevos=%s | a_IA=%s",
        fetched,
        len(nuevos),
        len(candidatos),
    )

    analisis = []
    auth_dead = False
    for p in candidatos:
        result = analyze_proceso(p, empresa)
        # Solo persistir si Grok respondió de verdad
        if result.get("error") in {"auth_failed", "auth_or_bad_request"}:
            auth_dead = True
            break
        if result.get("error"):
            logger.warning("Skip persist por error en %s: %s", p["proceso_id"], result.get("error"))
            continue
        save_analisis(result)
        analisis.append(result)

    if auth_dead:
        logger.error(
            "Run abortado por API key inválida. "
            "Corrige .env y vuelve a ejecutar python run_once.py"
        )

    relevant = [a for a in analisis if a.get("score", 0) >= 6]
    finished = datetime.now(timezone.utc).isoformat()

    report_path = build_report(
        analisis,
        {"fetched": fetched, "analyzed": len(analisis), "relevant": len(relevant)},
    )
    log_run(started, finished, fetched, len(analisis), len(relevant), str(report_path))

    logger.info("Reporte generado: %s", report_path)
    return str(report_path)