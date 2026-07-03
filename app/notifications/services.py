"""Notification delivery service with bill/subscription reminders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.config import get_settings
from app.models import (
    Bill,
    Notification,
    NotificationChannel,
    NotificationSetting,
    NotificationStatus,
    NotificationType,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.notifications.channels.email import send_email, EmailResult
from app.services.notification_service import NotificationService as BaseNotificationService


settings = get_settings()


class NotificationDeliveryService:
    """Orchestrates in-app and email notifications, including reminders."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.base = BaseNotificationService(db, tenant_id)

    # ------------------------------------------------------------------
    # Core notification lifecycle
    # ------------------------------------------------------------------

    async def create_notification(
        self,
        user_id: int,
        *,
        notification_type: NotificationType,
        title: str,
        message: str,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[int] = None,
        scheduled_for: Optional[datetime] = None,
    ) -> Notification:
        """Create a notification record."""
        notification = Notification(
            tenant_id=self.tenant_id,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            channel=channel,
            status=NotificationStatus.PENDING,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            scheduled_for=scheduled_for,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def list_notifications(
        self,
        user_id: int,
        *,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Notification]:
        """List notifications for a user in the current tenant."""
        query = (
            select(Notification)
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
        )
        if unread_only:
            query = query.where(Notification.is_read == False)
        query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_notification(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """Get a single notification scoped to user and tenant."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.id == notification_id)
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def mark_read(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """Mark a notification as read."""
        notification = await self.get_notification(notification_id, user_id)
        if notification is None:
            return None
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        if notification.status != NotificationStatus.READ:
            notification.status = NotificationStatus.READ
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_unread(self, notification_id: int, user_id: int) -> Optional[Notification]:
        """Mark a notification as unread."""
        notification = await self.get_notification(notification_id, user_id)
        if notification is None:
            return None
        notification.is_read = False
        notification.read_at = None
        notification.status = NotificationStatus.PENDING
        await self.db.commit()
        await self.db.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: int) -> int:
        """Mark all user notifications as read. Returns count updated."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
            .where(Notification.is_read == False)
        )
        notifications = result.scalars().all()
        now = datetime.utcnow()
        for notification in notifications:
            notification.is_read = True
            notification.read_at = now
            notification.status = NotificationStatus.READ
        await self.db.commit()
        return len(notifications)

    async def unread_count(self, user_id: int) -> int:
        """Return the number of unread notifications for a user."""
        result = await self.db.execute(
            select(func.count(Notification.id))
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
            .where(Notification.is_read == False)
        )
        return result.scalar() or 0

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    async def get_preferences(self, user_id: int) -> List[NotificationSetting]:
        """Return notification settings for a user."""
        result = await self.db.execute(
            select(NotificationSetting).where(NotificationSetting.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update_preference(
        self,
        user_id: int,
        notification_type: NotificationType,
        *,
        in_app: Optional[bool] = None,
        email: Optional[bool] = None,
        push: Optional[bool] = None,
        sms: Optional[bool] = None,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
    ) -> NotificationSetting:
        """Update or create a notification preference."""
        result = await self.db.execute(
            select(NotificationSetting)
            .where(NotificationSetting.user_id == user_id)
            .where(NotificationSetting.notification_type == notification_type)
        )
        setting = result.scalar_one_or_none()

        data = {
            "in_app": in_app,
            "email": email,
            "push": push,
            "sms": sms,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
        }
        data = {k: v for k, v in data.items() if v is not None}

        if setting:
            for field, value in data.items():
                setattr(setting, field, value)
        else:
            defaults = {
                "in_app": True,
                "email": True,
                "push": False,
                "sms": False,
            }
            defaults.update(data)
            setting = NotificationSetting(
                user_id=user_id,
                notification_type=notification_type,
                **defaults,
            )
            self.db.add(setting)

        await self.db.commit()
        await self.db.refresh(setting)
        return setting

    # ------------------------------------------------------------------
    # Email delivery
    # ------------------------------------------------------------------

    async def send_email_notification(self, notification: Notification) -> EmailResult:
        """Attempt to send a notification by email and update its status."""
        if notification.channel != NotificationChannel.EMAIL:
            return EmailResult(
                success=False, backend="none", error="Notification is not an email notification"
            )

        if not settings.NOTIFICATIONS_ENABLED:
            notification.status = NotificationStatus.SKIPPED
            notification.error_message = "Notifications disabled globally"
            await self.db.commit()
            return EmailResult(success=False, backend="disabled", error="Notifications disabled globally")

        # Respect user preference
        should_send_email = await self.base.should_send(
            notification.user_id, notification.notification_type.value, "email"
        )
        if not should_send_email:
            notification.status = NotificationStatus.SKIPPED
            notification.error_message = "User email preference disabled"
            await self.db.commit()
            return EmailResult(success=False, backend="preference", error="User email preference disabled")

        result = await send_email(
            to_email=notification.user.email,
            subject=notification.title,
            body_text=notification.message,
        )

        notification.sent_at = datetime.utcnow() if result.success else None
        notification.status = NotificationStatus.SENT if result.success else NotificationStatus.FAILED
        notification.error_message = result.error
        await self.db.commit()
        return result

    async def send_pending_email_notifications(self, limit: int = 100) -> dict:
        """Send pending email notifications. Used by Celery/script."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.channel == NotificationChannel.EMAIL)
            .where(Notification.status == NotificationStatus.PENDING)
            .where(
                (Notification.scheduled_for == None) | (Notification.scheduled_for <= datetime.utcnow())
            )
            .limit(limit)
        )
        notifications = result.scalars().all()

        sent = 0
        failed = 0
        skipped = 0
        for notification in notifications:
            res = await self.send_email_notification(notification)
            if res.success:
                sent += 1
            elif notification.status == NotificationStatus.SKIPPED:
                skipped += 1
            else:
                failed += 1

        return {"sent": sent, "failed": failed, "skipped": skipped}

    # ------------------------------------------------------------------
    # Reminder generation
    # ------------------------------------------------------------------

    async def _existing_reminder_today(
        self,
        user_id: int,
        notification_type: NotificationType,
        related_entity_type: str,
        related_entity_id: int,
    ) -> bool:
        """Check whether a reminder already exists for the same entity today."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        result = await self.db.execute(
            select(func.count(Notification.id))
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
            .where(Notification.notification_type == notification_type)
            .where(Notification.related_entity_type == related_entity_type)
            .where(Notification.related_entity_id == related_entity_id)
            .where(Notification.created_at >= today_start)
            .where(Notification.created_at < today_end)
        )
        return (result.scalar() or 0) > 0

    async def generate_bill_reminders(
        self,
        user: User,
        reminder_days: int = settings.BILL_REMINDER_DAYS_DEFAULT,
    ) -> dict:
        """Create bill due and overdue reminders for the tenant."""
        today = date.today()
        reminder_cutoff = today + timedelta(days=reminder_days)

        created = 0
        skipped = 0

        # Upcoming bills
        result = await self.db.execute(
            select(Bill)
            .where(Bill.tenant_id == self.tenant_id)
            .where(Bill.is_active == True)
            .where(Bill.is_paid == False)
            .where(Bill.due_date >= today)
            .where(Bill.due_date <= reminder_cutoff)
        )
        bills = result.scalars().all()

        for bill in bills:
            if await self._existing_reminder_today(
                user.id, NotificationType.BILL_DUE, "bill", bill.id
            ):
                skipped += 1
                continue
            await self.create_notification(
                user_id=user.id,
                notification_type=NotificationType.BILL_DUE,
                title=f"Bill due soon: {bill.name}",
                message=self._bill_reminder_message(bill, overdue=False),
                channel=NotificationChannel.IN_APP,
                related_entity_type="bill",
                related_entity_id=bill.id,
            )
            created += 1

        # Overdue bills
        result = await self.db.execute(
            select(Bill)
            .where(Bill.tenant_id == self.tenant_id)
            .where(Bill.is_active == True)
            .where(Bill.is_paid == False)
            .where(Bill.due_date < today)
        )
        overdue_bills = result.scalars().all()

        for bill in overdue_bills:
            if await self._existing_reminder_today(
                user.id, NotificationType.BILL_OVERDUE, "bill", bill.id
            ):
                skipped += 1
                continue
            await self.create_notification(
                user_id=user.id,
                notification_type=NotificationType.BILL_OVERDUE,
                title=f"Bill overdue: {bill.name}",
                message=self._bill_reminder_message(bill, overdue=True),
                channel=NotificationChannel.IN_APP,
                related_entity_type="bill",
                related_entity_id=bill.id,
            )
            created += 1

        return {"created": created, "skipped": skipped}

    async def generate_subscription_reminders(
        self,
        user: User,
        reminder_days: int = settings.SUBSCRIPTION_REMINDER_DAYS_DEFAULT,
    ) -> dict:
        """Create subscription renewal reminders for the tenant."""
        today = date.today()
        reminder_cutoff = today + timedelta(days=reminder_days)

        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == self.tenant_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .where(Subscription.next_billing_date >= today)
            .where(Subscription.next_billing_date <= reminder_cutoff)
        )
        subscriptions = result.scalars().all()

        created = 0
        skipped = 0
        for sub in subscriptions:
            if await self._existing_reminder_today(
                user.id, NotificationType.SUBSCRIPTION_RENEWAL, "subscription", sub.id
            ):
                skipped += 1
                continue
            await self.create_notification(
                user_id=user.id,
                notification_type=NotificationType.SUBSCRIPTION_RENEWAL,
                title=f"Subscription renewal: {sub.name}",
                message=self._subscription_reminder_message(sub),
                channel=NotificationChannel.IN_APP,
                related_entity_type="subscription",
                related_entity_id=sub.id,
            )
            created += 1

        return {"created": created, "skipped": skipped}

    async def generate_reminders(self, user: User) -> dict:
        """Generate all bill and subscription reminders for a user/tenant."""
        bill_result = await self.generate_bill_reminders(user)
        sub_result = await self.generate_subscription_reminders(user)
        return {
            "bills": bill_result,
            "subscriptions": sub_result,
            "total_created": bill_result["created"] + sub_result["created"],
            "total_skipped": bill_result["skipped"] + sub_result["skipped"],
        }

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    @staticmethod
    def _bill_reminder_message(bill: Bill, overdue: bool) -> str:
        status = "is overdue" if overdue else "is due soon"
        due = bill.due_date.isoformat()
        amount = f"{bill.typical_amount:.3f}"
        return (
            f"Your bill '{bill.name}' from {bill.provider} {status}.\n"
            f"Due date: {due}\n"
            f"Typical amount: {amount}\n"
            f"Please review and make payment if needed."
        )

    @staticmethod
    def _subscription_reminder_message(subscription: Subscription) -> str:
        renewal = subscription.next_billing_date.isoformat()
        amount = f"{subscription.amount:.3f}"
        return (
            f"Your subscription '{subscription.name}' from {subscription.provider} "
            f"will renew on {renewal}.\n"
            f"Amount: {amount}\n"
            f"Frequency: {subscription.frequency}"
        )

    @staticmethod
    def test_email_body() -> str:
        return (
            "This is a test email from PF AI Personal Finance.\n"
            "If you received this, your email notification channel is configured correctly."
        )
