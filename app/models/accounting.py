from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from decimal import Decimal

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class Account(Base, TimestampMixin, TenantMixin):
    """Chart of accounts entry."""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    account_type = Column(String(50), nullable=False)  # Asset, Liability, Equity, Income, Expense
    parent_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_bank_account = Column(Boolean, default=False, nullable=False)
    is_cash_account = Column(Boolean, default=False, nullable=False)
    is_credit_card = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    parent = relationship("Account", remote_side="Account.id", backref="children")
    journal_lines = relationship("JournalLine", back_populates="account")
    
    __table_args__ = (
        # Unique constraint on code per tenant
        {"sqlite_autoincrement": True},
    )


class JournalEntry(Base, TimestampMixin, TenantMixin):
    """A journal entry (double-entry transaction)."""
    __tablename__ = "journal_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    reference = Column(String(50), unique=True, nullable=False)
    narration = Column(Text, nullable=False)
    person_id = Column(Integer, nullable=True)
    source = Column(String(50), default="manual", nullable=False)  # manual, import, recurring, bank_feed
    is_reconciled = Column(Boolean, default=False, nullable=False)
    reversed_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    reversal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    reversed_at = Column(DateTime, nullable=True)
    reversal_reason = Column(Text, nullable=True)
    
    # Relationships
    lines = relationship("JournalLine", back_populates="entry", cascade="all, delete-orphan", order_by="JournalLine.id")
    reversed_entry = relationship(
        "JournalEntry",
        foreign_keys=[reversed_entry_id],
        remote_side=[id],
        post_update=True,
    )
    reversal_entry = relationship(
        "JournalEntry",
        foreign_keys=[reversal_entry_id],
        remote_side=[id],
        post_update=True,
    )


class JournalLine(Base, TimestampMixin, TenantMixin):
    """A single debit or credit line in a journal entry."""
    __tablename__ = "journal_lines"
    
    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    debit = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    credit = Column(Numeric(15, 3), default=Decimal('0'), nullable=False)
    description = Column(String(500), nullable=True)
    
    # Relationships
    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")


class RecurringTransaction(Base, TimestampMixin, TenantMixin):
    """A recurring transaction template."""
    __tablename__ = "recurring_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    frequency = Column(String(20), nullable=False)  # daily, weekly, monthly, yearly
    next_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    amount = Column(Numeric(15, 3), nullable=False)
    debit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    credit_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    narration = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_generated_at = Column(DateTime, nullable=True)
