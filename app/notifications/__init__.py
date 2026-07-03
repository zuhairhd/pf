"""Notification infrastructure: channels, delivery service, and reminder logic."""

from app.notifications.channels.email import send_email, EmailResult
from app.notifications.services import NotificationDeliveryService

__all__ = ["send_email", "EmailResult", "NotificationDeliveryService"]
