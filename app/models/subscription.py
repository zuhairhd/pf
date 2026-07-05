from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal
import enum

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


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
    status = Column(String(20), default=SubscriptionStatus.ACTIVE.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)  # legacy alias; kept for queries

    # AI-detected fields
    ai_detected = Column(Boolean, default=False, nullable=False)
    last_used_date = Column(Date, nullable=True)
    usage_score = Column(Numeric(5, 2), nullable=True)  # AI-calculated 0-100
    ai_recommendation = Column(Text, nullable=True)

    # Linked transaction pattern
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    # Payment posting
    payment_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    payment_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    payment_reversal_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    payment_account = relationship("Account", foreign_keys=[payment_account_id])
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    payment_journal_entry = relationship("JournalEntry", foreign_keys=[payment_journal_entry_id])
    payment_reversal_journal_entry = relationship(
        "JournalEntry", foreign_keys=[payment_reversal_journal_entry_id]
    )


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

    # Payment tracking
    is_paid = Column(Boolean, default=False, nullable=False)
    paid_at = Column(DateTime, nullable=True)

    # Payment posting
    payment_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    payment_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    payment_reversal_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    payment_account = relationship("Account", foreign_keys=[payment_account_id])
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    payment_journal_entry = relationship("JournalEntry", foreign_keys=[payment_journal_entry_id])
    payment_reversal_journal_entry = relationship(
        "JournalEntry", foreign_keys=[payment_reversal_journal_entry_id]
    )

    # AI fields
    ai_predicted_amount = Column(Numeric(15, 3), nullable=True)
    ai_trend = Column(String(20), nullable=True)  # increasing, decreasing, stable
    ai_alert = Column(Text, nullable=True)
