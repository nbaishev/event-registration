from celery import Celery

from app.common.config import get_settings

celery_app = Celery(
    "notifications",
    broker=get_settings().redis_url,
    include=["app.notifications.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    beat_schedule={
        "confirmation-scan": {
            "task": "notifications.scan_confirmation",
            "schedule": 300.0,
        },
    },
    timezone="UTC",
    broker_connection_retry_on_startup=True,
)
