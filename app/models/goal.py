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


class GoalVisibility(str, enum.Enum):
    """Visibility level for a family goal."""
    PRIVATE = "private"
    SHARED = "shared"
    FAMILY = "family"


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

    # Family ownership and visibility
    visibility = Column(
        String(20),
        default=GoalVisibility.PRIVATE.value,
        nullable=False,
        index=True,
    )
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=True, index=True)

    # AI-generated fields
    ai_probability = Column(Numeric(5, 2), nullable=True)  # % chance of reaching goal on time
    ai_recommendation = Column(Text, nullable=True)

    # Relationships
    contributions = relationship("GoalContribution", back_populates="goal", cascade="all, delete-orphan")
    owner = relationship("User", foreign_keys=[owner_user_id])
    family = relationship("Family", foreign_keys=[family_id])


class GoalContribution(Base, TimestampMixin, TenantMixin):
    """A contribution toward a goal."""
    __tablename__ = "goal_contributions"

    id = Column(Integer, primary_key=True, index=True)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False, index=True)
    amount = Column(Numeric(15, 3), nullable=False)
    date = Column(Date, default=datetime.utcnow, nullable=False)
    source = Column(String(50), default="manual", nullable=False)  # manual, automatic, transfer
    description = Column(Text, nullable=True)

    # Who made the contribution and optional account links
    contributed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)

    # Accounting posting fields for goal contributions (GOAL-1401A)
    source_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    destination_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True, index=True)
    posting_status = Column(String(20), default="progress_only", nullable=False)

    goal = relationship("Goal", back_populates="contributions")
    contributor = relationship("User", foreign_keys=[contributed_by_user_id])
    account = relationship("Account", foreign_keys=[account_id])
    source_account = relationship("Account", foreign_keys=[source_account_id])
    destination_account = relationship("Account", foreign_keys=[destination_account_id])
    journal_entry = relationship("JournalEntry", foreign_keys=[journal_entry_id])
