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


@celery_app.task
async def send_due_reminders_task(tenant_id: int):
    """Generate bill and subscription reminders for a tenant.

    This is a Celery task stub. The actual reminder logic is implemented in
    app.notifications.services.NotificationDeliveryService.
    """
    async with async_session() as db:
        from sqlalchemy import select
        from app.models import User
        from app.notifications import NotificationDeliveryService

        result = await db.execute(
            select(User)
            .where(User.organization_id == tenant_id)
            .order_by(User.id)
            .limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return {"error": "No user found for tenant", "tenant_id": tenant_id}

        service = NotificationDeliveryService(db, tenant_id=tenant_id)
        reminder_result = await service.generate_reminders(user)
        return reminder_result


@celery_app.task
async def send_pending_notifications_task(tenant_id: int, limit: int = 100):
    """Send pending email notifications for a tenant.

    This is a Celery task stub. The actual delivery logic is implemented in
    app.notifications.services.NotificationDeliveryService.
    """
    async with async_session() as db:
        from app.notifications import NotificationDeliveryService

        service = NotificationDeliveryService(db, tenant_id=tenant_id)
        result = await service.send_pending_email_notifications(limit=limit)
        return result


@celery_app.task
async def run_proactive_alerts_task(tenant_id: int):
    """Run proactive alert generation for a tenant.

    This is a Celery task stub. The actual alert logic is implemented in
    app.ai_cfo.engines.proactive_alerts.ProactiveAlertsEngine. In a production
    deployment this task would be scheduled to run daily.
    """
    async with async_session() as db:
        from sqlalchemy import select
        from app.models import User
        from app.ai_cfo.engines.proactive_alerts import ProactiveAlertsEngine

        result = await db.execute(
            select(User)
            .where(User.organization_id == tenant_id)
            .where(User.is_active.is_(True))
            .order_by(User.id)
            .limit(1)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return {"error": "No active user found for tenant", "tenant_id": tenant_id}

        engine = ProactiveAlertsEngine(db, tenant_id, user=user)
        alert_result = await engine.run()
        return alert_result
