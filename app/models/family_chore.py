"""Family chore and allowance tracking models (FAM-1304, FAM-1305).

Chores are tenant/family-scoped tasks that can be assigned to a family
member with an allowance amount. Completions are submitted by the
assigned member and approved/rejected by a head or parent. Approved
completions may optionally be paid — FAM-1305 adds payment-posting
columns to FamilyChoreCompletion so an approved allowance can be turned
into a balanced journal entry through AccountingService, with safe
reversal. Nothing here posts a journal entry directly; that only ever
happens through FamilyChoreService calling AccountingService.
"""

from datetime import datetime
from decimal import Decimal
import enum

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text,
    Date, Index,
)
from sqlalchemy.orm import relationship

from app.models.database import Base
from app.models.mixins import TimestampMixin, TenantMixin


class ChoreFrequency(str, enum.Enum):
    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ChoreStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ChoreCompletionStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class ChorePaymentStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    REVERSED = "reversed"


class FamilyChore(Base, TimestampMixin, TenantMixin):
    """A choreable task, optionally assigned to a family member with an allowance."""
    __tablename__ = "family_chores"

    id = Column(Integer, primary_key=True, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    assigned_to_member_id = Column(Integer, ForeignKey("family_members.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    allowance_amount = Column(Numeric(15, 3), default=Decimal("0"), nullable=False)
    currency = Column(String(3), default="OMR", nullable=False)
    frequency = Column(String(20), default=ChoreFrequency.ONE_TIME.value, nullable=False)
    due_date = Column(Date, nullable=True)
    status = Column(String(20), default=ChoreStatus.ACTIVE.value, nullable=False, index=True)
    requires_approval = Column(Boolean, default=True, nullable=False)

    # Relationships
    family = relationship("Family", foreign_keys=[family_id])
    assigned_to = relationship("FamilyMember", foreign_keys=[assigned_to_member_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    completions = relationship(
        "FamilyChoreCompletion", back_populates="chore",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_family_chores_tenant_status", "tenant_id", "status"),
        Index("ix_family_chores_tenant_assigned", "tenant_id", "assigned_to_member_id"),
        Index("ix_family_chores_tenant_due_date", "tenant_id", "due_date"),
    )


class FamilyChoreCompletion(Base, TimestampMixin, TenantMixin):
    """A single completion submission for a chore, subject to approval."""
    __tablename__ = "family_chore_completions"

    id = Column(Integer, primary_key=True, index=True)
    chore_id = Column(Integer, ForeignKey("family_chores.id"), nullable=False, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False, index=True)
    completed_by_member_id = Column(Integer, ForeignKey("family_members.id"), nullable=False, index=True)

    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_notes = Column(Text, nullable=True)
    status = Column(String(20), default=ChoreCompletionStatus.SUBMITTED.value, nullable=False, index=True)

    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    earned_amount = Column(Numeric(15, 3), default=Decimal("0"), nullable=False)

    # Payment posting (FAM-1305) — set only through FamilyChoreService calling
    # AccountingService; never mutated directly elsewhere.
    payment_status = Column(String(20), default=ChorePaymentStatus.UNPAID.value, nullable=False, index=True)
    payment_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    payment_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True, index=True)
    payment_reversal_journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True, index=True)
    paid_at = Column(DateTime, nullable=True)
    paid_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Relationships
    chore = relationship("FamilyChore", back_populates="completions")
    family = relationship("Family", foreign_keys=[family_id])
    completed_by = relationship("FamilyMember", foreign_keys=[completed_by_member_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    payment_account = relationship("Account", foreign_keys=[payment_account_id])
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    payment_journal_entry = relationship("JournalEntry", foreign_keys=[payment_journal_entry_id])
    payment_reversal_journal_entry = relationship(
        "JournalEntry", foreign_keys=[payment_reversal_journal_entry_id]
    )
    paid_by = relationship("User", foreign_keys=[paid_by_user_id])

    __table_args__ = (
        Index("ix_family_chore_completions_tenant_status", "tenant_id", "status"),
        Index("ix_family_chore_completions_tenant_member", "tenant_id", "completed_by_member_id"),
        Index("ix_family_chore_completions_tenant_payment_status", "tenant_id", "payment_status"),
    )
