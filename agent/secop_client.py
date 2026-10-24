"""
Cliente SECOP II vía datos abiertos (Socrata / datos.gov.co).
Ajusta FIELD_CANDIDATES si tu dataset usa otros nombres de columnas.
"""
from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from agent.config import (
    LOOKBACK_HOURS,
    SECOP_APP_TOKEN,
    SECOP_DATASET_ID,
    SECOP_DOMAIN,
)

logger = logging.getLogger(__name__)

# Mapea nombres frecuentes de columnas SECOP → campos internos.
FIELD_CANDIDATES = {
    "proceso_id": [
        "id_del_proceso",
        "id_proceso",
        "numero_de_proceso",
        "referencia_del_proceso",
        "processnumber",
        "id",
    ],
    "objeto": [
        "objeto_del_contrato",
        "objeto",
        "descripcion",
        "detailobject",
        "nombre_del_procedimiento",
    ],
    "entidad": [
        "entidad",
        "nombre_de_la_entidad",
        "entityname",
        "entidad_compradora",
    ],
    "valor": [
        "valor_total_estimado",
        "valor_estimado",
        "cuantia",
        "priced",
        "valor_del_contrato",
        "valor",
    ],
    "estado": [
        "estado_del_procedimiento",
        "estado",
        "processstatus",
        "estado_del_proceso",
    ],
    "fecha_pub": [
        "fecha_de_publicacion_del_proceso",
        "fecha_publicacion",
        "published_date",
        "fecha_de_publicacion",
        "created_date",
    ],
    "ciudad": [
        "ciudad_de_la_unidad_de_contratacion",
        "ciudad",
        "municipio",
        "city",
    ],
    "departamento": [
        "departamento_entidad",
        "departamento",
        "department",
    ],
    "url": [
        "urlproceso",
        "url",
        "link",
        "url_del_proceso",
    ],
    "modalidad": [
        "modalidad_de_contratacion",
        "modalidad",
        "proceduretype",
    ],
}

def _pick(row: dict, keys: list[str]) -> Any:
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        if k.lower() in lower_map and lower_map[k.lower()] not in (None, ""):
            return lower_map[k.lower()]
    return None

def _flatten_url(val: Any) -> str:
    """
    Normaliza URLs que vienen como:
    - string directa
    - dict {'url': 'https://...'}
    - string que parece dict
    """
    if val is None:
        return ""

    if isinstance(val, dict):
        for k in ("url", "href", "link", "value", "Uri", "uri"):
            if val.get(k):
                return _flatten_url(val.get(k))
        # último recurso: primer valor string con http
        for v in val.values():
            s = _flatten_url(v)
            if s.startswith("http"):
                return s
        return ""

    s = str(val).strip()
    if not s or s.lower() in {"none", "null", "nan"}:
        return ""

    # Ya es URL limpia
    if s.startswith("http://") or s.startswith("https://"):
        # por si trae basura al final
        m = re.match(r"https?://[^\s\"'<>}\\]]+", s)
        return m.group(0) if m else s

    # String que parece dict/JSON
    if "http" in s and (s.startswith("{") or s.startswith("'") or "url" in s.lower()):
        try:
            obj = ast.literal_eval(s)
            if isinstance(obj, (dict, list, tuple, str)):
                return _flatten_url(obj)
        except Exception:
            pass
        m = re.search(r"https?://[^\s\"'<>}\\]]+", s)
        if m:
            return m.group(0)

    return s

def _parse_valor(valor_raw: Any) -> float | None:
    if valor_raw is None:
        return None
    try:
        s = str(valor_raw).replace("$", "").replace(" ", "").strip()
        # formato CO: 1.234.567,89 o US: 1,234,567.89
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
        return float(s)
    except Exception:
        return None

def _normalize(row: dict) -> dict | None:
    proceso_id = _pick(row, FIELD_CANDIDATES["proceso_id"])
    objeto = _pick(row, FIELD_CANDIDATES["objeto"])
    if not proceso_id or not objeto:
        return None

    return {
        "proceso_id": str(proceso_id).strip(),
        "objeto": str(objeto)[:4000],
        "entidad": str(_pick(row, FIELD_CANDIDATES["entidad"]) or ""),
        "valor": _parse_valor(_pick(row, FIELD_CANDIDATES["valor"])),
        "estado": str(_pick(row, FIELD_CANDIDATES["estado"]) or ""),
        "fecha_pub": str(_pick(row, FIELD_CANDIDATES["fecha_pub"]) or ""),
        "ciudad": str(_pick(row, FIELD_CANDIDATES["ciudad"]) or ""),
        "departamento": str(_pick(row, FIELD_CANDIDATES["departamento"]) or ""),
        "url": _flatten_url(_pick(row, FIELD_CANDIDATES["url"])),
        "modalidad": str(_pick(row, FIELD_CANDIDATES["modalidad"]) or ""),
        "raw": row,
    }

def _parse_fecha(fp: str) -> datetime | None:
    if not fp:
        return None
    fp = str(fp).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            chunk = fp[:26].rstrip("Z")
            dt = datetime.strptime(chunk, fmt.replace("Z", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def fetch_recent_procesos(limit: int = 200) -> list[dict]:
    """
    Baja procesos recientes. Si el dataset no filtra bien por fecha,
    trae los últimos N y filtra en cliente.
    """
    url = f"https://{SECOP_DOMAIN}/resource/{SECOP_DATASET_ID}.json"
    headers = {"Accept": "application/json"}
    if SECOP_APP_TOKEN:
        headers["X-App-Token"] = SECOP_APP_TOKEN

    params_list = [
        {"$limit": limit, "$order": "fecha_de_publicacion_del_proceso DESC"},
        {"$limit": limit, "$order": ":created_at DESC"},
        {"$limit": limit},
    ]

    data: list = []
    last_err = None
    for params in params_list:
        try:
            r = requests.get(url, headers=headers, params=params, timeout=60)
            if r.status_code == 200:
                payload = r.json()
                if isinstance(payload, list):
                    data = payload
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

        fp = item.get("fecha_pub") or ""
        dt = _parse_fecha(fp)
        # Si no hay fecha parseable, igual lo dejamos (mejor recall)
        if dt is not None and dt < cutoff:
            continue
        out.append(item)

    logger.info("SECOP fetch: %s filas crudas → %s normalizadas", len(data), len(out))
    return out

def prefilter(procesos: list[dict], empresa: dict) -> list[dict]:
    """Filtro barato antes de gastar tokens en la IA."""
    pos = [k.lower() for k in empresa.get("keywords_positivas", [])]
    neg = [k.lower() for k in empresa.get("keywords_negativas", [])]
    vmin = empresa.get("valor_min_cop")
    vmax = empresa.get("valor_max_cop")

    selected: list[dict] = []
    for p in procesos:
        text = (
            f"{p.get('objeto', '')} {p.get('modalidad', '')} "
            f"{p.get('entidad', '')} {p.get('ciudad', '')}"
        ).lower()

        if neg and any(n in text for n in neg):
            continue

        valor = p.get("valor")
        # Solo aplica min/max si hay valor numérico Y el perfil define umbral
        if valor is not None:
            if vmin is not None and valor < float(vmin):
                continue
            if vmax is not None and valor > float(vmax):
                continue

        hits = sum(1 for k in pos if k in text) if pos else 0
        item = dict(p)
        item["_kw_hits"] = hits
        item["_weak_match"] = hits == 0
        selected.append(item)

    # Más hits primero; luego mayor valor; los sin keyword al final
    selected.sort(
        key=lambda x: (
            -int(x.get("_kw_hits") or 0),
            -(x.get("valor") or 0),
        )
    )
    return selected