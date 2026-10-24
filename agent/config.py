import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

for d in (DATA_DIR, REPORTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.reto.pltk.mx/v1").strip().rstrip("/")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-2-mini").strip()

SECOP_DOMAIN = os.getenv("SECOP_DOMAIN", "www.datos.gov.co")
SECOP_DATASET_ID = os.getenv("SECOP_DATASET_ID", "p6dx-8zbt")
SECOP_APP_TOKEN = os.getenv("SECOP_APP_TOKEN", "")
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "48"))
MAX_PROCESOS_IA = int(os.getenv("MAX_PROCESOS_IA", "25"))
TOP_N_REPORTE = int(os.getenv("TOP_N_REPORTE", "15"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "6"))
TIMEZONE = os.getenv("TIMEZONE", "America/Bogota")
DB_PATH = DATA_DIR / "agente_secop.db"
EMPRESA_PATH = CONFIG_DIR / "empresa.json"

def load_empresa() -> dict:
    with open(EMPRESA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)