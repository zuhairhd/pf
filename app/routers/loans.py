from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import Loan, LoanPayment
from app.schemas.loan import LoanCreate, LoanUpdate, LoanPaymentCreate
from app.services.loan_service import LoanService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def loans_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Loans list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Loan).where(Loan.tenant_id == tenant_id).where(Loan.is_active == True)
    )
    loans = result.scalars().all()
    
    return templates.TemplateResponse("loans/list.html", {
        "request": request,
        "loans": loans,
    })


@router.post("/")
async def create_loan(loan: LoanCreate, db: AsyncSession = Depends(get_db)):
    """Create a new loan."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = LoanService(db, tenant_id)
    new_loan = await service.create_loan(loan)
    return new_loan


@router.get("/{loan_id}/schedule")
async def get_repayment_schedule(loan_id: int, db: AsyncSession = Depends(get_db)):
    """Get repayment schedule for a loan."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = LoanService(db, tenant_id)
    schedule = await service.generate_schedule(loan_id)
    return schedule


@router.post("/{loan_id}/payments")
async def add_payment(loan_id: int, payment: LoanPaymentCreate, db: AsyncSession = Depends(get_db)):
    """Add a payment to a loan."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = LoanService(db, tenant_id)
    new_payment = await service.add_payment(loan_id, payment)
    return new_payment
