from pydantic import BaseModel, Field
from datetime import date, datetime
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
    visibility: Optional[str] = Field(default="private", pattern="^(private|shared|family)$")
    owner_user_id: Optional[int] = None
    family_id: Optional[int] = None
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    visibility: Optional[str] = Field(default=None, pattern="^(private|shared|family)$")
    owner_user_id: Optional[int] = None
    family_id: Optional[int] = None
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None


class AccountVisibilityUpdate(BaseModel):
    visibility: str = Field(..., pattern="^(private|shared|family)$")


class AccountOwnerUpdate(BaseModel):
    owner_user_id: Optional[int] = None


class AccountResponse(BaseModel):
    id: int
    tenant_id: int
    code: str
    name: str
    account_type: str
    parent_account_id: Optional[int] = None
    description: Optional[str] = None
    is_active: bool
    is_bank_account: bool
    is_cash_account: bool
    is_credit_card: bool
    visibility: str
    owner_user_id: Optional[int] = None
    family_id: Optional[int] = None
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None
    opening_balance_journal_entry_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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


class OpeningBalanceAccountResult(BaseModel):
    """Per-account outcome of an opening balance status check or posting run."""

    account_id: int
    code: str
    name: str
    account_type: str
    status: str  # pending | posted | already_posted | skipped_zero | skipped_no_balance | skipped_offset_account
    amount: Optional[Decimal] = None
    journal_entry_id: Optional[int] = None


class OpeningBalanceStatusResponse(BaseModel):
    accounts_considered: int
    accounts_pending: int
    accounts_already_posted: int
    accounts_skipped: int
    opening_balance_equity_account_id: Optional[int] = None
    results: List[OpeningBalanceAccountResult]


class OpeningBalancePostResponse(BaseModel):
    accounts_considered: int
    accounts_posted: int
    accounts_already_posted: int
    accounts_skipped: int
    opening_balance_equity_account_id: Optional[int] = None
    total_debit: Decimal
    total_credit: Decimal
    results: List[OpeningBalanceAccountResult]
