from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
from typing import Optional, List


class AccountCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    account_type: str = Field(..., pattern="^(Asset|Liability|Equity|Income|Expense)$")
    parent_account_id: Optional[int] = None
    description: Optional[str] = None
    is_bank_account: bool = False
    is_cash_account: bool = False
    is_credit_card: bool = False


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class JournalLineCreate(BaseModel):
    account_id: int
    debit: Decimal = Decimal('0')
    credit: Decimal = Decimal('0')
    description: Optional[str] = None


class JournalEntryCreate(BaseModel):
    date: date
    narration: str = Field(..., min_length=1, max_length=500)
    lines: List[JournalLineCreate]
    person_id: Optional[int] = None
    reference: Optional[str] = Field(default=None, min_length=1, max_length=50)


class JournalEntryReverseRequest(BaseModel):
    reversal_date: Optional[date] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class JournalEntryReverseLine(BaseModel):
    account_id: int
    debit: Decimal
    credit: Decimal


class JournalEntryReverseResponse(BaseModel):
    original_journal_entry_id: int
    reversal_journal_entry_id: int
    reversed: bool
    reversal_date: date
    amount: Decimal
    currency: str = "OMR"
    lines: List[JournalEntryReverseLine]


class TransferCreate(BaseModel):
    date: date
    from_account_id: int
    to_account_id: int
    amount: Decimal
    narration: Optional[str] = None
