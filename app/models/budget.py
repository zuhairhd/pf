from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date, Enum as SQLEnum
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
    
    # Relationships
    categories = relationship("BudgetCategory", back_populates="budget", cascade="all, delete-orphan")


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
