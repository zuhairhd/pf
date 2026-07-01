from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class Subscription(Base, TimestampMixin, TenantMixin):
    """A recurring subscription (Netflix, gym, etc.)."""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    provider = Column(String(200), nullable=False)
    amount = Column(Numeric(15, 3), nullable=False)
    frequency = Column(String(20), default="monthly", nullable=False)  # daily, weekly, monthly, yearly
    next_billing_date = Column(Date, nullable=False)
    category = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # AI-detected fields
    ai_detected = Column(Boolean, default=False, nullable=False)
    last_used_date = Column(Date, nullable=True)
    usage_score = Column(Numeric(5, 2), nullable=True)  # AI-calculated 0-100
    ai_recommendation = Column(Text, nullable=True)
    
    # Linked transaction pattern
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)


class Bill(Base, TimestampMixin, TenantMixin):
    """A predictable bill with due date."""
    __tablename__ = "bills"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    provider = Column(String(200), nullable=False)
    typical_amount = Column(Numeric(15, 3), nullable=False)
    due_date = Column(Date, nullable=False)
    frequency = Column(String(20), default="monthly", nullable=False)
    is_auto_pay = Column(Boolean, default=False, nullable=False)
    payment_method = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # AI fields
    ai_predicted_amount = Column(Numeric(15, 3), nullable=True)
    ai_trend = Column(String(20), nullable=True)  # increasing, decreasing, stable
    ai_alert = Column(Text, nullable=True)
