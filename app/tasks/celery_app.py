from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pf_ai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.recurring_transactions",
        "app.tasks.ai_daily_brief",
        "app.tasks.ai_weekly_report",
        "app.tasks.ai_monthly_report",
        "app.tasks.notifications",
        "app.tasks.subscription_detection",
        "app.tasks.anomaly_detection",
        "app.tasks.document_ocr",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    worker_prefetch_multiplier=1,
)
