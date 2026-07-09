from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from app.models.database import get_db
from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import Account, JournalEntry, JournalLine
from app.models import User
from app.schemas.accounting import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountVisibilityUpdate,
    AccountOwnerUpdate,
    JournalEntryCreate,
    JournalEntryReverseLine,
    JournalEntryReverseRequest,
    JournalEntryReverseResponse,
)
from app.services.accounting_service import AccountingService
from app.services.family_account_access_service import FamilyAccountAccessService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _to_response(account: Account) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        tenant_id=account.tenant_id,
        code=account.code,
        name=account.name,
        account_type=account.account_type,
        parent_account_id=account.parent_account_id,
        description=account.description,
        is_active=account.is_active,
        is_bank_account=account.is_bank_account,
        is_cash_account=account.is_cash_account,
        is_credit_card=account.is_credit_card,
        visibility=account.visibility,
        owner_user_id=account.owner_user_id,
        family_id=account.family_id,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/", response_class=HTMLResponse)
async def accounts_list(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Chart of accounts page, filtered by family visibility rules."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    accounts = await access.list_visible_accounts()

    return templates.TemplateResponse("accounts/list.html", {
        "request": request,
        "accounts": accounts,
    })


@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create a new account."""
    service = AccountingService(db, user.organization_id)
    new_account = await service.create_account(account)
    return _to_response(new_account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Get a single account if the user is allowed to view it."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == user.organization_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not await access.can_view_account(account):
        raise HTTPException(status_code=403, detail="Access denied")
    return _to_response(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Update basic account fields the user is allowed to manage."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == user.organization_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not await access.can_manage_account(account):
        raise HTTPException(status_code=403, detail="Access denied")

    data = payload.model_dump(exclude_unset=True)
    for field in ("name", "description", "is_active"):
        if field in data:
            setattr(account, field, data[field])
    await db.commit()
    await db.refresh(account)
    return _to_response(account)


@router.patch("/{account_id}/visibility", response_model=AccountResponse)
async def update_account_visibility(
    account_id: int,
    payload: AccountVisibilityUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Change account visibility (private/shared/family)."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == user.organization_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not await access.can_manage_account(account):
        raise HTTPException(status_code=403, detail="Access denied")

    account.visibility = payload.visibility
    await db.commit()
    await db.refresh(account)
    return _to_response(account)


@router.patch("/{account_id}/owner", response_model=AccountResponse)
async def update_account_owner(
    account_id: int,
    payload: AccountOwnerUpdate,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Assign or remove an account owner."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    result = await db.execute(
        select(Account).where(Account.id == account_id, Account.tenant_id == user.organization_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if not await access.can_manage_account(account):
        raise HTTPException(status_code=403, detail="Access denied")

    account.owner_user_id = payload.owner_user_id
    await db.commit()
    await db.refresh(account)
    return _to_response(account)


@router.post(
    "/journal-entries/{journal_entry_id}/reverse",
    response_model=JournalEntryReverseResponse,
)
async def reverse_journal_entry(
    journal_entry_id: int,
    payload: JournalEntryReverseRequest | None = None,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Create an idempotent reversing journal entry for the current tenant."""
    service = AccountingService(db, user.organization_id)
    try:
        reversal = await service.reverse_journal_entry(
            journal_entry_id,
            reversal_date=payload.reversal_date if payload else None,
            reason=payload.reason if payload else None,
            created_by=user.id,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Journal entry not found" else 400
        raise HTTPException(status_code=status_code, detail=detail)

    lines = [
        JournalEntryReverseLine(
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
        )
        for line in reversal.lines
    ]
    amount = sum((line.debit for line in reversal.lines), start=Decimal("0"))
    return JournalEntryReverseResponse(
        original_journal_entry_id=journal_entry_id,
        reversal_journal_entry_id=reversal.id,
        reversed=True,
        reversal_date=reversal.date,
        amount=amount,
        lines=lines,
    )
