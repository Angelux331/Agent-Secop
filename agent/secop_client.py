"""
Cliente SECOP II vía datos abiertos (Socrata).
Ajusta FIELD_MAP si tu dataset usa otros nombres de columnas.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from agent.config import (
    LOOKBACK_HOURS,
    SECOP_APP_TOKEN,
    SECOP_DATASET_ID,
    SECOP_DOMAIN,
)

logger = logging.getLogger(__name__)

# Mapea nombres frecuentes de columnas SECOP → campos internos.
# Revisa una fila real de tu dataset y ajusta.
FIELD_CANDIDATES = {
    "proceso_id": [
        "id_del_proceso",
        "id_proceso",
        "numero_de_proceso",
        "referencia_del_proceso",
        "processnumber",
        "id",
    ],
    "objeto": ["objeto_del_contrato", "objeto", "descripcion", "detailobject", "nombre_del_procedimiento"],
    "entidad": ["entidad", "nombre_de_la_entidad", "entityname", "entidad_compradora"],
    "valor": [
        "valor_total_estimado",
        "valor_estimado",
        "cuantia",
        "priced",
        "valor_del_contrato",
        "valor",
    ],
    "estado": ["estado_del_procedimiento", "estado", "processstatus", "estado_del_proceso"],
    "fecha_pub": [
        "fecha_de_publicacion_del_proceso",
        "fecha_publicacion",
        "published_date",
        "fecha_de_publicacion",
        "created_date",
    ],
    "ciudad": ["ciudad_de_la_unidad_de_contratacion", "ciudad", "municipio", "city"],
    "departamento": ["departamento_entidad", "departamento", "department"],
    "url": ["urlproceso", "url", "link", "url_del_proceso"],
    "modalidad": ["modalidad_de_contratacion", "modalidad", "proceduretype"],
}

def _pick(row: dict, keys: list[str]) -> Any:
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        if k.lower() in lower_map and lower_map[k.lower()] not in (None, ""):
            return lower_map[k.lower()]
    return None

def _normalize(row: dict) -> dict | None:
    proceso_id = _pick(row, FIELD_CANDIDATES["proceso_id"])
    objeto = _pick(row, FIELD_CANDIDATES["objeto"])
    if not proceso_id or not objeto:
        return None
    valor_raw = _pick(row, FIELD_CANDIDATES["valor"])
    try:
        valor = float(str(valor_raw).replace(",", "").replace("$", "").strip()) if valor_raw is not None else None
    except Exception:
        valor = None
    return {
        "proceso_id": str(proceso_id),
        "objeto": str(objeto)[:4000],
        "entidad": str(_pick(row, FIELD_CANDIDATES["entidad"]) or ""),
        "valor": valor,
        "estado": str(_pick(row, FIELD_CANDIDATES["estado"]) or ""),
        "fecha_pub": str(_pick(row, FIELD_CANDIDATES["fecha_pub"]) or ""),
        "ciudad": str(_pick(row, FIELD_CANDIDATES["ciudad"]) or ""),
        "departamento": str(_pick(row, FIELD_CANDIDATES["departamento"]) or ""),
        "url": str(_pick(row, FIELD_CANDIDATES["url"]) or ""),
        "modalidad": str(_pick(row, FIELD_CANDIDATES["modalidad"]) or ""),
        "raw": row,
    }

def fetch_recent_procesos(limit: int = 200) -> list[dict]:
    """
    Baja procesos recientes. Si el dataset no filtra bien por fecha,
    trae los últimos N y filtra en cliente.
    """
    url = f"https://{SECOP_DOMAIN}/resource/{SECOP_DATASET_ID}.json"
    headers = {"Accept": "application/json"}
    if SECOP_APP_TOKEN:
        headers["X-App-Token"] = SECOP_APP_TOKEN

    # Intento 1: order por fecha si el campo existe en tu dataset
    params_list = [
        {"$limit": limit, "$order": "fecha_de_publicacion_del_proceso DESC"},
        {"$limit": limit, "$order": ":created_at DESC"},
        {"$limit": limit},
    ]

    data = []
    last_err = None
    for params in params_list:
        try:
            r = requests.get(url, headers=headers, params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    break
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as e:
            last_err = str(e)

    if not data:
        logger.error("No se pudo obtener data de SECOP: %s", last_err)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        item = _normalize(row)
        if not item:
            continue
        # Filtro suave de frescura (si parsea fecha)
        fp = item["fecha_pub"]
        keep = True
        if fp:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d/%m/%Y",
            ):
                try:
                    dt = datetime.strptime(fp[:26], fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    keep = dt >= cutoff
                    break
                except Exception:
                    continue
        if keep:
            out.append(item)

    logger.info("SECOP fetch: %s filas crudas → %s normalizadas", len(data), len(out))
    return out

def prefilter(procesos: list[dict], empresa: dict) -> list[dict]:
    """Filtro barato antes de gastar tokens en Grok."""
    pos = [k.lower() for k in empresa.get("keywords_positivas", [])]
    neg = [k.lower() for k in empresa.get("keywords_negativas", [])]
    vmin = empresa.get("valor_min_cop")
    vmax = empresa.get("valor_max_cop")

    selected = []
    for p in procesos:
        text = f"{p.get('objeto','')} {p.get('modalidad','')}".lower()
        if any(n in text for n in neg):
            continue
        if vmin is not None and p.get("valor") is not None and p["valor"] < vmin:
            continue
        if vmax is not None and p.get("valor") is not None and p["valor"] > vmax:
            continue
        # Si hay keywords positivas, exigir al menos una (o relajar si quieres más recall)
        if pos and not any(k in text for k in pos):
            # Mantener algunos sin keyword para que Grok evalúe borde
            p["_weak_match"] = True
        else:
            p["_weak_match"] = False
        selected.append(p)

    # Prioriza matches fuertes
    selected.sort(key=lambda x: (x.get("_weak_match", True), -(x.get("valor") or 0)))
    return selected