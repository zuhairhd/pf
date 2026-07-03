"""Pydantic schemas for bills and subscriptions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

class BillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., min_length=1, max_length=200)
    typical_amount: Decimal = Field(..., gt=Decimal('0'))
    due_date: date
    frequency: str = Field(default="monthly", pattern="^(one-time|weekly|monthly|quarterly|yearly)$")
    is_auto_pay: bool = False
    payment_method: Optional[str] = Field(default=None, max_length=100)


class BillUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=200)
    typical_amount: Optional[Decimal] = Field(default=None, gt=Decimal('0'))
    due_date: Optional[date] = None
    frequency: Optional[str] = Field(default=None, pattern="^(one-time|weekly|monthly|quarterly|yearly)$")
    is_auto_pay: Optional[bool] = None
    payment_method: Optional[str] = Field(default=None, max_length=100)


class BillResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    provider: str
    typical_amount: Decimal
    due_date: date
    frequency: str
    is_auto_pay: bool
    payment_method: Optional[str] = None
    is_paid: bool
    paid_at: Optional[datetime] = None
    status: str  # computed: upcoming | paid | overdue | cancelled
    ai_predicted_amount: Optional[Decimal] = None
    ai_trend: Optional[str] = None
    ai_alert: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class SubscriptionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., min_length=1, max_length=200)
    amount: Decimal = Field(..., gt=Decimal('0'))
    frequency: str = Field(default="monthly", pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    next_billing_date: date
    category: Optional[str] = Field(default=None, max_length=100)
    account_id: Optional[int] = None


class SubscriptionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[Decimal] = Field(default=None, gt=Decimal('0'))
    frequency: Optional[str] = Field(default=None, pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    next_billing_date: Optional[date] = None
    category: Optional[str] = Field(default=None, max_length=100)
    account_id: Optional[int] = None


class SubscriptionResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    provider: str
    amount: Decimal
    frequency: str
    next_billing_date: date
    category: Optional[str] = None
    status: str  # active | paused | cancelled
    is_active: bool
    account_id: Optional[int] = None
    days_until_renewal: Optional[int] = None
    monthly_equivalent_amount: Decimal
    yearly_equivalent_amount: Decimal
    ai_detected: bool
    ai_recommendation: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Dashboard commitments
# ---------------------------------------------------------------------------

class CommitmentSummary(BaseModel):
    upcoming_bills_count: int
    upcoming_bills_total: Decimal
    overdue_bills_count: int
    overdue_bills_total: Decimal
    upcoming_renewals_count: int
    upcoming_renewals_total: Decimal
    monthly_subscription_total: Decimal
    total_fixed_commitments_this_month: Decimal
    upcoming_bills: List[BillResponse] = []
    overdue_bills: List[BillResponse] = []
    upcoming_renewals: List[SubscriptionResponse] = []
    currency: str = "OMR"
