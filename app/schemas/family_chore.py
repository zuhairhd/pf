from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field


class ChoreCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    assigned_to_member_id: Optional[int] = None
    allowance_amount: Decimal = Field(Decimal("0"), ge=0)
    currency: str = Field("OMR", min_length=3, max_length=3)
    frequency: str = Field("one_time", pattern="^(one_time|daily|weekly|monthly)$")
    due_date: Optional[date] = None
    requires_approval: bool = True


class ChoreUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    assigned_to_member_id: Optional[int] = None
    allowance_amount: Optional[Decimal] = Field(None, ge=0)
    frequency: Optional[str] = Field(None, pattern="^(one_time|daily|weekly|monthly)$")
    due_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern="^(active|paused|completed|cancelled|archived)$")
    requires_approval: Optional[bool] = None


class ChoreResponse(BaseModel):
    id: int
    tenant_id: int
    family_id: int
    title: str
    description: Optional[str] = None
    assigned_to_member_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    allowance_amount: Decimal
    currency: str
    frequency: str
    due_date: Optional[date] = None
    status: str
    requires_approval: bool
    created_at: datetime
    updated_at: datetime
    can_view: bool = True
    can_manage: bool = False
    can_submit_completion: bool = False


class ChoreCompletionCreate(BaseModel):
    completed_at: Optional[datetime] = None
    submitted_notes: Optional[str] = None


class ChoreCompletionResponse(BaseModel):
    id: int
    tenant_id: int
    chore_id: int
    family_id: int
    completed_by_member_id: int
    completed_at: datetime
    submitted_notes: Optional[str] = None
    status: str
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    earned_amount: Decimal
    payment_status: str = "unpaid"
    payment_account_id: Optional[int] = None
    expense_account_id: Optional[int] = None
    payment_journal_entry_id: Optional[int] = None
    payment_reversal_journal_entry_id: Optional[int] = None
    paid_at: Optional[datetime] = None
    paid_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ChoreApprovalRequest(BaseModel):
    """Used for both approve and reject actions.

    earned_amount — optional override for approval; defaults to the
    chore's allowance_amount when omitted. Ignored on reject.
    rejection_reason — required (by the service) for reject; ignored on approve.
    """
    earned_amount: Optional[Decimal] = Field(None, ge=0)
    rejection_reason: Optional[str] = None


class AllowanceMemberBreakdown(BaseModel):
    member_id: int
    member_name: str
    pending_approval_amount: Decimal
    approved_earned_amount: Decimal
    approved_unpaid_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    reversed_amount: Decimal = Decimal("0")
    rejected_amount: Decimal


class AllowanceSummaryResponse(BaseModel):
    currency: str
    pending_approval_amount: Decimal
    approved_earned_amount: Decimal
    approved_unpaid_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    reversed_amount: Decimal = Decimal("0")
    rejected_amount: Decimal
    by_member: List[AllowanceMemberBreakdown]


# ---------------------------------------------------------------------------
# Allowance payment posting schemas (FAM-1305)
# ---------------------------------------------------------------------------


class ChorePaymentPostRequest(BaseModel):
    payment_account_id: int
    expense_account_id: int
    payment_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class ChorePaymentPostResponse(BaseModel):
    completion_id: int
    payment_status: str
    paid_at: Optional[datetime] = None
    payment_journal_entry_id: Optional[int] = None
    debit_account_id: int
    credit_account_id: int
    amount: Decimal
    currency: str


class ChorePaymentReverseResponse(BaseModel):
    completion_id: int
    payment_status: str
    payment_journal_entry_id: Optional[int] = None
    payment_reversal_journal_entry_id: Optional[int] = None
    reversed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Dashboard widget schemas (DB-1107A)
# ---------------------------------------------------------------------------


class DashboardChoreItem(BaseModel):
    id: int
    title: str
    assigned_to_member_id: Optional[int] = None
    assigned_to_name: Optional[str] = None
    allowance_amount: Decimal
    currency: str
    frequency: str
    due_date: Optional[date] = None
    status: str
    is_overdue: bool
    is_due_soon: bool
    can_submit: bool = False
    can_manage: bool = False


class DashboardCompletionItem(BaseModel):
    id: int
    chore_id: int
    chore_title: str
    completed_by_member_id: int
    completed_by_name: Optional[str] = None
    submitted_notes: Optional[str] = None
    status: str
    earned_amount: Decimal
    completed_at: datetime
    can_approve: bool = False
    can_reject: bool = False


class DashboardAccountOption(BaseModel):
    id: int
    code: str
    name: str


class DashboardReadyToPayItem(BaseModel):
    id: int
    chore_id: int
    chore_title: str
    member_id: int
    member_name: Optional[str] = None
    earned_amount: Decimal
    currency: str
    approved_at: Optional[datetime] = None
    can_pay: bool = False


class DashboardPaymentHistoryItem(BaseModel):
    id: int
    chore_title: str
    member_name: Optional[str] = None
    earned_amount: Decimal
    currency: str
    payment_status: str
    payment_journal_entry_id: Optional[int] = None
    payment_reversal_journal_entry_id: Optional[int] = None
    paid_at: Optional[datetime] = None
    can_reverse: bool = False


class DashboardAllowanceMemberBreakdown(BaseModel):
    member_id: int
    member_name: str
    pending_approval_amount: Decimal
    approved_earned_amount: Decimal
    approved_unpaid_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    reversed_amount: Decimal = Decimal("0")
    rejected_amount: Decimal


class DashboardAllowanceSummary(BaseModel):
    currency: str
    pending_approval_amount: Decimal
    approved_earned_amount: Decimal
    approved_this_month_amount: Decimal
    approved_unpaid_amount: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    reversed_amount: Decimal = Decimal("0")
    rejected_amount: Decimal
    by_member: List[DashboardAllowanceMemberBreakdown]


class FamilyChoresDashboardResponse(BaseModel):
    assigned_chores: List[DashboardChoreItem]
    overdue_chores: List[DashboardChoreItem]
    pending_approvals: List[DashboardCompletionItem]
    ready_to_pay: List[DashboardReadyToPayItem] = []
    recent_payments: List[DashboardPaymentHistoryItem] = []
    allowance_summary: DashboardAllowanceSummary
    due_soon_count: int
    overdue_count: int
    pending_approvals_count: int
    ready_to_pay_count: int = 0
    currency: str
    permissions: dict
