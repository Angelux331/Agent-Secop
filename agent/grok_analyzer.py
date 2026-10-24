from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI, AuthenticationError, BadRequestError, APIError

from agent.config import GROK_MODEL, XAI_API_KEY

logger = logging.getLogger(__name__)

_client = None
_auth_failed = False  # evita 25 llamadas inútiles

def get_client() -> OpenAI:
    global _client
    if _client is None:
        key = (XAI_API_KEY or "").strip()
        if not key:
            raise RuntimeError(
                "XAI_API_KEY vacía. Configúrala en el archivo .env (sin comillas)."
            )
        if key.lower().startswith("xai-tu") or "pega_aqui" in key.lower() or "your_" in key.lower():
            raise RuntimeError(
                "XAI_API_KEY parece un placeholder. Pega la key real de https://console.x.ai"
            )
        _client = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    return _client

SYSTEM_PROMPT = """Eres un analista experto en contratación pública colombiana (SECOP II).
Evalúas si un proceso encaja con el perfil de una empresa.
Responde SOLO JSON válido, sin markdown ni texto extra.
"""

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise

def analyze_proceso(proceso: dict, empresa: dict) -> dict:
    global _auth_failed

    base = {
        "proceso_id": proceso["proceso_id"],
        "objeto": proceso.get("objeto"),
        "entidad": proceso.get("entidad"),
        "valor": proceso.get("valor"),
        "url": proceso.get("url"),
        "score": 0.0,
        "resumen": "",
        "requisitos": "[]",
        "documentos": "[]",
        "motivo_score": "",
        "riesgos": [],
        "siguiente_paso": "",
        "relevante": False,
        "raw_json": "{}",
        "error": None,
    }

    if _auth_failed:
        base["error"] = "auth_failed"
        base["motivo_score"] = "API key inválida (se detuvo el lote)"
        base["riesgos"] = ["No se llamó a Grok por error de autenticación previo"]
        return base

    user_prompt = f"""
Perfil de la empresa (JSON):
{json.dumps(empresa, ensure_ascii=False)}

Proceso SECOP (JSON):
{json.dumps({k: v for k, v in proceso.items() if k != 'raw'}, ensure_ascii=False)}

Devuelve exactamente este JSON:
{{
  "score": <número 0 a 10, qué tan recomendable es participar>,
  "relevante": <true/false>,
  "motivo_score": "<1-3 frases>",
  "resumen": "<resumen del objeto y oportunidad en 3-5 líneas>",
  "requisitos_principales": ["req1", "req2", "req3"],
  "documentos_a_reunir": ["doc1", "doc2", "doc3"],
  "riesgos": ["riesgo1"],
  "siguiente_paso": "<acción concreta para la empresa>"
}}

Criterios de score:
- 9-10: encaje excelente con sector, valor y capacidades
- 7-8: bueno, vale la pena evaluar
- 5-6: dudoso / parcial
- 0-4: no recomendable
Si falta info de pliego completo, indica documentos típicos SECOP II (jurídicos, financieros, técnicos, experiencia, RUP si aplica) y márcalo en riesgos.
"""
    try:
        client = get_client()
        resp = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        content = resp.choices[0].message.content or "{}"
        data = _extract_json(content)
    except (AuthenticationError, BadRequestError) as e:
        msg = str(e)
        if "Incorrect API key" in msg or "invalid" in msg.lower() or "401" in msg or "400" in msg:
            _auth_failed = True
            logger.error(
                "Fallo de autenticación Grok/xAI. Revisa XAI_API_KEY en .env "
                "(console.x.ai). No se harán más llamadas en este run. Detalle: %s",
                msg,
            )
        else:
            logger.error("BadRequest Grok: %s", msg)
        base["error"] = "auth_or_bad_request"
        base["motivo_score"] = msg
        base["riesgos"] = ["Error de API Grok"]
        base["siguiente_paso"] = "Corregir API key / modelo y re-ejecutar"
        return base
    except APIError as e:
        logger.error("APIError Grok: %s", e)
        base["error"] = "api_error"
        base["motivo_score"] = str(e)
        return base
    except Exception as e:
        logger.exception("Error Grok inesperado: %s", e)
        base["error"] = "unknown"
        base["motivo_score"] = str(e)
        return base

    base.update(
        {
            "score": float(data.get("score") or 0),
            "resumen": data.get("resumen") or "",
            "requisitos": json.dumps(data.get("requisitos_principales") or [], ensure_ascii=False),
            "documentos": json.dumps(data.get("documentos_a_reunir") or [], ensure_ascii=False),
            "motivo_score": data.get("motivo_score"),
            "riesgos": data.get("riesgos") or [],
            "siguiente_paso": data.get("siguiente_paso") or "",
            "relevante": bool(data.get("relevante")),
            "raw_json": json.dumps(data, ensure_ascii=False),
        }
    )
    return base

def reset_auth_flag():
    """Llamar al inicio de cada run diario."""
    global _auth_failed
    _auth_failed = False