from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, date
from decimal import Decimal

from app.models.database import get_db
from app.models import User, Organization, Account, JournalEntry, JournalLine, Goal, Loan, Budget, AIInsight, AIReport
from app.services.health_score_service import HealthScoreService
from app.services.ai_orchestrator import AIOrchestrator
from app.services.bill_subscription_service import CommitmentService
from app.schemas.bill_subscription import CommitmentSummary
from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Main dashboard page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    
    # Get financial summary
    health_service = HealthScoreService(db, tenant_id)
    health_score = await health_service.calculate_score() if tenant_id else None
    
    # Get latest AI insights
    latest_insights = []
    if tenant_id:
        result = await db.execute(
            select(AIInsight)
            .where(AIInsight.tenant_id == tenant_id)
            .where(AIInsight.is_dismissed == False)
            .order_by(AIInsight.created_at.desc())
            .limit(3)
        )
        latest_insights = result.scalars().all()
    
    # Get latest AI report
    latest_report = None
    if tenant_id:
        result = await db.execute(
            select(AIReport)
            .where(AIReport.tenant_id == tenant_id)
            .where(AIReport.report_type == "daily")
            .order_by(AIReport.created_at.desc())
            .limit(1)
        )
        latest_report = result.scalar_one_or_none()
    
    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "health_score": health_score,
        "latest_insights": latest_insights,
        "latest_report": latest_report,
        "currency": settings.CURRENCY_DEFAULT,
    })


@router.get("/api/summary")
async def dashboard_summary(request: Request, db: AsyncSession = Depends(get_db)):
    """API endpoint for dashboard summary data (used by HTMX)."""
    tenant_id = getattr(request.state, "tenant_id", None)
    
    if not tenant_id:
        return {"error": "Not authenticated"}
    
    # Calculate financial summary
    health_service = HealthScoreService(db, tenant_id)
    health_score = await health_service.calculate_score()
    
    # Get account balances
    result = await db.execute(
        select(Account).where(Account.tenant_id == tenant_id).where(Account.is_active == True)
    )
    accounts = result.scalars().all()
    
    total_assets = sum(
        float(a.current_balance) for a in accounts if a.account_type == "Asset"
    )
    total_liabilities = sum(
        float(a.current_balance) for a in accounts if a.account_type == "Liability"
    )
    net_worth = total_assets - total_liabilities
    
    return {
        "health_score": health_score,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
    }


@router.get("/api/commitments", response_model=CommitmentSummary)
async def dashboard_commitments(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return upcoming bills, overdue bills, and subscription renewal summary."""
    service = CommitmentService(db, tenant_id=user.organization_id)
    summary = await service.summary()
    return CommitmentSummary(**summary)
