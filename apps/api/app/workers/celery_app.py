from datetime import timedelta

from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "jobpilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_time_limit=1200,
    task_soft_time_limit=1170,
    beat_schedule={
        "discover-jobs": {
            "task": "app.workers.tasks.scheduled_discovery",
            "schedule": timedelta(hours=settings.discovery_interval_hours),
        }
    }
    if settings.discovery_schedule_enabled
    else {},
)
