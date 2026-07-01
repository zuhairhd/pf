from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from typing import Optional, List


class BudgetCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    account_id: Optional[int] = None
    budgeted_amount: Decimal
    alert_threshold: Decimal = Decimal('80')


class BudgetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    period: str = Field(..., pattern="^(monthly|quarterly|yearly)$")
    start_date: date
    end_date: date
    categories: List[BudgetCategoryCreate]


class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
