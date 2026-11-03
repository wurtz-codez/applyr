from celery import Celery

from app.config import get_settings

settings = get_settings()
celery = Celery("applyr", broker=settings.redis_url, include=["app.workers.tasks"])
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=570,
    task_time_limit=600,
    broker_connection_timeout=2,
    task_publish_retry=False,
    task_routes={
        "ingestion.run": {"queue": "ingestion"},
        "ingestion.browser": {"queue": "browser"},
        "ingestion.schedule": {"queue": "ingestion"},
        "ingestion.freshness": {"queue": "ingestion"},
        "ingestion.maintenance": {"queue": "ingestion"},
        "matching.refresh": {"queue": "ingestion"},
    },
    beat_schedule={
        "due-sources": {"task": "ingestion.schedule", "schedule": 60.0},
        "catalog-maintenance": {"task": "ingestion.maintenance", "schedule": 60.0},
        "profile-matching": {
            "task": "matching.refresh",
            "schedule": 60.0,
            "options": {"queue": "ingestion"},
        },
    },
)
