from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin


class UserActivity(Base, TimestampMixin):
    """User engagement tracking."""
    __tablename__ = "user_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    tenant_id = Column(Integer, nullable=False)
    activity_type = Column(String(100), nullable=False)  # login, page_view, transaction_create, etc.
    feature = Column(String(100), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)


class FeatureUsage(Base, TimestampMixin):
    """Feature usage analytics."""
    __tablename__ = "feature_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False)
    feature_name = Column(String(100), nullable=False)
    usage_count = Column(Integer, default=1, nullable=False)
    usage_date = Column(Date, nullable=False)


class AITokenUsage(Base, TimestampMixin):
    """AI API usage and cost tracking."""
    __tablename__ = "ai_token_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    model = Column(String(50), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    request_type = Column(String(50), nullable=False)  # chat, insight, report, forecast
