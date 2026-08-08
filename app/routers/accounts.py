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
from app.models.family import FamilyRole
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
    OpeningBalancePostResponse,
    OpeningBalanceStatusResponse,
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
        opening_balance=account.opening_balance,
        opening_balance_date=account.opening_balance_date,
        opening_balance_journal_entry_id=account.opening_balance_journal_entry_id,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def _require_accounting_admin(db: AsyncSession, user: User) -> None:
    """Only HEAD/PARENT (or a tenant OWNER/ADMIN with no family record, which
    FamilyAccountAccessService.get_role() already resolves to HEAD) may
    manage tenant-wide accounting setup actions like opening balances --
    matching the exact elevated-role gate FAM-1305/GOAL-1401B already use for
    posting/reversing financial entries."""
    access = FamilyAccountAccessService(db, user.organization_id, user)
    role = await access.get_role()
    if role not in (FamilyRole.HEAD, FamilyRole.PARENT):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage accounting setup",
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
    if (
        ("opening_balance" in data or "opening_balance_date" in data)
        and account.opening_balance_journal_entry_id is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Opening balance has already been posted and cannot be changed",
        )

    for field in ("name", "description", "is_active", "opening_balance", "opening_balance_date"):
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


@router.get("/opening-balances/status", response_model=OpeningBalanceStatusResponse)
async def get_opening_balances_status(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Preview opening balance posting status without posting anything.

    Read-only: never creates or modifies a journal entry, account, or any
    other record.
    """
    await _require_accounting_admin(db, user)
    service = AccountingService(db, user.organization_id)
    status = await service.get_opening_balance_status()
    return OpeningBalanceStatusResponse(**status)


@router.post("/opening-balances/post", response_model=OpeningBalancePostResponse)
async def post_opening_balances(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Post configured opening balances into real, idempotent journal entries.

    Reuses AccountingService.post_opening_balances() unchanged, which itself
    only ever creates entries through create_journal_entry() -- never a
    direct insert. Safe to call repeatedly: already-posted accounts are
    reported, never re-posted or duplicated.
    """
    await _require_accounting_admin(db, user)
    service = AccountingService(db, user.organization_id)
    result = await service.post_opening_balances(posted_by=user.id)
    return OpeningBalancePostResponse(**result)


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
