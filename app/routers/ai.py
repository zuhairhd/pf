from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.ai_cfo.engines.debt_optimizer import DebtOptimizer, DebtOptimizerError, DebtStrategyType
from app.ai_cfo.engines.whatif_simulator import WhatIfError, WhatIfScenarioType, WhatIfSimulator
from app.ai_cfo.llm.prompts import DEFAULT_DISCLAIMER
from app.core.security import get_db_with_tenant_context, require_tenant_member
from app.models import AIInsight, AIReport, AIChatSession, AIChatMessage, User
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    DebtOptimizerCompareResponse,
    DebtOptimizerRequest,
    DebtOptimizerResponse,
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
