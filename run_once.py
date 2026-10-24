import logging
import sys

from agent.scheduler_job import run_daily_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

if __name__ == "__main__":
    path = run_daily_job()
    print(f"\nReporte: {path}")