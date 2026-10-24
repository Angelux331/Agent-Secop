import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from agent.config import LOGS_DIR, TIMEZONE
from agent.scheduler_job import run_daily_job

def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "agent.log"
    handlers = [
        RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )

def main():
    setup_logging()
    logger = logging.getLogger("main")
    tz = pytz.timezone(TIMEZONE)

    # Primera corrida al arrancar (opcional pero útil)
    logger.info("Corrida inicial…")
    try:
        path = run_daily_job()
        logger.info("OK: %s", path)
    except Exception:
        logger.exception("Fallo en corrida inicial")

    scheduler = BlockingScheduler(timezone=tz)
    # Todos los días laborables a las 07:00 hora Colombia
    scheduler.add_job(
        run_daily_job,
        CronTrigger(day_of_week="mon-fri", hour=7, minute=0, timezone=tz),
        id="secop_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    logger.info("Scheduler activo: lun-vie 07:00 %s", TIMEZONE)
    scheduler.start()

if __name__ == "__main__":
    main()