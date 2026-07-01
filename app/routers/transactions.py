from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import JournalEntry, JournalLine
from app.schemas.accounting import JournalEntryCreate, TransferCreate
from app.services.accounting_service import AccountingService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def transactions_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Transaction list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(JournalEntry)
        .where(JournalEntry.tenant_id == tenant_id)
        .order_by(JournalEntry.date.desc())
        .limit(50)
    )
    entries = result.scalars().all()
    
    return templates.TemplateResponse("transactions/list.html", {
        "request": request,
        "entries": entries,
    })


@router.post("/")
async def create_transaction(entry: JournalEntryCreate, db: AsyncSession = Depends(get_db)):
    """Create a new journal entry."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = AccountingService(db, tenant_id)
    new_entry = await service.create_journal_entry(entry)
    return new_entry


@router.post("/transfer")
async def create_transfer(transfer: TransferCreate, db: AsyncSession = Depends(get_db)):
    """Create a transfer between accounts (auto-balanced journal entry)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = AccountingService(db, tenant_id)
    entry = await service.create_transfer(transfer)
    return entry
