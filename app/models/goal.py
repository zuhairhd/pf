from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class GoalType(str, enum.Enum):
    EMERGENCY_FUND = "emergency_fund"
    CAR = "car"
    HOUSE = "house"
    EDUCATION = "education"
    VACATION = "vacation"
    RETIREMENT = "retirement"
    CUSTOM = "custom"


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class Goal(Base, TimestampMixin, TenantMixin):
    """A financial goal."""
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    goal_type = Column(SQLEnum(GoalType), default=GoalType.CUSTOM, nullable=False)
    status = Column(SQLEnum(GoalStatus), default=GoalStatus.ACTIVE, nullable=False)
    target_amount = Column(Numeric(15, 3), nullable=False)
    current_amount = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    target_date = Column(Date, nullable=True)
    monthly_contribution = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=1, nullable=False)  # 1 = highest
    
    # AI-generated fields
    ai_probability = Column(Numeric(5, 2), nullable=True)  # % chance of reaching goal on time
    ai_recommendation = Column(Text, nullable=True)
    
    # Relationships
    contributions = relationship("GoalContribution", back_populates="goal", cascade="all, delete-orphan")


class GoalContribution(Base, TimestampMixin):
    """A contribution toward a goal."""
    __tablename__ = "goal_contributions"
    
    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False)
    amount = Column(Numeric(15, 3), nullable=False)
    date = Column(Date, default=datetime.utcnow, nullable=False)
    source = Column(String(50), default="manual", nullable=False)  # manual, automatic, transfer
    description = Column(Text, nullable=True)
    
    goal = relationship("Goal", back_populates="contributions")
