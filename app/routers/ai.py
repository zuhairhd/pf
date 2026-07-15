from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.ai_cfo.engines.debt_optimizer import DebtOptimizer, DebtOptimizerError, DebtStrategyType
from app.ai_cfo.engines.goal_planner import (
    GoalPlanMode,
    GoalPlanner,
    GoalPlannerError,
    GoalPriorityStrategy,
)
from app.ai_cfo.engines.proactive_alerts import (
    ProactiveAlertSeverity,
    ProactiveAlertsEngine,
    ProactiveAlertsError,
    ProactiveAlertType,
)
from app.ai_cfo.engines.savings_optimizer import (
    AllocationStrategy,
    SavingsModeType,
    SavingsOptimizer,
    SavingsOptimizerError,
)
from app.ai_cfo.engines.whatif_simulator import WhatIfError, WhatIfScenarioType, WhatIfSimulator
from app.ai_cfo.llm.prompts import DEFAULT_DISCLAIMER
from app.core.security import (
    get_db_with_tenant_context,
    require_tenant_admin,
    require_tenant_member,
)
from app.models import AIInsight, AIReport, AIChatSession, AIChatMessage, User
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    DebtOptimizerCompareResponse,
    DebtOptimizerRequest,
    DebtOptimizerResponse,
    GoalPlannerModeMeta,
    GoalPlannerRequest,
    GoalPlannerResponse,
    GoalPlannerStrategyMeta,
    GoalPrioritizeRequest,
    GoalPrioritizeResponse,
    ProactiveAlertPreviewResponse,
    ProactiveAlertRunRequest,
    ProactiveAlertRunResponse,
    ProactiveAlertTypeMeta,
    SavingsOptimizerCompareResponse,
    SavingsOptimizerRequest,
    SavingsOptimizerResponse,
    SavingsOptimizerStrategyMeta,
    WhatIfCompareRequest,
    WhatIfCompareResponse,
    WhatIfRequest,
    WhatIfResponse,
    WhatIfScenarioField,
    WhatIfScenarioMeta,
    WhatIfScenarioRequest,
    WhatIfScenariosResponse,
    WhatIfSimulationResponse,
)
from app.services.ai_orchestrator import AIOrchestrator
from app.services.ai_chat import AIChatService
from app.services.ai_forecast import AIForecastService
from app.config import get_settings

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


_SCENARIO_CATALOG = [
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.INCREASE_MONTHLY_SAVINGS.value,
        label="Increase monthly savings",
        description="Model the impact of saving an extra fixed amount each month.",
        fields=[
            WhatIfScenarioField(name="monthly_extra_savings", field_type="decimal", required=True, description="Extra amount to save each month"),
            WhatIfScenarioField(name="target_account_id", field_type="integer", required=False, description="Optional destination account"),
            WhatIfScenarioField(name="goal_id", field_type="integer", required=False, description="Optional linked goal to show acceleration"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.REDUCE_EXPENSE_CATEGORY.value,
        label="Reduce expense category",
        description="Model the impact of reducing a recurring expense.",
        fields=[
            WhatIfScenarioField(name="monthly_reduction_amount", field_type="decimal", required=False, description="Fixed monthly reduction"),
            WhatIfScenarioField(name="reduction_percent", field_type="decimal", required=False, description="Percentage reduction of the category"),
            WhatIfScenarioField(name="expense_account_id", field_type="integer", required=False, description="Optional expense account"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.INCOME_INCREASE.value,
        label="Income increase",
        description="Model the impact of a raise or new income stream.",
        fields=[
            WhatIfScenarioField(name="monthly_income_increase", field_type="decimal", required=False, description="Fixed monthly increase"),
            WhatIfScenarioField(name="percent_increase", field_type="decimal", required=False, description="Percentage increase"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.EMERGENCY_EXPENSE.value,
        label="Emergency expense",
        description="Model the impact of a one-time unexpected expense.",
        fields=[
            WhatIfScenarioField(name="amount", field_type="decimal", required=True, description="One-time expense amount"),
            WhatIfScenarioField(name="month_number", field_type="integer", required=False, description="Month in which the expense occurs"),
            WhatIfScenarioField(name="source_account_id", field_type="integer", required=False, description="Account used to cover the expense"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.CANCEL_SUBSCRIPTION.value,
        label="Cancel subscription",
        description="Model the impact of cancelling a recurring subscription.",
        fields=[
            WhatIfScenarioField(name="subscription_id", field_type="integer", required=True, description="Subscription to cancel"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.GOAL_CONTRIBUTION_INCREASE.value,
        label="Increase goal contribution",
        description="Model how increasing monthly contributions affects goal progress.",
        fields=[
            WhatIfScenarioField(name="goal_id", field_type="integer", required=True, description="Goal to contribute to"),
            WhatIfScenarioField(name="monthly_extra_contribution", field_type="decimal", required=True, description="Extra monthly contribution"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
    WhatIfScenarioMeta(
        scenario_type=WhatIfScenarioType.NEW_MONTHLY_PAYMENT.value,
        label="New monthly payment",
        description="Model the impact of a new recurring payment such as a car loan.",
        fields=[
            WhatIfScenarioField(name="down_payment", field_type="decimal", required=False, description="One-time upfront payment"),
            WhatIfScenarioField(name="monthly_payment", field_type="decimal", required=True, description="Recurring monthly payment"),
            WhatIfScenarioField(name="months", field_type="integer", required=False, description="Projection horizon (1-120)"),
        ],
    ),
]


def _handle_whatif_error(exc: WhatIfError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """AI chat interface page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})

    # Get chat sessions
    result = await db.execute(
        select(AIChatSession)
        .where(AIChatSession.tenant_id == tenant_id)
        .order_by(AIChatSession.created_at.desc())
        .limit(10)
    )
    sessions = result.scalars().all()

    return templates.TemplateResponse("ai/chat.html", {
        "request": request,
        "sessions": sessions,
    })


@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Chat with the AI Financial Coach."""
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)

    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    chat_service = AIChatService(db, tenant_id, user_id)
    response = await chat_service.chat(chat_request.message, chat_request.session_id)

    return response


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """AI insights page."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return templates.TemplateResponse("auth/login.html", {"request": request})

    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.tenant_id == tenant_id)
        .where(AIInsight.is_dismissed == False)
        .order_by(AIInsight.priority.desc(), AIInsight.created_at.desc())
    )
    insights = result.scalars().all()

    return templates.TemplateResponse("ai/insights.html", {
        "request": request,
        "insights": insights,
    })


@router.post("/what-if", response_model=WhatIfResponse)
async def what_if_scenario(
    request: WhatIfRequest,
    request_obj: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Run a what-if scenario."""
    tenant_id = getattr(request_obj.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    forecast_service = AIForecastService(db, tenant_id)
    result = await forecast_service.simulate_scenario(request.scenario)

    return result


@router.get("/what-if/scenarios", response_model=WhatIfScenariosResponse)
async def what_if_scenarios(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return supported what-if scenario types and their fields."""
    return WhatIfScenariosResponse(scenarios=_SCENARIO_CATALOG)


@router.post("/what-if/simulate", response_model=WhatIfSimulationResponse)
async def what_if_simulate(
    request: WhatIfScenarioRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Run a single structured what-if scenario."""
    simulator = WhatIfSimulator(db, user.organization_id, user=user)
    try:
        result = await simulator.simulate(request.model_dump())
    except WhatIfError as exc:
        _handle_whatif_error(exc)
    return WhatIfSimulationResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


@router.post("/what-if/compare", response_model=WhatIfCompareResponse)
async def what_if_compare(
    request: WhatIfCompareRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Compare multiple what-if scenarios side-by-side."""
    simulator = WhatIfSimulator(db, user.organization_id, user=user)
    try:
        results = await simulator.simulate_many([s.model_dump() for s in request.scenarios])
    except WhatIfError as exc:
        _handle_whatif_error(exc)

    best = max(results, key=lambda r: r["ending_balance_scenario"])
    worst = min(results, key=lambda r: r["ending_balance_scenario"])
    summary = {
        "best_ending_balance_scenario": best["scenario_label"],
        "worst_ending_balance_scenario": worst["scenario_label"],
        "best_ending_balance": best["ending_balance_scenario"],
        "worst_ending_balance": worst["ending_balance_scenario"],
    }
    return WhatIfCompareResponse(
        results=results,
        summary=summary,
        disclaimer=DEFAULT_DISCLAIMER,
    )



# ---------------------------------------------------------------------------
# Debt Optimizer (AI-1211)
# ---------------------------------------------------------------------------

_STRATEGY_CATALOG = [
    {
        "strategy_type": DebtStrategyType.AVALANCHE.value,
        "label": "Avalanche",
        "description": "Pay off highest-interest debt first to minimize total interest.",
    },
    {
        "strategy_type": DebtStrategyType.SNOWBALL.value,
        "label": "Snowball",
        "description": "Pay off smallest balance first for quick wins and motivation.",
    },
    {
        "strategy_type": DebtStrategyType.CUSTOM_ORDER.value,
        "label": "Custom order",
        "description": "Pay off debts in a user-defined order.",
    },
]


def _handle_debt_optimizer_error(exc: DebtOptimizerError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/debt-optimizer/strategies")
async def debt_optimizer_strategies(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return available debt payoff strategies."""
    return {"strategies": _STRATEGY_CATALOG}


@router.post("/debt-optimizer/simulate", response_model=DebtOptimizerResponse)
async def debt_optimizer_simulate(
    request: DebtOptimizerRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Run a single debt payoff optimization strategy."""
    optimizer = DebtOptimizer(db, user.organization_id, user=user)
    try:
        result = await optimizer.optimize(
            strategy=DebtStrategyType(request.strategy),
            extra_monthly_payment=request.extra_monthly_payment,
            loan_ids=request.loan_ids,
            account_ids=request.account_ids,
            custom_order=request.custom_order,
            include_narrative=request.include_narrative,
        )
    except DebtOptimizerError as exc:
        _handle_debt_optimizer_error(exc)
    return DebtOptimizerResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


@router.post("/debt-optimizer/compare", response_model=DebtOptimizerCompareResponse)
async def debt_optimizer_compare(
    request: DebtOptimizerRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Compare avalanche vs snowball payoff strategies."""
    optimizer = DebtOptimizer(db, user.organization_id, user=user)
    try:
        comparison = await optimizer.compare(
            extra_monthly_payment=request.extra_monthly_payment,
            loan_ids=request.loan_ids,
            account_ids=request.account_ids,
            include_narrative=request.include_narrative,
        )
    except DebtOptimizerError as exc:
        _handle_debt_optimizer_error(exc)
    return DebtOptimizerCompareResponse(
        results=comparison["results"],
        recommendation=comparison["recommendation"],
        disclaimer=DEFAULT_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Savings Optimizer (AI-1212)
# ---------------------------------------------------------------------------

_SAVINGS_STRATEGY_CATALOG = [
    SavingsOptimizerStrategyMeta(
        mode=SavingsModeType.EMERGENCY_FUND.value,
        label="Emergency fund analysis",
        description="Calculate emergency-fund target, gap, and months to reach it.",
    ),
    SavingsOptimizerStrategyMeta(
        mode=SavingsModeType.SAVINGS_CAPACITY.value,
        label="Monthly savings capacity",
        description="Estimate how much you can save each month based on recent income and expenses.",
    ),
    SavingsOptimizerStrategyMeta(
        mode=SavingsModeType.GOAL_ALLOCATION.value,
        label="Goal-based savings allocation",
        description="Allocate monthly savings across goals using a chosen strategy.",
    ),
    SavingsOptimizerStrategyMeta(
        mode=SavingsModeType.REDUCE_SPENDING.value,
        label="Reduce spending to save more",
        description="Find how much spending must be cut to hit a target monthly savings amount.",
    ),
    SavingsOptimizerStrategyMeta(
        mode=SavingsModeType.COMPARE_STRATEGIES.value,
        label="Compare savings strategies",
        description="Compare goal allocation strategies side-by-side.",
    ),
]


def _handle_savings_optimizer_error(exc: SavingsOptimizerError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/savings-optimizer/strategies")
async def savings_optimizer_strategies(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return available savings optimization modes."""
    return {"strategies": _SAVINGS_STRATEGY_CATALOG}


@router.post("/savings-optimizer/simulate", response_model=SavingsOptimizerResponse)
async def savings_optimizer_simulate(
    request: SavingsOptimizerRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Run a single savings optimization mode."""
    optimizer = SavingsOptimizer(db, user.organization_id, user=user)
    try:
        result = await optimizer.optimize(
            mode=SavingsModeType(request.mode),
            request=request.model_dump(),
        )
    except SavingsOptimizerError as exc:
        _handle_savings_optimizer_error(exc)
    return SavingsOptimizerResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


@router.post("/savings-optimizer/compare", response_model=SavingsOptimizerCompareResponse)
async def savings_optimizer_compare(
    request: SavingsOptimizerRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Compare goal allocation strategies."""
    optimizer = SavingsOptimizer(db, user.organization_id, user=user)
    try:
        result = await optimizer.compare(request.model_dump())
    except SavingsOptimizerError as exc:
        _handle_savings_optimizer_error(exc)
    return SavingsOptimizerCompareResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


# ---------------------------------------------------------------------------
# Goal Planner (AI-1213)
# ---------------------------------------------------------------------------

_GOAL_PLANNER_MODE_CATALOG = [
    GoalPlannerModeMeta(
        mode=GoalPlanMode.SINGLE_GOAL_FEASIBILITY.value,
        label="Single goal feasibility",
        description="Analyze whether one existing goal is on track and what monthly contribution is required.",
    ),
    GoalPlannerModeMeta(
        mode=GoalPlanMode.HYPOTHETICAL_GOAL.value,
        label="Hypothetical goal",
        description="Plan a new goal before creating it by estimating required contributions and timeline.",
    ),
    GoalPlannerModeMeta(
        mode=GoalPlanMode.MULTI_GOAL_PRIORITIZATION.value,
        label="Multi-goal prioritization",
        description="Allocate monthly savings across multiple goals using a chosen strategy.",
    ),
    GoalPlannerModeMeta(
        mode=GoalPlanMode.DEADLINE_RESCUE.value,
        label="Deadline rescue plan",
        description="Get options to bring an at-risk goal back on track before its deadline.",
    ),
    GoalPlannerModeMeta(
        mode=GoalPlanMode.FAMILY_GOAL_PLAN.value,
        label="Family goal plan",
        description="Build a shared allocation plan across visible family goals.",
    ),
]

_GOAL_PLANNER_STRATEGY_CATALOG = [
    GoalPlannerStrategyMeta(
        strategy=GoalPriorityStrategy.EQUAL_SPLIT.value,
        label="Equal split",
        description="Divide available savings evenly across all goals.",
    ),
    GoalPlannerStrategyMeta(
        strategy=GoalPriorityStrategy.PRIORITY_FIRST.value,
        label="Priority first",
        description="Fund highest-priority goals fully before lower-priority goals.",
    ),
    GoalPlannerStrategyMeta(
        strategy=GoalPriorityStrategy.CLOSEST_DEADLINE.value,
        label="Closest deadline",
        description="Fund goals with the nearest target dates first.",
    ),
    GoalPlannerStrategyMeta(
        strategy=GoalPriorityStrategy.LOWEST_GAP_FIRST.value,
        label="Lowest gap first",
        description="Fund goals with the smallest remaining amount first.",
    ),
]


def _handle_goal_planner_error(exc: GoalPlannerError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/goal-planner/modes")
async def goal_planner_modes(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return supported goal planning modes and strategies."""
    return {
        "modes": _GOAL_PLANNER_MODE_CATALOG,
        "strategies": _GOAL_PLANNER_STRATEGY_CATALOG,
    }


@router.post("/goal-planner/plan", response_model=GoalPlannerResponse)
async def goal_planner_plan(
    request: GoalPlannerRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Run one goal planning mode."""
    planner = GoalPlanner(db, user.organization_id, user=user)
    try:
        result = await planner.plan(
            mode=GoalPlanMode(request.mode),
            request=request.model_dump(),
        )
    except GoalPlannerError as exc:
        _handle_goal_planner_error(exc)
    return GoalPlannerResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


@router.post("/goal-planner/prioritize", response_model=GoalPrioritizeResponse)
async def goal_planner_prioritize(
    request: GoalPrioritizeRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Prioritize multiple goals using a selected strategy."""
    planner = GoalPlanner(db, user.organization_id, user=user)
    try:
        result = await planner.prioritize(request.model_dump())
    except GoalPlannerError as exc:
        _handle_goal_planner_error(exc)
    return GoalPrioritizeResponse(result=result, disclaimer=DEFAULT_DISCLAIMER)


# ---------------------------------------------------------------------------
# Proactive Alerts (AI-1219)
# ---------------------------------------------------------------------------

_PROACTIVE_ALERT_CATALOG = [
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.BILL_DUE_SOON.value,
        label="Bill due soon",
        description="Unpaid bills due within the configured number of days.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.BILL_OVERDUE.value,
        label="Bill overdue",
        description="Unpaid bills that have passed their due date.",
        default_severity=ProactiveAlertSeverity.CRITICAL.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.SUBSCRIPTION_RENEWAL_SOON.value,
        label="Subscription renewal soon",
        description="Active subscriptions renewing within the configured number of days.",
        default_severity=ProactiveAlertSeverity.INFO.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.HIGH_SPENDING_ANOMALY.value,
        label="High spending anomaly",
        description="Recent spending significantly above the recent baseline.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.NEGATIVE_CASH_FLOW.value,
        label="Cash-flow risk",
        description="Average monthly expenses are near or exceeding income.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.LOW_EMERGENCY_FUND.value,
        label="Emergency fund risk",
        description="Liquid assets cover fewer months of expenses than the configured target.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.GOAL_DEADLINE_RISK.value,
        label="Goal deadline risk",
        description="A goal may miss its target date at the current contribution rate.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
    ProactiveAlertTypeMeta(
        alert_type=ProactiveAlertType.DEBT_PRESSURE.value,
        label="Debt pressure warning",
        description="Debt obligations are high relative to income, or a minimum payment does not cover interest.",
        default_severity=ProactiveAlertSeverity.WARNING.value,
    ),
]


def _handle_proactive_alerts_error(exc: ProactiveAlertsError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/proactive-alerts/types")
async def proactive_alerts_types(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return supported proactive alert types and thresholds."""
    return {
        "alert_types": _PROACTIVE_ALERT_CATALOG,
        "thresholds": {
            "bill_due_days": settings.ALERT_BILL_DUE_DAYS,
            "subscription_renewal_days": settings.ALERT_SUBSCRIPTION_RENEWAL_DAYS,
            "spending_anomaly_percent": settings.ALERT_SPENDING_ANOMALY_PERCENT,
            "low_cashflow_threshold": settings.ALERT_LOW_CASHFLOW_THRESHOLD,
            "emergency_fund_months": settings.ALERT_EMERGENCY_FUND_MONTHS,
            "debt_to_income_threshold": settings.ALERT_DEBT_TO_INCOME_THRESHOLD,
        },
    }


@router.post("/proactive-alerts/preview", response_model=ProactiveAlertPreviewResponse)
async def proactive_alerts_preview(
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_member),
):
    """Return detected alert candidates without creating notifications."""
    engine = ProactiveAlertsEngine(db, user.organization_id, user=user)
    try:
        candidates = await engine.preview()
    except ProactiveAlertsError as exc:
        _handle_proactive_alerts_error(exc)

    return ProactiveAlertPreviewResponse(
        candidates=[
            {
                "alert_type": c.alert_type.value,
                "severity": c.severity.value,
                "title": c.title,
                "message": c.message,
                "related_entity_type": c.related_entity_type,
                "related_entity_id": c.related_entity_id,
            }
            for c in candidates
        ]
    )


@router.post("/proactive-alerts/run", response_model=ProactiveAlertRunResponse)
async def proactive_alerts_run(
    request: ProactiveAlertRunRequest,
    db: AsyncSession = Depends(get_db_with_tenant_context),
    user: User = Depends(require_tenant_admin),
):
    """Detect alerts and create in-app notifications, deduplicated by day."""
    engine = ProactiveAlertsEngine(db, user.organization_id, user=user)
    try:
        result = await engine.run(include_llm_wording=request.include_llm_wording)
    except ProactiveAlertsError as exc:
        _handle_proactive_alerts_error(exc)
    return ProactiveAlertRunResponse(**result)


@router.get("/reports/daily")
async def get_daily_report(
    request: Request,
    db: AsyncSession = Depends(get_db_with_tenant_context),
):
    """Get the latest daily AI report."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Not authenticated")

    result = await db.execute(
        select(AIReport)
        .where(AIReport.tenant_id == tenant_id)
        .where(AIReport.report_type == "daily")
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()

    if not report:
        # Generate on demand
        orchestrator = AIOrchestrator(db, tenant_id)
        report = await orchestrator.generate_daily_brief()

    return report
