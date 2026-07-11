from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional, List, Union

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    confidence: Optional[int] = None
    actions: Optional[List[dict]] = None
    follow_up_questions: Optional[List[str]] = None
    related_insights: Optional[List[str]] = None
    disclaimer: Optional[str] = None
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None


class WhatIfRequest(BaseModel):
    scenario: str = Field(..., min_length=1, max_length=500)


class WhatIfResponse(BaseModel):
    scenario: str
    impact_summary: str
    projected_changes: Optional[List[dict]] = None
    recommendations: Optional[List[str]] = None
    confidence: Optional[int] = None


# ---------------------------------------------------------------------------
# Structured What-If Simulator schemas (AI-1214)
# ---------------------------------------------------------------------------


class WhatIfScenarioField(BaseModel):
    name: str
    field_type: str
    required: bool
    description: str


class WhatIfScenarioMeta(BaseModel):
    scenario_type: str
    label: str
    description: str
    fields: List[WhatIfScenarioField]


class WhatIfScenariosResponse(BaseModel):
    scenarios: List[WhatIfScenarioMeta]


class WhatIfBaseRequest(BaseModel):
    months: int = Field(12, ge=1, le=120)
    include_narrative: bool = False


class IncreaseMonthlySavingsRequest(WhatIfBaseRequest):
    scenario_type: Literal["increase_monthly_savings"] = "increase_monthly_savings"
    monthly_extra_savings: Decimal = Field(..., gt=0)
    target_account_id: Optional[int] = None
    goal_id: Optional[int] = None


class ReduceExpenseRequest(WhatIfBaseRequest):
    scenario_type: Literal["reduce_expense_category"] = "reduce_expense_category"
    monthly_reduction_amount: Optional[Decimal] = Field(None, gt=0)
    reduction_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    expense_account_id: Optional[int] = None


class IncomeIncreaseRequest(WhatIfBaseRequest):
    scenario_type: Literal["income_increase"] = "income_increase"
    monthly_income_increase: Optional[Decimal] = Field(None, gt=0)
    percent_increase: Optional[Decimal] = Field(None, gt=0, le=100)


class EmergencyExpenseRequest(WhatIfBaseRequest):
    scenario_type: Literal["emergency_expense"] = "emergency_expense"
    amount: Decimal = Field(..., gt=0)
    month_number: int = Field(1, ge=1)
    source_account_id: Optional[int] = None


class CancelSubscriptionRequest(WhatIfBaseRequest):
    scenario_type: Literal["cancel_subscription"] = "cancel_subscription"
    subscription_id: int = Field(..., ge=1)


class GoalContributionRequest(WhatIfBaseRequest):
    scenario_type: Literal["goal_contribution_increase"] = "goal_contribution_increase"
    goal_id: int = Field(..., ge=1)
    monthly_extra_contribution: Decimal = Field(..., gt=0)


class NewMonthlyPaymentRequest(WhatIfBaseRequest):
    scenario_type: Literal["new_monthly_payment"] = "new_monthly_payment"
    down_payment: Decimal = Field(Decimal("0"), ge=0)
    monthly_payment: Decimal = Field(..., gt=0)


WhatIfScenarioRequest = Union[
    IncreaseMonthlySavingsRequest,
    ReduceExpenseRequest,
    IncomeIncreaseRequest,
    EmergencyExpenseRequest,
    CancelSubscriptionRequest,
    GoalContributionRequest,
    NewMonthlyPaymentRequest,
]


class WhatIfAssumption(BaseModel):
    description: str


class WhatIfWarning(BaseModel):
    severity: str
    message: str


class WhatIfProjectionPoint(BaseModel):
    month_number: int
    month_label: str
    baseline_net_flow: Decimal
    scenario_net_flow: Decimal
    baseline_balance: Decimal
    scenario_balance: Decimal


class WhatIfResult(BaseModel):
    scenario_type: str
    scenario_label: str
    currency: str
    months: int
    starting_balance: Decimal
    baseline_monthly_net_flow: Decimal
    scenario_monthly_net_flow: Decimal
    total_impact: Decimal
    ending_balance_baseline: Decimal
    ending_balance_scenario: Decimal
    confidence: str
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    monthly_projections: List[WhatIfProjectionPoint]
    impact_metrics: dict[str, str]
    narrative: str


class WhatIfSimulationResponse(BaseModel):
    result: WhatIfResult
    disclaimer: str


class WhatIfCompareRequest(BaseModel):
    scenarios: List[WhatIfScenarioRequest] = Field(..., min_length=2, max_length=5)
    include_narrative: bool = False


class WhatIfCompareResponse(BaseModel):
    results: List[WhatIfResult]
    summary: dict[str, Any]
    disclaimer: str
