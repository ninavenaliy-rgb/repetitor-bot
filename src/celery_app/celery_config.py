"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from config.settings import settings

celery_app = Celery(
    "repetitor",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.celery_app.tasks.reminder_tasks",
        "src.celery_app.tasks.engagement_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "scan-upcoming-bookings": {
            "task": "src.celery_app.tasks.reminder_tasks.scan_upcoming_bookings",
            "schedule": crontab(minute="*/5"),
        },
        "send-daily-engagement": {
            "task": "src.celery_app.tasks.engagement_tasks.send_daily_word",
            "schedule": crontab(hour=9, minute=0),
        },
        "check-streaks": {
            "task": "src.celery_app.tasks.engagement_tasks.check_streaks",
            "schedule": crontab(hour=21, minute=0),
        },
    },
)
