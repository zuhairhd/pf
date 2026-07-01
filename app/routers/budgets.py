from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models import Budget, BudgetCategory
from app.schemas.budget import BudgetCreate, BudgetUpdate
from app.services.budget_service import BudgetService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def budgets_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Budgets list page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    result = await db.execute(
        select(Budget).where(Budget.tenant_id == tenant_id).where(Budget.is_active == True)
    )
    budgets = result.scalars().all()
    
    return templates.TemplateResponse("budgets/list.html", {
        "request": request,
        "budgets": budgets,
    })


@router.post("/")
async def create_budget(budget: BudgetCreate, db: AsyncSession = Depends(get_db)):
    """Create a new budget."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")
    
    service = BudgetService(db, tenant_id)
    new_budget = await service.create_budget(budget)
    return new_budget
