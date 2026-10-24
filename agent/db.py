import sqlite3
from datetime import datetime, timezone
from agent.config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS procesos_analizados (
            proceso_id TEXT PRIMARY KEY,
            objeto TEXT,
            entidad TEXT,
            valor REAL,
            score REAL,
            resumen TEXT,
            requisitos TEXT,
            documentos TEXT,
            url TEXT,
            raw_json TEXT,
            analyzed_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            fetched INTEGER,
            analyzed INTEGER,
            relevant INTEGER,
            report_path TEXT
        )
        """)
        conn.commit()

def already_analyzed(proceso_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM procesos_analizados WHERE proceso_id = ?",
            (proceso_id,),
        ).fetchone()
        return row is not None

def save_analisis(item: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO procesos_analizados
            (proceso_id, objeto, entidad, valor, score, resumen, requisitos, documentos, url, raw_json, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["proceso_id"],
                item.get("objeto"),
                item.get("entidad"),
                item.get("valor"),
                item.get("score"),
                item.get("resumen"),
                item.get("requisitos"),
                item.get("documentos"),
                item.get("url"),
                item.get("raw_json"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()

def log_run(started_at, finished_at, fetched, analyzed, relevant, report_path):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO runs (started_at, finished_at, fetched, analyzed, relevant, report_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (started_at, finished_at, fetched, analyzed, relevant, report_path),
        )
        conn.commit()