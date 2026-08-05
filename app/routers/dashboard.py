"""Dashboard routes and HTMX partials."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.security import get_db_with_tenant_context, require_tenant_member, require_tenant_admin
from app.models import User, UserRole
from app.models.family import FamilyRole, FamilyMember
from app.models.database import get_db
from app.models import Organization, Account, JournalEntry, JournalLine, Goal, Loan, Budget, AIReport
from app.notifications import NotificationDeliveryService
from app.models.budget import BudgetStatus
from app.models.family_chore import ChoreCompletionStatus, ChorePaymentStatus, ChoreStatus
from app.schemas.bill_subscription import BillResponse, SubscriptionResponse, CommitmentSummary
from app.schemas.budget import (
    DashboardBudgetCategoryItem,
    DashboardBudgetItem,
    FamilyBudgetsDashboardResponse,
)
from app.schemas.dashboard import DashboardToday
from app.schemas.goal import (
    DashboardFamilyGoalItem,
    DashboardGoalContributionItem,
    FamilyGoalsDashboardResponse,
    GoalContributionCreate,
)
from app.schemas.family_chore import (
    ChoreCompletionCreate,
    DashboardAccountOption,
    DashboardAllowanceMemberBreakdown,
    DashboardAllowanceSummary,
    DashboardChoreItem,
    DashboardCompletionItem,
    DashboardPaymentHistoryItem,
    DashboardReadyToPayItem,
    FamilyChoresDashboardResponse,
)
from app.services.bill_subscription_service import BillService, CommitmentService, SubscriptionService
from app.services.dashboard_ai_service import DashboardAIService
from app.services.family_account_access_service import FamilyAccountAccessService
from app.services.family_budget_service import FamilyBudgetService, FamilyBudgetServiceError
from app.services.family_chore_service import FamilyChoreService, FamilyChoreServiceError
from app.services.family_goal_service import FamilyGoalService, FamilyGoalServiceError
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
        payment_account_id=bill.payment_account_id,
        expense_account_id=bill.expense_account_id,
        payment_journal_entry_id=bill.payment_journal_entry_id,
        payment_reversal_journal_entry_id=bill.payment_reversal_journal_entry_id,
        journal_entry_id=bill.payment_journal_entry_id,
        reversal_journal_entry_id=bill.payment_reversal_journal_entry_id,
        debit_account_id=bill.expense_account_id,
        credit_account_id=bill.payment_account_id,
        payment_amount=bill.typical_amount if bill.payment_journal_entry_id else None,
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
        payment_account_id=subscription.payment_account_id,
        expense_account_id=subscription.expense_account_id,
        payment_journal_entry_id=subscription.payment_journal_entry_id,
        payment_reversal_journal_entry_id=subscription.payment_reversal_journal_entry_id,
        journal_entry_id=subscription.payment_journal_entry_id,
        reversal_journal_entry_id=subscription.payment_reversal_journal_entry_id,
        debit_account_id=subscription.expense_account_id,
        credit_account_id=subscription.payment_account_id,
        payment_amount=subscription.amount if subscription.payment_journal_entry_id else None,
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
    family_goals = await _build_family_goals_dashboard(db, user)

    try:
        family_budgets = await _build_family_budgets_dashboard(db, user)
    except Exception:
        family_budgets = None

    try:
        family_chores = await _build_family_chores_dashboard(db, user)
    except Exception:
        family_chores = None

    try:
        ai_service = DashboardAIService(db, tenant_id, user)
        ai_today = await ai_service.build_today()
    except Exception:
        ai_today = None

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "user": user,
            "health_score": health_score,
            "latest_report": latest_report,
            "currency": settings.CURRENCY_DEFAULT,
            "commitments": commitments,
            "family_goals": family_goals,
            "family_budgets": family_budgets,
            "family_chores": family_chores,
            "ai_today": ai_today,
            "today": date.today().isoformat(),
            "is_admin": _is_admin(user),
        },
    )


@router.get("/api/today", response_model=DashboardToday)
async def dashboard_today_api(
    include_narrative: bool = False,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return the AI-centric "Today" dashboard payload as UI-ready JSON.

    Read-only: composes existing read-only AI CFO engines/services and
    never creates, updates, or deletes financial records.
    """
    ai_service = DashboardAIService(db, user.organization_id, user)
    today = await ai_service.build_today(include_narrative=include_narrative)
    return DashboardToday(**today)


@router.get("/partials/ai-today", response_class=HTMLResponse)
async def ai_today_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial to refresh the AI "Today" brief without a full page reload."""
    try:
        ai_service = DashboardAIService(db, user.organization_id, user)
        ai_today = await ai_service.build_today()
    except Exception:
        ai_today = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/ai_today.html",
        {
            "ai_today": ai_today,
            "currency": settings.CURRENCY_DEFAULT,
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
    payment_error = None
    status_code = 200
    try:
        await bill_service.mark_paid(bill, user=user)
    except ValueError as exc:
        payment_error = str(exc)
        status_code = 400
    commitments = await _build_commitments(db, user.organization_id)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/commitments_widget.html",
        {
            "commitments": commitments,
            "currency": settings.CURRENCY_DEFAULT,
            "is_admin": _is_admin(user),
            "payment_error": payment_error,
        },
        status_code=status_code,
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


# ---------------------------------------------------------------------------
# Family Goals Dashboard Widget
# ---------------------------------------------------------------------------


_DASHBOARD_RECENT_CONTRIBUTIONS_LIMIT = 5


async def _dashboard_contributor_names(db: AsyncSession, user_ids: set[int]) -> dict[int, str]:
    """Batch-resolve contributor display names for the dashboard contribution history."""
    if not user_ids:
        return {}
    result = await db.execute(select(User).where(User.id.in_(user_ids)))
    return {
        u.id: f"{u.first_name} {u.last_name}".strip() or u.email
        for u in result.scalars().all()
    }


async def _build_family_goals_dashboard(
    db: AsyncSession,
    user: User,
) -> dict:
    """Load family goals visible to the user and compute dashboard summary.

    Includes a small, permission-aware recent-contributions list per goal
    (GOAL-1401B/DB-1105B) -- read-only, reuses FamilyGoalService.list_contributions()
    unchanged. A contribution's `can_reverse` flag is only true when the current
    user can manage the goal and the contribution is an unreversed posted entry
    with a journal_entry_id -- the same eligibility FamilyGoalService.reverse_contribution()
    itself enforces server-side, so the button is never shown for something the
    backend would reject anyway.
    """
    goal_service = FamilyGoalService(db, tenant_id=user.organization_id, user=user)
    visible_goals = await goal_service.list_visible_goals()

    goals = []
    active_count = 0
    completed_count = 0
    total_target = 0.0
    total_current = 0.0

    for goal in visible_goals:
        target = float(goal.target_amount)
        current = float(goal.current_amount)
        remaining = max(target - current, 0.0)
        progress = (current / target * 100) if target > 0 else 0.0

        if goal.status == "active":
            active_count += 1
            total_target += target
            total_current += current
        elif goal.status == "completed":
            completed_count += 1

        can_manage = await goal_service.can_manage_goal(goal)

        contributions = await goal_service.list_contributions(goal.id)
        recent = contributions[:_DASHBOARD_RECENT_CONTRIBUTIONS_LIMIT]
        names = await _dashboard_contributor_names(
            db, {c.contributed_by_user_id for c in recent if c.contributed_by_user_id}
        )
        recent_contributions = [
            DashboardGoalContributionItem(
                id=c.id,
                goal_id=goal.id,
                goal_name=goal.name,
                amount=float(c.amount),
                date=c.date,
                contributed_by_name=names.get(c.contributed_by_user_id),
                posting_status=c.posting_status,
                journal_entry_id=c.journal_entry_id,
                reversal_journal_entry_id=c.reversal_journal_entry_id,
                can_reverse=(
                    can_manage
                    and c.journal_entry_id is not None
                    and c.reversal_journal_entry_id is None
                    and c.posting_status == "posted"
                    and c.amount > 0
                ),
            )
            for c in recent
        ]

        goals.append(
            DashboardFamilyGoalItem(
                id=goal.id,
                name=goal.name,
                visibility=goal.visibility,
                status=goal.status.value if hasattr(goal.status, "value") else goal.status,
                target_amount=target,
                current_amount=current,
                remaining_amount=remaining,
                progress_percent=round(progress, 1),
                target_date=goal.target_date,
                owner_user_id=goal.owner_user_id,
                family_id=goal.family_id,
                can_view=True,
                can_manage=can_manage,
                can_contribute=await goal_service.can_contribute_to_goal(goal),
                recent_contributions=recent_contributions,
            )
        )

    total_remaining = max(total_target - total_current, 0.0)
    avg_progress = (
        round((total_current / total_target * 100), 1) if total_target > 0 else 0.0
    )

    return {
        "goals": goals,
        "active_goals_count": active_count,
        "completed_goals_count": completed_count,
        "total_target_amount": total_target,
        "total_current_amount": total_current,
        "total_remaining_amount": total_remaining,
        "average_progress_percent": avg_progress,
        "currency": settings.CURRENCY_DEFAULT,
        "permissions": {
            "can_create_goal": await goal_service._get_role() != FamilyRole.VIEWER,
        },
    }


@router.get("/api/family-goals", response_model=FamilyGoalsDashboardResponse)
async def dashboard_family_goals_api(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return UI-ready JSON for the family goals dashboard widget."""
    data = await _build_family_goals_dashboard(db, user)
    return FamilyGoalsDashboardResponse(**data)


@router.get("/partials/family-goals", response_class=HTMLResponse)
async def family_goals_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial for the family goals dashboard widget."""
    family_goals = await _build_family_goals_dashboard(db, user)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_goals_widget.html",
        {
            "family_goals": family_goals,
            "currency": settings.CURRENCY_DEFAULT,
            "today": date.today().isoformat(),
        },
    )


@router.post("/partials/family-goals/{goal_id}/contributions", response_class=HTMLResponse)
async def family_goals_add_contribution_partial(
    request: Request,
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Add a contribution to a family goal from the dashboard widget."""
    goal_service = FamilyGoalService(db, tenant_id=user.organization_id, user=user)
    form_data = await request.form()

    try:
        amount = Decimal(str(form_data.get("amount", "0")))
        contribution_date = (
            date.fromisoformat(str(form_data.get("date")))
            if form_data.get("date")
            else date.today()
        )
        await goal_service.add_contribution(
            goal_id,
            GoalContributionCreate(
                amount=amount,
                date=contribution_date,
                description=str(form_data.get("description", "")),
            ),
        )
    except Exception as exc:
        # Surface the error inside the refreshed widget.
        family_goals = await _build_family_goals_dashboard(db, user)
        return templates.TemplateResponse(
            request,
            "dashboard/partials/family_goals_widget.html",
            {
                "family_goals": family_goals,
                "currency": settings.CURRENCY_DEFAULT,
                "today": date.today().isoformat(),
                "action_error": str(exc),
            },
            status_code=400,
        )

    family_goals = await _build_family_goals_dashboard(db, user)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_goals_widget.html",
        {
            "family_goals": family_goals,
            "currency": settings.CURRENCY_DEFAULT,
            "today": date.today().isoformat(),
        },
    )


@router.post(
    "/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse",
    response_class=HTMLResponse,
)
async def family_goals_reverse_contribution_partial(
    request: Request,
    goal_id: int,
    contribution_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reverse a posted family goal contribution from the dashboard widget.

    Reuses FamilyGoalService.reverse_contribution() unchanged -- the same
    tenant-scoped, permission-gated, idempotent reversal used by the
    POST /family/goals/{goal_id}/contributions/{contribution_id}/reverse API
    route (GOAL-1401B). No reversal logic lives here; this route only calls
    the service and re-renders the widget.
    """
    goal_service = FamilyGoalService(db, tenant_id=user.organization_id, user=user)
    action_error = None
    status_code = 200
    try:
        await goal_service.reverse_contribution(goal_id, contribution_id)
    except FamilyGoalServiceError as exc:
        action_error = exc.message
        status_code = 400

    family_goals = await _build_family_goals_dashboard(db, user)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_goals_widget.html",
        {
            "family_goals": family_goals,
            "currency": settings.CURRENCY_DEFAULT,
            "today": date.today().isoformat(),
            "action_error": action_error,
        },
        status_code=status_code,
    )


@router.post("/partials/family-goals/{goal_id}/complete", response_class=HTMLResponse)
async def family_goals_complete_partial(
    request: Request,
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Mark a family goal as completed from the dashboard widget."""
    goal_service = FamilyGoalService(db, tenant_id=user.organization_id, user=user)
    try:
        await goal_service.complete_goal(goal_id)
    except FamilyGoalServiceError:
        pass  # Refresh widget; user will not see the action if unauthorized.

    family_goals = await _build_family_goals_dashboard(db, user)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_goals_widget.html",
        {
            "family_goals": family_goals,
            "currency": settings.CURRENCY_DEFAULT,
            "today": date.today().isoformat(),
        },
    )


@router.post("/partials/family-goals/{goal_id}/cancel", response_class=HTMLResponse)
async def family_goals_cancel_partial(
    request: Request,
    goal_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Cancel a family goal from the dashboard widget."""
    goal_service = FamilyGoalService(db, tenant_id=user.organization_id, user=user)
    try:
        await goal_service.cancel_goal(goal_id)
    except FamilyGoalServiceError:
        pass

    family_goals = await _build_family_goals_dashboard(db, user)
    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_goals_widget.html",
        {
            "family_goals": family_goals,
            "currency": settings.CURRENCY_DEFAULT,
            "today": date.today().isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Family Budgets Dashboard Widget (DB-1106A)
# ---------------------------------------------------------------------------


async def _build_family_budgets_dashboard(db: AsyncSession, user: User) -> dict:
    """Load budgets visible to the user and compute a read-only dashboard summary.

    Reuses FamilyBudgetService's permission checks and budget-vs-actual
    calculation; never creates/updates/deletes financial records or budget
    actual fields while rendering.
    """
    service = FamilyBudgetService(db, tenant_id=user.organization_id, user=user)
    visible_budgets = await service.list_visible_budgets_for_user()

    budget_items: list[DashboardBudgetItem] = []
    total_planned = Decimal("0")
    total_actual = Decimal("0")
    over_budget_count = 0
    near_limit_count = 0
    active_count = 0
    percent_used_values: list[Decimal] = []

    for budget in visible_budgets:
        summary = await service.calculate_budget_summary(budget.id)
        is_over = bool(summary["over_budget_category_ids"])
        is_near = bool(summary["near_limit_category_ids"]) and not is_over

        categories = [
            DashboardBudgetCategoryItem(
                id=c["id"],
                name=c["name"],
                account_name=c["account_name"],
                planned_amount=c["budgeted_amount"],
                actual_amount=c["actual_amount"],
                remaining_amount=c["remaining_amount"],
                percent_used=c["percent_used"],
                alert_threshold=c["alert_threshold"],
                is_over_budget=c["is_over_budget"],
                is_near_limit=c["is_near_limit"],
            )
            for c in summary["categories"]
        ]

        budget_items.append(
            DashboardBudgetItem(
                id=budget.id,
                name=budget.name,
                visibility=budget.visibility,
                status=budget.status,
                period_start=budget.start_date,
                period_end=budget.end_date,
                total_planned=summary["total_planned"],
                total_actual=summary["total_actual"],
                total_remaining=summary["total_remaining"],
                percent_used=summary["percent_used"],
                is_over_budget=is_over,
                is_near_limit=is_near,
                categories=categories,
                can_view=True,
                can_manage=await service.can_user_manage_budget(budget),
            )
        )

        if budget.status == BudgetStatus.ACTIVE.value:
            active_count += 1
            total_planned += summary["total_planned"]
            total_actual += summary["total_actual"]
            percent_used_values.append(summary["percent_used"])
            if is_over:
                over_budget_count += 1
            elif is_near:
                near_limit_count += 1

    average_percent_used = (
        (sum(percent_used_values) / len(percent_used_values)).quantize(Decimal("0.01"))
        if percent_used_values
        else Decimal("0")
    )

    return {
        "budgets": budget_items,
        "active_budgets_count": active_count,
        "total_planned": total_planned,
        "total_actual": total_actual,
        "total_remaining": total_planned - total_actual,
        "average_percent_used": average_percent_used,
        "over_budget_count": over_budget_count,
        "near_limit_count": near_limit_count,
        "currency": settings.CURRENCY_DEFAULT,
        "permissions": {
            "can_create_budget": await service.can_create_budget(),
        },
    }


@router.get("/api/family-budgets", response_model=FamilyBudgetsDashboardResponse)
async def dashboard_family_budgets_api(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return UI-ready JSON for the family budgets dashboard widget."""
    data = await _build_family_budgets_dashboard(db, user)
    return FamilyBudgetsDashboardResponse(**data)


@router.get("/partials/family-budgets", response_class=HTMLResponse)
async def family_budgets_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial for the family budgets dashboard widget."""
    try:
        family_budgets = await _build_family_budgets_dashboard(db, user)
    except Exception:
        family_budgets = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_budgets_widget.html",
        {
            "family_budgets": family_budgets,
            "currency": settings.CURRENCY_DEFAULT,
        },
    )


@router.post("/partials/family-budgets/{budget_id}/archive", response_class=HTMLResponse)
async def family_budgets_archive_partial(
    request: Request,
    budget_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Archive a budget from the dashboard widget (permission-checked; status only)."""
    service = FamilyBudgetService(db, tenant_id=user.organization_id, user=user)
    action_error = None
    try:
        await service.archive_budget(budget_id)
    except FamilyBudgetServiceError as exc:
        action_error = exc.message

    try:
        family_budgets = await _build_family_budgets_dashboard(db, user)
    except Exception:
        family_budgets = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_budgets_widget.html",
        {
            "family_budgets": family_budgets,
            "currency": settings.CURRENCY_DEFAULT,
            "action_error": action_error,
        },
        status_code=400 if action_error else 200,
    )


@router.get("/partials/family-budgets/{budget_id}/categories", response_class=HTMLResponse)
async def family_budget_categories_partial(
    request: Request,
    budget_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial to expand a single budget's category breakdown, read-only."""
    service = FamilyBudgetService(db, tenant_id=user.organization_id, user=user)
    try:
        summary = await service.calculate_budget_summary(budget_id)
    except FamilyBudgetServiceError as exc:
        status_code = 404 if "not found" in exc.message.lower() else 403
        raise HTTPException(status_code=status_code, detail=exc.message)

    categories = [
        DashboardBudgetCategoryItem(
            id=c["id"],
            name=c["name"],
            account_name=c["account_name"],
            planned_amount=c["budgeted_amount"],
            actual_amount=c["actual_amount"],
            remaining_amount=c["remaining_amount"],
            percent_used=c["percent_used"],
            alert_threshold=c["alert_threshold"],
            is_over_budget=c["is_over_budget"],
            is_near_limit=c["is_near_limit"],
        )
        for c in summary["categories"]
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_budget_categories.html",
        {
            "budget_id": budget_id,
            "categories": categories,
            "currency": summary["currency"],
        },
    )


# ---------------------------------------------------------------------------
# Family chores & allowance dashboard widget (DB-1107A)
# ---------------------------------------------------------------------------


async def _build_family_chores_dashboard(db: AsyncSession, user: User) -> dict:
    """Load chores/completions visible to the user and compute a read-only summary.

    Reuses FamilyChoreService's permission checks and allowance
    calculations; never creates/updates completion records or posts
    allowance while rendering. Due-soon/overdue bucketing is view-only
    categorization of chores the service already scoped by role.
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)
    chores = await service.list_visible_chores_for_user()
    pending_completions = await service.list_pending_completions_for_user()
    allowance_summary = await service.get_allowance_summary()
    approved_this_month = await service.get_approved_allowance_this_month()

    today = date.today()
    due_soon_cutoff = date.fromordinal(today.toordinal() + 7)

    member_ids = {c.assigned_to_member_id for c in chores if c.assigned_to_member_id is not None}
    member_ids.update(c.completed_by_member_id for c in pending_completions)
    members_by_id: dict[int, FamilyMember] = {}
    if member_ids:
        result = await db.execute(select(FamilyMember).where(FamilyMember.id.in_(member_ids)))
        members_by_id = {m.id: m for m in result.scalars().all()}

    def _member_name(member_id: Optional[int]) -> Optional[str]:
        member = members_by_id.get(member_id) if member_id is not None else None
        return f"{member.first_name} {member.last_name}".strip() if member else None

    chore_titles_by_id = {c.id: c.title for c in chores}

    assigned_items: list[DashboardChoreItem] = []
    overdue_items: list[DashboardChoreItem] = []
    active_chores = [c for c in chores if c.status == ChoreStatus.ACTIVE.value]

    for chore in active_chores:
        is_overdue = chore.due_date is not None and chore.due_date < today
        is_due_soon = chore.due_date is not None and today <= chore.due_date <= due_soon_cutoff
        if not (is_overdue or is_due_soon):
            continue

        item = DashboardChoreItem(
            id=chore.id,
            title=chore.title,
            assigned_to_member_id=chore.assigned_to_member_id,
            assigned_to_name=_member_name(chore.assigned_to_member_id),
            allowance_amount=chore.allowance_amount,
            currency=chore.currency,
            frequency=chore.frequency,
            due_date=chore.due_date,
            status=chore.status,
            is_overdue=is_overdue,
            is_due_soon=is_due_soon,
            can_submit=await service.can_user_submit_completion(chore),
            can_manage=await service.can_user_manage_chore(chore),
        )
        if is_overdue:
            overdue_items.append(item)
        else:
            assigned_items.append(item)

    can_approve = await service.can_user_approve_completion()
    pending_items = [
        DashboardCompletionItem(
            id=completion.id,
            chore_id=completion.chore_id,
            chore_title=chore_titles_by_id.get(completion.chore_id, "Unknown chore"),
            completed_by_member_id=completion.completed_by_member_id,
            completed_by_name=_member_name(completion.completed_by_member_id),
            submitted_notes=completion.submitted_notes,
            status=completion.status,
            earned_amount=completion.earned_amount,
            completed_at=completion.completed_at,
            can_approve=can_approve,
            can_reject=can_approve,
        )
        for completion in pending_completions
    ]

    by_member = [
        DashboardAllowanceMemberBreakdown(**member_summary)
        for member_summary in allowance_summary["by_member"]
    ]

    can_post_payment = await service.can_user_post_payment()
    ready_to_pay_completions = await service.list_approved_unpaid_completions_for_user()
    recent_payment_completions = await service.list_recent_paid_completions_for_user()

    # Name lookups above only cover assigned/pending members; extend for
    # ready-to-pay and recent-payment completions too.
    extra_member_ids = {c.completed_by_member_id for c in ready_to_pay_completions}
    extra_member_ids.update(c.completed_by_member_id for c in recent_payment_completions)
    missing_member_ids = extra_member_ids - set(members_by_id.keys())
    if missing_member_ids:
        extra_result = await db.execute(select(FamilyMember).where(FamilyMember.id.in_(missing_member_ids)))
        members_by_id.update({m.id: m for m in extra_result.scalars().all()})

    ready_to_pay_items = [
        DashboardReadyToPayItem(
            id=completion.id,
            chore_id=completion.chore_id,
            chore_title=chore_titles_by_id.get(completion.chore_id, "Unknown chore"),
            member_id=completion.completed_by_member_id,
            member_name=_member_name(completion.completed_by_member_id),
            earned_amount=completion.earned_amount,
            currency=allowance_summary["currency"],
            approved_at=completion.approved_at,
            can_pay=can_post_payment,
        )
        for completion in ready_to_pay_completions
    ]

    recent_payment_items = [
        DashboardPaymentHistoryItem(
            id=completion.id,
            chore_title=chore_titles_by_id.get(completion.chore_id, "Unknown chore"),
            member_name=_member_name(completion.completed_by_member_id),
            earned_amount=completion.earned_amount,
            currency=allowance_summary["currency"],
            payment_status=completion.payment_status,
            payment_journal_entry_id=completion.payment_journal_entry_id,
            payment_reversal_journal_entry_id=completion.payment_reversal_journal_entry_id,
            paid_at=completion.paid_at,
            can_reverse=(
                can_post_payment
                and completion.payment_status == ChorePaymentStatus.PAID.value
                and bool(completion.payment_journal_entry_id)
                and not completion.payment_reversal_journal_entry_id
            ),
        )
        for completion in recent_payment_completions
    ]

    return {
        "assigned_chores": assigned_items,
        "overdue_chores": overdue_items,
        "pending_approvals": pending_items,
        "ready_to_pay": ready_to_pay_items,
        "recent_payments": recent_payment_items,
        "allowance_summary": DashboardAllowanceSummary(
            currency=allowance_summary["currency"],
            pending_approval_amount=allowance_summary["pending_approval_amount"],
            approved_earned_amount=allowance_summary["approved_earned_amount"],
            approved_this_month_amount=approved_this_month,
            approved_unpaid_amount=allowance_summary["approved_unpaid_amount"],
            paid_amount=allowance_summary["paid_amount"],
            reversed_amount=allowance_summary["reversed_amount"],
            rejected_amount=allowance_summary["rejected_amount"],
            by_member=by_member,
        ),
        "due_soon_count": len(assigned_items),
        "overdue_count": len(overdue_items),
        "pending_approvals_count": len(pending_items),
        "ready_to_pay_count": len(ready_to_pay_items),
        "currency": allowance_summary["currency"],
        "permissions": {
            "can_manage_chores": await service.can_user_manage_chore(),
            "can_approve_completions": can_approve,
            "can_post_payment": can_post_payment,
        },
    }


@router.get("/api/family-chores", response_model=FamilyChoresDashboardResponse)
async def dashboard_family_chores_api(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return UI-ready JSON for the family chores & allowance dashboard widget."""
    data = await _build_family_chores_dashboard(db, user)
    return FamilyChoresDashboardResponse(**data)


@router.get("/partials/family-chores", response_class=HTMLResponse)
async def family_chores_partial(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """HTMX partial for the family chores & allowance dashboard widget."""
    try:
        family_chores = await _build_family_chores_dashboard(db, user)
    except Exception:
        family_chores = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chores_widget.html",
        {
            "family_chores": family_chores,
            "currency": settings.CURRENCY_DEFAULT,
        },
    )


@router.post("/partials/family-chores/{chore_id}/complete", response_class=HTMLResponse)
async def family_chores_complete_partial(
    request: Request,
    chore_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Submit a chore completion from the dashboard widget (permission-checked).

    Creates only a FamilyChoreCompletion record (status=submitted, earned
    amount 0 until approved) — never a transaction, journal entry, or
    account balance change.
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)
    action_error = None
    try:
        await service.submit_completion(chore_id, ChoreCompletionCreate())
    except FamilyChoreServiceError as exc:
        action_error = exc.message

    try:
        family_chores = await _build_family_chores_dashboard(db, user)
    except Exception:
        family_chores = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chores_widget.html",
        {
            "family_chores": family_chores,
            "currency": settings.CURRENCY_DEFAULT,
            "action_error": action_error,
        },
        status_code=400 if action_error else 200,
    )


@router.post("/partials/family-chore-completions/{completion_id}/approve", response_class=HTMLResponse)
async def family_chore_completions_approve_partial(
    request: Request,
    completion_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Approve a chore completion from the dashboard widget (HEAD/PARENT only).

    Sets the completion's earned_amount to the chore's allowance amount;
    never creates a transaction, journal entry, or posts to any account.
    Reject is intentionally not offered here since it requires a reason —
    use the full chore completions view to reject (see implementation
    report "Known Limitations").
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)
    action_error = None
    try:
        await service.approve_completion(completion_id)
    except FamilyChoreServiceError as exc:
        action_error = exc.message

    try:
        family_chores = await _build_family_chores_dashboard(db, user)
    except Exception:
        family_chores = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chores_widget.html",
        {
            "family_chores": family_chores,
            "currency": settings.CURRENCY_DEFAULT,
            "action_error": action_error,
        },
        status_code=400 if action_error else 200,
    )


# ---------------------------------------------------------------------------
# Allowance payment dashboard action form (DB-1107B)
# ---------------------------------------------------------------------------


def _dashboard_chore_error_status(message: str) -> int:
    lower = message.lower()
    if "not found" in lower:
        return 404
    if "permission" in lower:
        return 403
    return 400


async def _dashboard_account_options(db: AsyncSession, user: User) -> tuple[list, list]:
    """Return (payment_account_options, expense_account_options) visible to the user.

    Reuses FamilyAccountAccessService.list_visible_accounts() unchanged —
    only accounts the user is already allowed to see/use are offered, so
    inaccessible private accounts and cross-tenant accounts never appear.
    """
    access = FamilyAccountAccessService(db, tenant_id=user.organization_id, user=user)
    visible_accounts = await access.list_visible_accounts()
    payment_options = [
        DashboardAccountOption(id=a.id, code=a.code, name=a.name)
        for a in visible_accounts if a.account_type == "Asset"
    ]
    expense_options = [
        DashboardAccountOption(id=a.id, code=a.code, name=a.name)
        for a in visible_accounts if a.account_type == "Expense"
    ]
    return payment_options, expense_options


async def _dashboard_ready_to_pay_item(service: FamilyChoreService, completion) -> DashboardReadyToPayItem:
    """Build a DashboardReadyToPayItem for the payment-form partial, read-only."""
    chore = await service._get_chore_raw(completion.chore_id)
    member = await service._get_member(completion.completed_by_member_id)
    return DashboardReadyToPayItem(
        id=completion.id,
        chore_id=completion.chore_id,
        chore_title=chore.title if chore is not None else "Unknown chore",
        member_id=completion.completed_by_member_id,
        member_name=(f"{member.first_name} {member.last_name}".strip() if member else None),
        earned_amount=completion.earned_amount,
        currency=chore.currency if chore is not None else settings.CURRENCY_DEFAULT,
        approved_at=completion.approved_at,
        can_pay=True,
    )


@router.get(
    "/partials/family-chore-completions/{completion_id}/payment-form",
    response_class=HTMLResponse,
)
async def family_chore_payment_form_partial(
    request: Request,
    completion_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Render the inline payment-posting form for one approved unpaid completion.

    Read-only: never creates, updates, or posts anything. HEAD/PARENT
    only; every other role gets a safe inline message instead of a form,
    even if they craft the request directly.
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)

    if not await service.can_user_post_payment():
        return templates.TemplateResponse(
            request,
            "dashboard/partials/family_chore_payment_form.html",
            {"completion_id": completion_id, "completion_item": None, "payment_account_options": [],
             "expense_account_options": [], "form_error": "You do not have permission to post allowance payments."},
            status_code=403,
        )

    completion = await service._get_completion_raw(completion_id)
    if completion is None:
        return templates.TemplateResponse(
            request,
            "dashboard/partials/family_chore_payment_form.html",
            {"completion_id": completion_id, "completion_item": None, "payment_account_options": [],
             "expense_account_options": [], "form_error": "Chore completion not found."},
            status_code=404,
        )

    if (
        completion.status != ChoreCompletionStatus.APPROVED.value
        or completion.payment_status != ChorePaymentStatus.UNPAID.value
        or completion.earned_amount <= 0
    ):
        return templates.TemplateResponse(
            request,
            "dashboard/partials/family_chore_payment_form.html",
            {"completion_id": completion_id, "completion_item": None, "payment_account_options": [],
             "expense_account_options": [], "form_error": "This completion is not ready to pay."},
            status_code=400,
        )

    completion_item = await _dashboard_ready_to_pay_item(service, completion)
    payment_options, expense_options = await _dashboard_account_options(db, user)

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chore_payment_form.html",
        {
            "completion_id": completion_id,
            "completion_item": completion_item,
            "payment_account_options": payment_options,
            "expense_account_options": expense_options,
            "form_error": None,
        },
    )


@router.post(
    "/partials/family-chore-completions/{completion_id}/post-payment",
    response_class=HTMLResponse,
)
async def family_chore_completions_dashboard_post_payment(
    request: Request,
    completion_id: int,
    payment_account_id: Optional[int] = Form(None),
    expense_account_id: Optional[int] = Form(None),
    payment_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Submit the inline payment form and post an allowance payment.

    Posts through FamilyChoreService.post_payment() unchanged — the user
    must explicitly choose both accounts; nothing is ever guessed. On
    success the whole Chores & Allowance widget is refreshed (via
    HX-Retarget/HX-Reswap) so the completion moves out of "ready to pay"
    into the allowance summary's Paid total. On any error, only the
    inline form re-renders with a message and no journal entry is created.
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)

    form_error: Optional[str] = None
    if not await service.can_user_post_payment():
        form_error = "You do not have permission to post allowance payments"
    elif payment_account_id is None or expense_account_id is None:
        form_error = "Please select both a payment account and an expense account."
    else:
        parsed_date = None
        if payment_date:
            try:
                parsed_date = date.fromisoformat(payment_date)
            except ValueError:
                form_error = "Invalid payment date."

        if form_error is None:
            try:
                await service.post_payment(
                    completion_id,
                    payment_account_id=payment_account_id,
                    expense_account_id=expense_account_id,
                    payment_date=parsed_date,
                    notes=notes or None,
                )
            except FamilyChoreServiceError as exc:
                form_error = exc.message

    if form_error is None:
        try:
            family_chores = await _build_family_chores_dashboard(db, user)
        except Exception:
            family_chores = None

        response = templates.TemplateResponse(
            request,
            "dashboard/partials/family_chores_widget.html",
            {
                "family_chores": family_chores,
                "currency": settings.CURRENCY_DEFAULT,
            },
        )
        response.headers["HX-Retarget"] = "#family-chores-widget"
        response.headers["HX-Reswap"] = "outerHTML"
        return response

    # Re-render the inline form in place, with the error and the same
    # account options, so the user can correct their selection.
    completion = await service._get_completion_raw(completion_id)
    completion_item = None
    payment_options: list = []
    expense_options: list = []
    if completion is not None:
        completion_item = await _dashboard_ready_to_pay_item(service, completion)
        payment_options, expense_options = await _dashboard_account_options(db, user)

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chore_payment_form.html",
        {
            "completion_id": completion_id,
            "completion_item": completion_item,
            "payment_account_options": payment_options,
            "expense_account_options": expense_options,
            "form_error": form_error,
        },
        status_code=_dashboard_chore_error_status(form_error),
    )


@router.post(
    "/partials/family-chore-completions/{completion_id}/reverse-payment",
    response_class=HTMLResponse,
)
async def family_chore_completions_reverse_payment_partial(
    request: Request,
    completion_id: int,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Reverse a posted allowance payment from the dashboard widget (HEAD/PARENT only).

    Reuses FamilyChoreService.reverse_payment() unchanged, which delegates
    entirely to AccountingService.reverse_journal_entry() (ACC-503A) — the
    original payment journal entry is never deleted or mutated, and a
    reversal is only ever created once (idempotent on
    payment_reversal_journal_entry_id). Follows the exact same
    action_error / whole-widget-refresh pattern already used by the
    submit-completion and approve-completion quick actions (DB-1107A).
    """
    service = FamilyChoreService(db, tenant_id=user.organization_id, user=user)
    action_error = None
    try:
        await service.reverse_payment(completion_id)
    except FamilyChoreServiceError as exc:
        action_error = exc.message

    try:
        family_chores = await _build_family_chores_dashboard(db, user)
    except Exception:
        family_chores = None

    return templates.TemplateResponse(
        request,
        "dashboard/partials/family_chores_widget.html",
        {
            "family_chores": family_chores,
            "currency": settings.CURRENCY_DEFAULT,
            "action_error": action_error,
        },
        status_code=400 if action_error else 200,
    )
