from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List


class BudgetCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    account_id: Optional[int] = None
    budgeted_amount: Decimal = Field(..., ge=0)
    alert_threshold: Decimal = Field(Decimal('80'), ge=0, le=1000)


class BudgetCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    account_id: Optional[int] = None
    budgeted_amount: Optional[Decimal] = Field(None, ge=0)
    alert_threshold: Optional[Decimal] = Field(None, ge=0, le=1000)


class BudgetCategoryResponse(BaseModel):
    id: int
    budget_id: int
    name: str
    account_id: Optional[int] = None
    account_name: Optional[str] = None
    budgeted_amount: Decimal
    actual_amount: Decimal
    remaining_amount: Decimal
    percent_used: Decimal
    alert_threshold: Decimal
    is_over_budget: bool
    is_near_limit: bool


class BudgetCreate(BaseModel):
    """Legacy/simple budget creation payload (used by the plain /budgets router)."""
    name: str = Field(..., min_length=1, max_length=200)
    period: str = Field("monthly", pattern="^(monthly|quarterly|yearly)$")
    start_date: date
    end_date: date
    categories: List[BudgetCategoryCreate] = []


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class FamilyBudgetCreate(BaseModel):
    """Family-aware budget creation payload with visibility support."""
    name: str = Field(..., min_length=1, max_length=200)
    period: str = Field("monthly", pattern="^(monthly|quarterly|yearly)$")
    start_date: date
    end_date: date
    currency: str = Field("OMR", min_length=3, max_length=3)
    visibility: str = Field("private", pattern="^(private|shared|family)$")
    categories: List[BudgetCategoryCreate] = []


class FamilyBudgetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    visibility: Optional[str] = Field(None, pattern="^(private|shared|family)$")
    status: Optional[str] = Field(None, pattern="^(active|archived|closed)$")


class FamilyBudgetResponse(BaseModel):
    id: int
    tenant_id: int
    family_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    name: str
    period: str
    start_date: date
    end_date: date
    currency: str
    visibility: str
    status: str
    is_active: bool
    total_budgeted: Decimal
    total_actual: Decimal
    created_at: datetime
    updated_at: datetime
    can_view: bool = True
    can_manage: bool = False


class BudgetSummaryResponse(BaseModel):
    budget: FamilyBudgetResponse
    categories: List[BudgetCategoryResponse]
    total_planned: Decimal
    total_actual: Decimal
    total_remaining: Decimal
    percent_used: Decimal
    currency: str
    over_budget_category_ids: List[int]
    near_limit_category_ids: List[int]


class FamilyBudgetsListResponse(BaseModel):
    budgets: List[FamilyBudgetResponse]


class ActiveFamilyBudgetsSummary(BaseModel):
    """Lightweight summary for future dashboard use (DB-1106A)."""
    active_budgets_count: int
    total_planned: Decimal
    total_actual: Decimal
    over_budget_count: int
    near_limit_count: int
    currency: str
