from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict


class GoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    goal_type: str = Field(..., pattern="^(emergency_fund|car|house|education|vacation|retirement|custom)$")
    target_amount: Decimal
    target_date: Optional[date] = None
    monthly_contribution: Decimal = Decimal('0')
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10)


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[Decimal] = None
    target_date: Optional[date] = None
    monthly_contribution: Optional[Decimal] = None
    priority: Optional[int] = None
    status: Optional[str] = None


class GoalContributionCreate(BaseModel):
    amount: Decimal
    date: date
    description: Optional[str] = None
    account_id: Optional[int] = None
    source_account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    post_to_accounting: bool = False


class FamilyGoalCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    goal_type: str = Field(..., pattern="^(emergency_fund|car|house|education|vacation|retirement|custom)$")
    target_amount: Decimal
    target_date: Optional[date] = None
    monthly_contribution: Decimal = Decimal('0')
    description: Optional[str] = None
    priority: int = Field(1, ge=1, le=10)
    visibility: str = Field(default="private", pattern="^(private|shared|family)$")


class FamilyGoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[Decimal] = None
    target_date: Optional[date] = None
    monthly_contribution: Optional[Decimal] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    visibility: Optional[str] = Field(default=None, pattern="^(private|shared|family)$")


class GoalContributionResponse(BaseModel):
    id: int
    goal_id: int
    tenant_id: int
    amount: Decimal
    date: date
    source: str
    description: Optional[str] = None
    contributed_by_user_id: Optional[int] = None
    account_id: Optional[int] = None
    source_account_id: Optional[int] = None
    destination_account_id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    posting_status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoalResponse(BaseModel):
    id: int
    tenant_id: int
    family_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    name: str
    goal_type: str
    status: str
    visibility: str
    target_amount: Decimal
    current_amount: Decimal
    target_date: Optional[date] = None
    monthly_contribution: Decimal
    description: Optional[str] = None
    priority: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoalProgressResponse(BaseModel):
    goal: GoalResponse
    target: float
    current: float
    remaining: float
    progress_percentage: float
    monthly_contribution: float
    months_to_completion: Optional[float]
    estimated_completion: Optional[date]
    contributions: List[GoalContributionResponse]
    is_on_track: bool

    model_config = {"from_attributes": True}


class DashboardFamilyGoalItem(BaseModel):
    id: int
    name: str
    visibility: str
    status: str
    target_amount: float
    current_amount: float
    remaining_amount: float
    progress_percent: float
    target_date: Optional[date] = None
    owner_user_id: Optional[int] = None
    family_id: Optional[int] = None
    can_view: bool
    can_manage: bool
    can_contribute: bool


class FamilyGoalsDashboardResponse(BaseModel):
    goals: List[DashboardFamilyGoalItem]
    active_goals_count: int
    completed_goals_count: int
    total_target_amount: float
    total_current_amount: float
    total_remaining_amount: float
    average_progress_percent: float
    currency: str
    permissions: Dict[str, bool]
