from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class AIInsightType(str, enum.Enum):
    CASH_FLOW = "cash_flow"
    EXPENSE = "expense"
    INCOME = "income"
    DEBT = "debt"
    BUDGET = "budget"
    SAVINGS = "savings"
    EMERGENCY_FUND = "emergency_fund"
    INVESTMENT = "investment"
    RETIREMENT = "retirement"
    GOAL = "goal"
    RISK = "risk"
    SUBSCRIPTION = "subscription"
    GENERAL = "general"


class AIInsightPriority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AIInsight(Base, TimestampMixin, TenantMixin):
    """A pre-computed AI insight."""
    __tablename__ = "ai_insights"
    
    id = Column(Integer, primary_key=True, index=True)
    insight_type = Column(SQLEnum(AIInsightType), nullable=False)
    priority = Column(SQLEnum(AIInsightPriority), default=AIInsightPriority.MEDIUM, nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    confidence = Column(Numeric(5, 2), nullable=False)  # 0-100
    
    # Structured data
    data_json = Column(Text, nullable=True)  # JSON with structured data
    actions_json = Column(Text, nullable=True)  # JSON array of recommended actions
    
    # Display
    is_dismissed = Column(Boolean, default=False, nullable=False)
    dismissed_at = Column(DateTime, nullable=True)
    is_featured = Column(Boolean, default=False, nullable=False)  # Show on dashboard


class AIReport(Base, TimestampMixin, TenantMixin):
    """A generated AI report (daily, weekly, monthly)."""
    __tablename__ = "ai_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(20), nullable=False)  # daily, weekly, monthly
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    health_score = Column(Integer, nullable=True)  # 0-100
    
    # Metrics
    metrics_json = Column(Text, nullable=True)  # JSON with score breakdowns
    recommendations_json = Column(Text, nullable=True)  # JSON array
    
    # Delivery
    is_emailed = Column(Boolean, default=False, nullable=False)
    emailed_at = Column(DateTime, nullable=True)


class AIChatSession(Base, TimestampMixin, TenantMixin):
    """A chat session with the AI."""
    __tablename__ = "ai_chat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=True)  # Auto-generated from first message
    
    # Relationships
    messages = relationship("AIChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="AIChatMessage.created_at")


class AIChatMessage(Base, TimestampMixin):
    """A single message in an AI chat session."""
    __tablename__ = "ai_chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("ai_chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # AI metadata
    tokens_used = Column(Integer, nullable=True)
    cost = Column(Numeric(10, 6), nullable=True)  # Estimated cost in USD
    model = Column(String(50), nullable=True)
    
    session = relationship("AIChatSession", back_populates="messages")
