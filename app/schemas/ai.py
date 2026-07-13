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


# ---------------------------------------------------------------------------
# Debt Optimizer schemas (AI-1211)
# ---------------------------------------------------------------------------


class DebtOptimizerDebtItem(BaseModel):
    id: int
    name: str
    source: str
    balance: Decimal
    annual_rate: Decimal
    minimum_payment: Decimal
    payoff_month: Optional[int] = None


class DebtOptimizerMonth(BaseModel):
    month_number: int
    total_paid: Decimal
    total_interest: Decimal
    total_principal: Decimal
    remaining_balance: Decimal


class DebtOptimizerRequest(BaseModel):
    strategy: Literal["avalanche", "snowball", "custom_order"] = "avalanche"
    extra_monthly_payment: Decimal = Field(Decimal("0"), ge=0)
    loan_ids: Optional[List[int]] = None
    account_ids: Optional[List[int]] = None
    custom_order: Optional[List[int]] = None
    include_narrative: bool = False


class DebtOptimizerResult(BaseModel):
    strategy: str
    currency: str
    total_balance: Decimal
    total_minimum_payment: Decimal
    extra_monthly_payment: Decimal
    debt_to_income_ratio: Optional[str] = None
    payoff_months: int
    baseline_months: int
    months_saved: int
    total_paid: Decimal
    total_interest: Decimal
    baseline_total_interest: Decimal
    interest_saved: Decimal
    debt_count: int
    payoff_order: List[DebtOptimizerDebtItem]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    monthly_schedule: List[DebtOptimizerMonth]
    narrative: str


class DebtOptimizerResponse(BaseModel):
    result: DebtOptimizerResult
    disclaimer: str


class DebtOptimizerCompareResponse(BaseModel):
    results: List[DebtOptimizerResult]
    recommendation: str
    disclaimer: str


# ---------------------------------------------------------------------------
# Savings Optimizer schemas (AI-1212)
# ---------------------------------------------------------------------------


class SavingsOptimizerStrategyMeta(BaseModel):
    mode: str
    label: str
    description: str


class SavingsOptimizerRequest(BaseModel):
    mode: Literal[
        "emergency_fund",
        "savings_capacity",
        "goal_allocation",
        "reduce_spending",
        "compare_strategies",
    ]
    months: int = Field(12, ge=1, le=120)
    include_narrative: bool = False
    target_months_of_expenses: Optional[Decimal] = Field(None, ge=0)
    monthly_contribution: Optional[Decimal] = Field(None, ge=0)
    account_id: Optional[int] = None
    target_savings_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    monthly_available_savings: Optional[Decimal] = Field(None, gt=0)
    strategy: Literal["equal_split", "priority_first", "closest_deadline", "lowest_gap_first"] = "equal_split"
    goal_ids: Optional[List[int]] = None
    target_monthly_savings: Optional[Decimal] = Field(None, gt=0)


class SavingsProjectionMonth(BaseModel):
    month_number: int
    month_label: str
    balance: Decimal
    cumulative_savings: Decimal
    monthly_addition: Decimal


class SavingsGoalAllocationItem(BaseModel):
    goal_id: int
    goal_name: str
    target_amount: Decimal
    current_amount: Decimal
    remaining_amount: Decimal
    monthly_contribution: Decimal
    recommended_allocation: Decimal
    new_monthly_contribution: Decimal
    projected_progress_percent: str
    months_to_completion: Optional[int] = None
    priority: int
    target_date: Optional[str] = None


class EmergencyFundResult(BaseModel):
    mode: str
    currency: str
    target_months_of_expenses: str
    monthly_expenses: Decimal
    target_amount: Decimal
    current_savings: Decimal
    gap_amount: Decimal
    months_to_target: Optional[int] = None
    monthly_contribution: Decimal
    risk_level: str
    projected_emergency_balance: Decimal
    monthly_projections: List[SavingsProjectionMonth]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class SavingsCapacityResult(BaseModel):
    mode: str
    currency: str
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    avg_monthly_net_flow: Decimal
    current_savings_rate_percent: str
    target_savings_rate_percent: Optional[str] = None
    target_monthly_savings: Optional[Decimal] = None
    savings_gap: Optional[Decimal] = None
    suggested_monthly_savings_min: Decimal
    suggested_monthly_savings_max: Decimal
    projected_total_savings: Decimal
    monthly_projections: List[SavingsProjectionMonth]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class GoalAllocationResult(BaseModel):
    mode: str
    currency: str
    strategy: str
    monthly_available_savings: Decimal
    total_allocated: Decimal
    unallocated: Decimal
    goal_count: int
    goals: List[SavingsGoalAllocationItem]
    projected_total_progress: Decimal
    monthly_projections: List[SavingsProjectionMonth]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class ReduceSpendingResult(BaseModel):
    mode: str
    currency: str
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    target_monthly_savings: Decimal
    current_monthly_savings_capacity: Decimal
    required_spending_reduction: Decimal
    expense_reduction_candidates: List[dict[str, Any]]
    projected_total_savings: Decimal
    monthly_projections: List[SavingsProjectionMonth]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class StrategyComparisonItem(BaseModel):
    strategy: str
    total_allocated: Decimal
    unallocated: Decimal
    projected_total_progress: Decimal
    goal_count: int


class CompareStrategiesResult(BaseModel):
    mode: str
    currency: str
    monthly_available_savings: Decimal
    goal_count: int
    strategies: List[StrategyComparisonItem]
    recommended_strategy: str
    recommendation: str
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class SavingsOptimizerResponse(BaseModel):
    result: Union[
        EmergencyFundResult,
        SavingsCapacityResult,
        GoalAllocationResult,
        ReduceSpendingResult,
        CompareStrategiesResult,
    ]
    disclaimer: str


class SavingsOptimizerCompareResponse(BaseModel):
    result: CompareStrategiesResult
    disclaimer: str
