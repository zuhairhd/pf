from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from typing import Optional


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
