import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv
from pathlib import Path

# Load env from root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6373/0") # Default local port if not set

app = Celery(
    "studio_admin",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["engine.tasks"]
)

# Optional configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=1, # Respect CloudNode CPU/RAM limits
    task_time_limit=1800, # 30 minutes max for one production
    beat_schedule={
        "sunday-analytics-audit": {
            "task": "engine.tasks.growth_analytics_task",
            "schedule": crontab(minute=0, hour=3, day_of_week="sun"),
            "args": ("fr",), # On commence par la branche FR
        },
    }
)

if __name__ == "__main__":
    app.start()
