from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.core.security import get_db_with_tenant_context
from app.models import Account, JournalEntry, JournalLine
from app.schemas.accounting import AccountCreate, AccountUpdate, JournalEntryCreate
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
