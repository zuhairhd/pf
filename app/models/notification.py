from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class NotificationType(str, enum.Enum):
    BUDGET_ALERT = "budget_alert"
    GOAL_MILESTONE = "goal_milestone"
    BILL_DUE = "bill_due"
    AI_INSIGHT = "ai_insight"
    AI_RECOMMENDATION = "ai_recommendation"
    ANOMALY_DETECTED = "anomaly_detected"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    SYSTEM = "system"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"


class Notification(Base, TimestampMixin, TenantMixin):
    """An in-app notification."""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime, nullable=True)
    
    # AI-generated
    ai_confidence = Column(Numeric(5, 2), nullable=True)
    ai_action_url = Column(String(500), nullable=True)


class NotificationSetting(Base, TimestampMixin):
    """Per-user notification preferences."""
    __tablename__ = "notification_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    in_app = Column(Boolean, default=True, nullable=False)
    email = Column(Boolean, default=True, nullable=False)
    push = Column(Boolean, default=False, nullable=False)
    sms = Column(Boolean, default=False, nullable=False)
    quiet_hours_start = Column(String(5), nullable=True)  # HH:MM
    quiet_hours_end = Column(String(5), nullable=True)
