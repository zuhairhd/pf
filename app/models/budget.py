from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class BudgetPeriod(str, enum.Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class BudgetVisibility(str, enum.Enum):
    """Visibility level for a family budget."""
    PRIVATE = "private"
    SHARED = "shared"
    FAMILY = "family"


class BudgetStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class Budget(Base, TimestampMixin, TenantMixin):
    """A budget for a specific period."""
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    period = Column(SQLEnum(BudgetPeriod), default=BudgetPeriod.MONTHLY, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_budgeted = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    total_actual = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    currency = Column(String(3), default="OMR", nullable=False)

    # Family ownership and visibility (FAM-1303)
    visibility = Column(
        String(20),
        default=BudgetVisibility.PRIVATE.value,
        nullable=False,
        index=True,
    )
    status = Column(
        String(20),
        default=BudgetStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Relationships
    categories = relationship(
        "BudgetCategory", back_populates="budget", cascade="all, delete-orphan", lazy="selectin"
    )
    owner = relationship("User", foreign_keys=[owner_user_id])
    family = relationship("Family", foreign_keys=[family_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_budgets_tenant_period", "tenant_id", "start_date", "end_date"),
    )


class BudgetCategory(Base, TimestampMixin):
    """A category within a budget."""
    __tablename__ = "budget_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("budgets.id"), nullable=False)
    name = Column(String(200), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # Link to expense account
    budgeted_amount = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    actual_amount = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    alert_threshold = Column(Numeric(5, 2), default=Decimal('80'), nullable=False)  # Alert at %
    
    budget = relationship("Budget", back_populates="categories")


class BudgetAlert(Base, TimestampMixin, TenantMixin):
    """Budget overspending alerts."""
    __tablename__ = "budget_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("budgets.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("budget_categories.id"), nullable=True)
    alert_type = Column(String(50), nullable=False)  # threshold_exceeded, budget_depleted
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
