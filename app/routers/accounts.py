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
    JournalEntryCreate,
    JournalEntryReverseLine,
    JournalEntryReverseRequest,
    JournalEntryReverseResponse,
)
from app.services.accounting_service import AccountingService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def accounts_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Chart of accounts page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Account).where(Account.tenant_id == tenant_id).order_by(Account.code)
    )
    accounts = result.scalars().all()
    
    return templates.TemplateResponse("accounts/list.html", {
        "request": request,
        "accounts": accounts,
    })


@router.post("/")
async def create_account(
    account: AccountCreate,
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Create a new account."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    service = AccountingService(db, tenant_id)
    new_account = await service.create_account(account)
    return new_account


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
