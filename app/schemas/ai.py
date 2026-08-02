from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional, List, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Confidence scoring fields (AI-1222)
# ---------------------------------------------------------------------------


class ConfidenceFactorSchema(BaseModel):
    name: str
    impact: float
    explanation: str


class ConfidenceFields(BaseModel):
    """Optional confidence fields mixed into AI response schemas.

    All fields are optional so existing clients that don't read them are
    unaffected; engines that don't compute confidence simply omit them.
    """
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_label: Optional[str] = None
    confidence_factors: Optional[List[ConfidenceFactorSchema]] = None
    confidence_explanation: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[int] = None


class ChatResponse(ConfidenceFields):
    answer: str
    confidence: Optional[int] = None
    actions: Optional[List[dict]] = None
    follow_up_questions: Optional[List[str]] = None
    related_insights: Optional[List[str]] = None
    disclaimer: Optional[str] = None
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None
    session_id: Optional[int] = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    tokens_used: Optional[int] = None
    estimated_cost: Optional[float] = None
    model: Optional[str] = None
    created_at: str


class ChatSessionResponse(BaseModel):
    id: int
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int


class ChatSessionsResponse(BaseModel):
    sessions: List[ChatSessionResponse]


class ChatHistoryResponse(BaseModel):
    session_id: int
    title: Optional[str] = None
    messages: List[ChatMessageResponse]


class ChatSuggestedQuestionsResponse(BaseModel):
    questions: List[str]


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    GOAL_CONTEXT = "goal_context"
    RISK_PROFILE = "risk_profile"
    BEHAVIOR_PATTERN = "behavior_pattern"
    DISMISSED_ADVICE = "dismissed_advice"
    CUSTOM = "custom"


class MemorySource(str, Enum):
    EXPLICIT_USER_STATEMENT = "explicit_user_statement"
    CHAT_INFERRED = "chat_inferred"
    SYSTEM_GENERATED = "system_generated"


class MemoryCreate(BaseModel):
    memory_type: MemoryType = MemoryType.CUSTOM
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=2000)
    summary: Optional[str] = Field(None, max_length=255)
    source: MemorySource = MemorySource.EXPLICIT_USER_STATEMENT
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_sensitive: bool = False
    expires_at: Optional[str] = None


class MemoryUpdate(BaseModel):
    value: Optional[str] = Field(None, min_length=1, max_length=2000)
    summary: Optional[str] = Field(None, max_length=255)
    memory_type: Optional[MemoryType] = None
    is_active: Optional[bool] = None
    is_sensitive: Optional[bool] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    expires_at: Optional[str] = None


class MemoryResponse(BaseModel):
    id: int
    memory_type: str
    key: str
    value: str
    summary: Optional[str] = None
    source: str
    confidence_score: Optional[float] = None
    is_active: bool
    is_sensitive: bool
    expires_at: Optional[str] = None
    deleted_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_at: str
    updated_at: str


class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse]


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(20, ge=1, le=100)


class MemorySearchResponse(BaseModel):
    memories: List[MemoryResponse]


class MemoryExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class MemoryExtractCandidate(BaseModel):
    memory_type: str
    key: str
    value: str
    summary: Optional[str] = None
    source: str
    confidence_score: Optional[float] = None


class MemoryExtractResponse(BaseModel):
    candidates: List[MemoryExtractCandidate]


class MemoryForgetRequest(BaseModel):
    query: Optional[str] = Field(None, min_length=1, max_length=200)
    memory_id: Optional[int] = None


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


class WhatIfResult(ConfidenceFields):
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


class DebtOptimizerResult(ConfidenceFields):
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


class EmergencyFundResult(ConfidenceFields):
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


class SavingsCapacityResult(ConfidenceFields):
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


class GoalAllocationResult(ConfidenceFields):
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


class ReduceSpendingResult(ConfidenceFields):
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


class CompareStrategiesResult(ConfidenceFields):
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


# ---------------------------------------------------------------------------
# Goal Planner schemas (AI-1213)
# ---------------------------------------------------------------------------


class GoalPlannerModeMeta(BaseModel):
    mode: str
    label: str
    description: str


class GoalPlannerStrategyMeta(BaseModel):
    strategy: str
    label: str
    description: str


class GoalPlanItem(ConfidenceFields):
    goal_id: int
    goal_name: str
    target_amount: Decimal
    current_amount: Decimal
    remaining_amount: Decimal
    monthly_contribution: Decimal
    required_monthly_contribution: Optional[Decimal] = None
    months_to_completion: Optional[int] = None
    projected_completion_date: Optional[str] = None
    target_date: Optional[str] = None
    on_track: bool
    deadline_risk: str
    progress_percent: str
    priority: int
    warnings: List[WhatIfWarning]


class GoalPlannerRequest(BaseModel):
    mode: Literal[
        "single_goal_feasibility",
        "hypothetical_goal",
        "multi_goal_prioritization",
        "deadline_rescue",
        "family_goal_plan",
    ]
    months: int = Field(12, ge=1, le=120)
    include_narrative: bool = False
    goal_id: Optional[int] = None
    target_amount: Optional[Decimal] = Field(None, gt=0)
    current_amount: Optional[Decimal] = Field(None, ge=0)
    target_date: Optional[str] = None
    monthly_contribution: Optional[Decimal] = Field(None, gt=0)
    goal_name: Optional[str] = None
    goal_ids: Optional[List[int]] = None
    strategy: Literal["equal_split", "priority_first", "closest_deadline", "lowest_gap_first"] = "equal_split"
    available_monthly_savings: Optional[Decimal] = Field(None, gt=0)
    family_id: Optional[int] = None
    monthly_family_contribution: Optional[Decimal] = Field(None, gt=0)


class HypotheticalGoalResult(ConfidenceFields):
    mode: str
    currency: str
    goal_name: str
    target_amount: Decimal
    current_amount: Decimal
    remaining_amount: Decimal
    target_date: Optional[str] = None
    monthly_contribution: Optional[Decimal] = None
    required_monthly_contribution: Optional[Decimal] = None
    months_to_completion: Optional[int] = None
    projected_completion_date: Optional[str] = None
    on_track: bool
    deadline_risk: str
    feasibility: str
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class SingleGoalFeasibilityResult(ConfidenceFields):
    mode: str
    currency: str
    goal: GoalPlanItem
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class MultiGoalPrioritizationResult(ConfidenceFields):
    mode: str
    currency: str
    strategy: str
    available_monthly_savings: Decimal
    total_allocated: Decimal
    unallocated: Decimal
    goal_count: int
    goals: List[GoalPlanItem]
    goals_at_risk: List[int]
    total_funding_gap: Decimal
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class DeadlineRescueOption(BaseModel):
    option: str
    description: str
    new_monthly_contribution: Optional[Decimal] = None
    suggested_target: Optional[Decimal] = None


class DeadlineRescueResult(ConfidenceFields):
    mode: str
    currency: str
    goal_id: int
    goal_name: str
    target_date: str
    target_amount: Decimal
    current_amount: Decimal
    remaining_amount: Decimal
    current_monthly_contribution: Decimal
    required_monthly_contribution: Decimal
    shortfall: Decimal
    months_to_target: int
    options: List[DeadlineRescueOption]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class FamilyGoalPlanResult(ConfidenceFields):
    mode: str
    currency: str
    family_id: Optional[int] = None
    monthly_family_contribution: Decimal
    total_allocated: Decimal
    goal_count: int
    goals: List[GoalPlanItem]
    assumptions: List[WhatIfAssumption]
    warnings: List[WhatIfWarning]
    confidence: str
    narrative: str


class GoalPlannerResponse(BaseModel):
    result: Union[
        SingleGoalFeasibilityResult,
        HypotheticalGoalResult,
        MultiGoalPrioritizationResult,
        DeadlineRescueResult,
        FamilyGoalPlanResult,
    ]
    disclaimer: str


class GoalPrioritizeRequest(BaseModel):
    months: int = Field(12, ge=1, le=120)
    include_narrative: bool = False
    goal_ids: Optional[List[int]] = None
    strategy: Literal["equal_split", "priority_first", "closest_deadline", "lowest_gap_first"] = "equal_split"
    available_monthly_savings: Decimal = Field(..., gt=0)


class GoalPrioritizeResponse(BaseModel):
    result: MultiGoalPrioritizationResult
    disclaimer: str


# ---------------------------------------------------------------------------
# Proactive Alerts schemas (AI-1219)
# ---------------------------------------------------------------------------


class ProactiveAlertTypeMeta(BaseModel):
    alert_type: str
    label: str
    description: str
    default_severity: str


class ProactiveAlertCandidateSchema(ConfidenceFields):
    alert_type: str
    severity: str
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None


class ProactiveAlertRunRequest(BaseModel):
    include_llm_wording: bool = False


class ProactiveAlertRunResponse(BaseModel):
    created: int
    skipped: int
    candidates: int


class ProactiveAlertPreviewResponse(BaseModel):
    candidates: List[ProactiveAlertCandidateSchema]


# ---------------------------------------------------------------------------
# Confidence rules schema (AI-1222)
# ---------------------------------------------------------------------------


class ConfidenceRulesResponse(BaseModel):
    score_range: dict[str, float]
    thresholds: dict[str, float]
    base_score: float
    labels: List[str]
    positive_factors: List[ConfidenceFactorSchema]
    negative_factors: List[ConfidenceFactorSchema]
