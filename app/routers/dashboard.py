"""Dashboard routes and HTMX partials."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.security import get_db_with_tenant_context, require_tenant_member, require_tenant_admin
from app.models import User, UserRole
from app.models.database import get_db
from app.models import Organization, Account, JournalEntry, JournalLine, Goal, Loan, Budget, AIInsight, AIReport
from app.notifications import NotificationDeliveryService
from app.schemas.bill_subscription import BillResponse, SubscriptionResponse, CommitmentSummary
from app.services.bill_subscription_service import BillService, CommitmentService, SubscriptionService
from app.services.health_score_service import HealthScoreService
from app.services.ai_orchestrator import AIOrchestrator

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _bill_status(bill) -> str:
    if not bill.is_active:
        return "cancelled"
    if bill.is_paid:
        return "paid"
    if bill.due_date < date.today():
        return "overdue"
    return "upcoming"


def _serialize_bill(bill) -> dict:
    return BillResponse(
        id=bill.id,
        tenant_id=bill.tenant_id,
        name=bill.name,
        provider=bill.provider,
        typical_amount=bill.typical_amount,
        due_date=bill.due_date,
        frequency=bill.frequency,
        is_auto_pay=bill.is_auto_pay,
        payment_method=bill.payment_method,
        is_paid=bill.is_paid,
        paid_at=bill.paid_at,
        status=_bill_status(bill),
        ai_predicted_amount=bill.ai_predicted_amount,
        ai_trend=bill.ai_trend,
        ai_alert=bill.ai_alert,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    ).model_dump()


def _serialize_subscription(subscription) -> dict:
    return SubscriptionResponse(
        id=subscription.id,
        tenant_id=subscription.tenant_id,
        name=subscription.name,
        provider=subscription.provider,
        amount=subscription.amount,
        frequency=subscription.frequency,
        next_billing_date=subscription.next_billing_date,
        category=subscription.category,
        status=subscription.status,
        is_active=subscription.is_active,
        account_id=subscription.account_id,
        days_until_renewal=SubscriptionService.days_until_renewal(subscription),
        monthly_equivalent_amount=SubscriptionService.monthly_equivalent(subscription),
        yearly_equivalent_amount=SubscriptionService.yearly_equivalent(subscription),
        ai_detected=subscription.ai_detected,
        ai_recommendation=subscription.ai_recommendation,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    ).model_dump()


async def _build_commitments(db: AsyncSession, tenant_id: int) -> dict:
    """Load commitment summary plus serialized bill/subscription lists."""
    service = CommitmentService(db, tenant_id=tenant_id)
    summary = await service.summary()

    upcoming = await service.upcoming_bills(7)
    overdue = await service.overdue_bills()
    renewals = await service.upcoming_renewals(30)

    return {
        **summary,
        "upcoming_bills": [_serialize_bill(b) for b in upcoming],
        "overdue_bills": [_serialize_bill(b) for b in overdue],
        "upcoming_renewals": [_serialize_subscription(s) for s in renewals],
        "currency": settings.CURRENCY_DEFAULT,
    }


def _is_admin(user: User) -> bool:
    return user.role in (UserRole.OWNER, UserRole.ADMIN)


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Main dashboard page."""
    tenant_id = user.organization_id

    # Get financial summary
    try:
        health_service = HealthScoreService(db, tenant_id)
        health_score = await health_service.calculate_score()
    except Exception:
        health_score = None

    # Get latest AI insights
    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.tenant_id == tenant_id)
        .where(AIInsight.is_dismissed == False)
        .order_by(AIInsight.created_at.desc())
        .limit(3)
    )
    latest_insights = result.scalars().all()

    # Get latest AI report
    result = await db.execute(
        select(AIReport)
        .where(AIReport.tenant_id == tenant_id)
        .where(AIReport.report_type == "daily")
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )
    latest_report = result.scalar_one_or_none()

    commitments = await _build_commitments(db, tenant_id)

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "user": user,
            "health_score": health_score,
            "latest_insights": latest_insights,
            "latest_report": latest_report,
            "currency": settings.CURRENCY_DEFAULT,
            "commitments": commitments,
            "is_admin": _is_admin(user),
        },
    )


@router.get("/api/summary")
async def dashboard_summary(request: Request, db: AsyncSession = Depends(get_db)):
    """API endpoint for dashboard summary data (used by HTMX)."""
    tenant_id = getattr(request.state, "tenant_id", None)

    if not tenant_id:
        return {"error": "Not authenticated"}

    try:
        # Calculate financial summary
        health_service = HealthScoreService(db, tenant_id)
        health_score = await health_service.calculate_score()
    except Exception:
        health_score = None

    try:
        # Get account balances
        result = await db.execute(
            select(Account).where(Account.tenant_id == tenant_id).where(Account.is_active == True)
        )
        accounts = result.scalars().all()

        total_assets = sum(
            float(getattr(a, "current_balance", 0)) for a in accounts if a.account_type == "Asset"
        )
        total_liabilities = sum(
            float(getattr(a, "current_balance", 0)) for a in accounts if a.account_type == "Liability"
        )
        net_worth = total_assets - total_liabilities
    except Exception:
        total_assets = 0
        total_liabilities = 0
        net_worth = 0

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
    commitments = await _build_commitments(db, user.organization_id)
    return CommitmentSummary(**commitments)


@router.get("/partials/commitments", response_class=HTMLResponse)
async def commitments_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial for the commitments widget."""
    commitments = await _build_commitments(db, user.organization_id)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/commitments_widget.html",
        {
            "commitments": commitments,
            "currency": settings.CURRENCY_DEFAULT,
            "is_admin": _is_admin(user),
        },
    )


@router.post("/partials/bills/{bill_id}/mark-paid", response_class=HTMLResponse)
async def mark_bill_paid_partial(
    bill_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a bill as paid from the dashboard and return refreshed widget."""
    bill_service = BillService(db, tenant_id=user.organization_id)
    bill = await bill_service.get(bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    await bill_service.mark_paid(bill)
    commitments = await _build_commitments(db, user.organization_id)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/commitments_widget.html",
        {
            "commitments": commitments,
            "currency": settings.CURRENCY_DEFAULT,
            "is_admin": _is_admin(user),
        },
    )


@router.post("/partials/run-reminders", response_class=HTMLResponse)
async def run_reminders_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_admin),
):
    """Run bill/subscription reminders from the dashboard and return refreshed widget."""
    service = NotificationDeliveryService(db, tenant_id=user.organization_id)
    await service.generate_reminders(user)
    commitments = await _build_commitments(db, user.organization_id)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/commitments_widget.html",
        {
            "commitments": commitments,
            "currency": settings.CURRENCY_DEFAULT,
            "is_admin": _is_admin(user),
        },
    )
