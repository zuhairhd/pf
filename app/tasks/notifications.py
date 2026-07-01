from app.tasks.celery_app import celery_app
from app.models.database import async_session
from datetime import datetime


@celery_app.task
async def send_scheduled_notifications():
    """Send scheduled notifications."""
    async with async_session() as db:
        from app.models import Notification
        from sqlalchemy import select
        
        # Get unsent notifications
        result = await db.execute(
            select(Notification)
            .where(Notification.is_read == False)
            .order_by(Notification.created_at.desc())
        )
        notifications = result.scalars().all()
        
        # TODO: Implement actual notification sending (email, push, SMS)
        # For now, just mark them as processed
        for notification in notifications:
            # Send logic here
            pass
