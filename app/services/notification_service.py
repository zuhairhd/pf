from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional

from app.models import Notification, NotificationSetting
from app.schemas.notification import NotificationCreate, NotificationSettingUpdate


class NotificationService:
    """Multi-channel notification delivery service."""
    
    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
    
    async def create_notification(self, user_id: int, notification_data: NotificationCreate) -> Notification:
        """Create a new notification."""
        notification = Notification(
            tenant_id=self.tenant_id,
            user_id=user_id,
            notification_type=notification_data.notification_type,
            title=notification_data.title,
            message=notification_data.message,
            ai_confidence=notification_data.ai_confidence,
            ai_action_url=notification_data.ai_action_url,
        )
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)
        return notification
    
    async def mark_as_read(self, notification_id: int) -> None:
        """Mark a notification as read."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.id == notification_id)
            .where(Notification.tenant_id == self.tenant_id)
        )
        notification = result.scalar_one_or_none()
        if notification:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            await self.db.commit()
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        result = await self.db.execute(
            select(Notification)
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == user_id)
            .where(Notification.is_read == False)
        )
        return len(result.scalars().all())
    
    async def update_settings(self, user_id: int, settings_data: NotificationSettingUpdate) -> None:
        """Update notification settings for a user."""
        # Find or create setting
        result = await self.db.execute(
            select(NotificationSetting)
            .where(NotificationSetting.user_id == user_id)
            .where(NotificationSetting.notification_type == settings_data.notification_type)
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            for field, value in settings_data.dict(exclude_unset=True).items():
                setattr(setting, field, value)
        else:
            setting = NotificationSetting(
                user_id=user_id,
                **settings_data.dict(exclude_unset=True)
            )
            self.db.add(setting)
        
        await self.db.commit()
    
    async def should_send(self, user_id: int, notification_type: str, channel: str) -> bool:
        """Check if a notification should be sent to a user via a specific channel."""
        result = await self.db.execute(
            select(NotificationSetting)
            .where(NotificationSetting.user_id == user_id)
            .where(NotificationSetting.notification_type == notification_type)
        )
        setting = result.scalar_one_or_none()
        
        if not setting:
            return True  # Default to sending
        
        return getattr(setting, channel, True)
