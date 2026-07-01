from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from typing import Optional


class LoanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lender: str = Field(..., min_length=1, max_length=200)
    loan_type: str = Field(..., pattern="^(personal|credit_card|mortgage|auto|student|family|other)$")
    original_principal: Decimal
    current_balance: Decimal
    interest_rate: Decimal  # Annual rate as decimal, e.g., 0.0525 for 5.25%
    term_months: Optional[int] = None
    start_date: date
    minimum_payment: Optional[Decimal] = None
    repayment_strategy: str = Field("avalanche", pattern="^(snowball|avalanche|custom)$")
    extra_payment: Decimal = Decimal('0')
    account_id: Optional[int] = None


class LoanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    lender: Optional[str] = Field(None, min_length=1, max_length=200)
    loan_type: Optional[str] = Field(None, pattern="^(personal|credit_card|mortgage|auto|student|family|other)$")
    current_balance: Optional[Decimal] = None
    interest_rate: Optional[Decimal] = None
    term_months: Optional[int] = None
    minimum_payment: Optional[Decimal] = None
    repayment_strategy: Optional[str] = Field(None, pattern="^(snowball|avalanche|custom)$")
    extra_payment: Optional[Decimal] = None
    account_id: Optional[int] = None
    is_active: Optional[bool] = None


class LoanPaymentCreate(BaseModel):
    payment_date: date
    total_payment: Decimal
    principal_paid: Decimal
    interest_paid: Decimal
    remaining_balance: Decimal
