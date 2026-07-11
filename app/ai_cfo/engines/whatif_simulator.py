"""Deterministic What-If simulator for the AI Personal CFO.

The simulator is read-only: it never writes transactions, journal entries,
accounts, goals, bills, or subscriptions. It projects the impact of a user
scenario using aggregated historical cash flow and current balance data, then
optionally asks the LLM for a short narrative summary.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import what_if_structured_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import Account, Bill, Goal, JournalEntry, JournalLine, Subscription, User


class WhatIfError(Exception):
    """Raised when a scenario cannot be simulated."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WhatIfScenarioType(str, enum.Enum):
    INCREASE_MONTHLY_SAVINGS = "increase_monthly_savings"
    REDUCE_EXPENSE_CATEGORY = "reduce_expense_category"
    INCOME_INCREASE = "income_increase"
    EMERGENCY_EXPENSE = "emergency_expense"
    CANCEL_SUBSCRIPTION = "cancel_subscription"
    GOAL_CONTRIBUTION_INCREASE = "goal_contribution_increase"
    NEW_MONTHLY_PAYMENT = "new_monthly_payment"


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class FinancialSnapshot:
    """Aggregated financial picture used for projections."""

    total_assets: Decimal
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    avg_monthly_net_flow: Decimal
    currency: str


def _signed_balance(account_type: str, debit_sum: Decimal, credit_sum: Decimal) -> Decimal:
    """Return the normal-balance signed amount for an account."""
    if account_type in ("Asset", "Expense"):
        return debit_sum - credit_sum
    return credit_sum - debit_sum


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _monthly_equivalent(amount: Decimal, frequency: str) -> Decimal:
    """Convert a subscription/bill amount to a monthly amount."""
    freq = (frequency or "monthly").lower()
    if freq == "monthly":
        return amount
    if freq == "yearly":
        return amount / Decimal("12")
    if freq == "weekly":
        return amount * Decimal("52") / Decimal("12")
    if freq == "daily":
        return amount * Decimal("30")
    if freq == "quarterly":
        return amount / Decimal("3")
    return amount


class WhatIfSimulator:
    """Read-only what-if scenario simulator."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        user: Optional[User] = None,
        settings: Optional[Settings] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self.settings = settings or get_settings()
        self.safety = SafetyFilter()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    async def load_snapshot(self) -> FinancialSnapshot:
        """Load current assets and average monthly income/expense."""
        total_assets = await self._total_assets()
        avg_monthly_income = await self._avg_monthly_flow("Income")
        avg_monthly_expenses = await self._avg_monthly_flow("Expense")
        return FinancialSnapshot(
            total_assets=total_assets,
            avg_monthly_income=avg_monthly_income,
            avg_monthly_expenses=avg_monthly_expenses,
            avg_monthly_net_flow=avg_monthly_income - avg_monthly_expenses,
            currency=self._currency(),
        )

    async def _total_assets(self) -> Decimal:
        result = await self.db.execute(
            select(
                Account.account_type,
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            )
            .join(JournalLine, JournalLine.account_id == Account.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Asset")
            .group_by(Account.account_type)
        )
        rows = result.all()
        total = Decimal("0")
        for account_type, debit_sum, credit_sum in rows:
            total += _signed_balance(account_type, _to_decimal(debit_sum), _to_decimal(credit_sum))
        return total

    async def _avg_monthly_flow(self, account_type: str, lookback_months: int = 3) -> Decimal:
        since = date.today() - timedelta(days=30 * lookback_months)
        if account_type == "Income":
            aggregate = func.coalesce(func.sum(JournalLine.credit), Decimal("0"))
        else:
            aggregate = func.coalesce(func.sum(JournalLine.debit), Decimal("0"))

        result = await self.db.execute(
            select(aggregate)
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == account_type)
            .where(JournalEntry.date >= since)
        )
        total = _to_decimal(result.scalar())
        return total / Decimal(str(lookback_months))

    async def _account_balance(self, account_id: int) -> Decimal:
        result = await self.db.execute(
            select(Account.account_type, Account.tenant_id)
            .where(Account.id == account_id)
        )
        row = result.one_or_none()
        if row is None or row.tenant_id != self.tenant_id:
            raise WhatIfError("Account not found in tenant", 404)

        agg = await self.db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            )
            .where(JournalLine.account_id == account_id)
        )
        debit_sum, credit_sum = agg.one()
        return _signed_balance(row.account_type, _to_decimal(debit_sum), _to_decimal(credit_sum))

    def _currency(self) -> str:
        if self.user and getattr(self.user, "currency", None):
            return self.user.currency
        return self.settings.CURRENCY_DEFAULT

    # ------------------------------------------------------------------
    # Tenant/family permission helpers
    # ------------------------------------------------------------------
    async def _validate_account(self, account_id: Optional[int], permission: str = "view") -> Optional[Account]:
        if account_id is None:
            return None
        result = await self.db.execute(
            select(Account).where(Account.id == account_id, Account.tenant_id == self.tenant_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise WhatIfError("Account not found in tenant", 404)

        if self.user is not None:
            from app.services.family_account_access_service import FamilyAccountAccessService

            access = FamilyAccountAccessService(self.db, self.tenant_id, self.user)
            if permission == "use":
                allowed = await access.can_use_account_for_posting(account)
            else:
                allowed = await access.can_view_account(account)
            if not allowed:
                raise WhatIfError("You do not have permission to use this account", 403)

        return account

    async def _validate_subscription(self, subscription_id: int) -> Subscription:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.tenant_id == self.tenant_id,
            )
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            raise WhatIfError("Subscription not found in tenant", 404)
        return subscription

    async def _validate_goal(self, goal_id: int) -> Goal:
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if goal is None:
            raise WhatIfError("Goal not found in tenant", 404)

        if self.user is not None:
            from app.services.family_goal_service import FamilyGoalService

            goal_service = FamilyGoalService(self.db, self.tenant_id, self.user)
            if not await goal_service.can_view_goal(goal):
                raise WhatIfError("You do not have permission to view this goal", 403)

        return goal

    # ------------------------------------------------------------------
    # Scenario simulation
    # ------------------------------------------------------------------
    async def simulate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run a single what-if scenario and return a serializable result."""
        scenario_type = request.get("scenario_type")
        if scenario_type not in {t.value for t in WhatIfScenarioType}:
            raise WhatIfError(f"Unsupported scenario type: {scenario_type}")

        snapshot = await self.load_snapshot()
        months = int(request.get("months", 12))
        if months < 1 or months > 120:
            raise WhatIfError("months must be between 1 and 120")

        handler = {
            WhatIfScenarioType.INCREASE_MONTHLY_SAVINGS.value: self._simulate_increase_savings,
            WhatIfScenarioType.REDUCE_EXPENSE_CATEGORY.value: self._simulate_reduce_expense,
            WhatIfScenarioType.INCOME_INCREASE.value: self._simulate_income_increase,
            WhatIfScenarioType.EMERGENCY_EXPENSE.value: self._simulate_emergency_expense,
            WhatIfScenarioType.CANCEL_SUBSCRIPTION.value: self._simulate_cancel_subscription,
            WhatIfScenarioType.GOAL_CONTRIBUTION_INCREASE.value: self._simulate_goal_contribution,
            WhatIfScenarioType.NEW_MONTHLY_PAYMENT.value: self._simulate_new_payment,
        }[scenario_type]

        result = await handler(snapshot, months, request)

        if request.get("include_narrative"):
            result["narrative"] = await self._generate_narrative(result)
        else:
            result["narrative"] = self._deterministic_narrative(result)

        return result

    async def simulate_many(
        self, requests: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Run several scenarios for side-by-side comparison."""
        results = []
        for req in requests:
            results.append(await self.simulate(req))
        return results

    # ------------------------------------------------------------------
    # Individual scenario handlers
    # ------------------------------------------------------------------
    async def _simulate_increase_savings(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        extra = _to_decimal(request.get("monthly_extra_savings", 0))
        if extra <= 0:
            raise WhatIfError("monthly_extra_savings must be positive")

        target_account_id = request.get("target_account_id")
        await self._validate_account(target_account_id)

        goal_id = request.get("goal_id")
        goal = await self._validate_goal(goal_id) if goal_id else None

        delta = extra
        projections = self._build_projections(snapshot, months, delta_per_month=delta)
        total_impact = extra * Decimal(str(months))

        impact_metrics: dict[str, str] = {
            "monthly_extra_savings": str(extra),
            "total_extra_savings": str(total_impact),
        }
        if goal is not None:
            impact_metrics.update(self._goal_impact_metrics(goal, extra))

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.INCREASE_MONTHLY_SAVINGS.value,
            label="Increase monthly savings",
            snapshot=snapshot,
            months=months,
            delta_per_month=delta,
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "Extra savings are fully retained (not spent).",
                "Historical income/expense averages from the last 90 days continue.",
            ],
            impact_metrics=impact_metrics,
        )

    async def _simulate_reduce_expense(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        reduction_amount = request.get("monthly_reduction_amount")
        reduction_percent = request.get("reduction_percent")
        expense_account_id = request.get("expense_account_id")

        baseline_expense = snapshot.avg_monthly_expenses
        if reduction_amount is not None:
            reduction = _to_decimal(reduction_amount)
        elif reduction_percent is not None:
            reduction = baseline_expense * (_to_decimal(reduction_percent) / Decimal("100"))
        else:
            raise WhatIfError("Provide monthly_reduction_amount or reduction_percent")

        if reduction <= 0:
            raise WhatIfError("Reduction must be positive")
        if expense_account_id is not None:
            await self._validate_account(expense_account_id)

        delta = reduction
        projections = self._build_projections(snapshot, months, delta_per_month=delta)
        total_impact = reduction * Decimal(str(months))

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.REDUCE_EXPENSE_CATEGORY.value,
            label="Reduce expense category",
            snapshot=snapshot,
            months=months,
            delta_per_month=delta,
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "Reduced spending is fully retained as additional cash flow.",
                "Historical income/expense averages from the last 90 days continue.",
            ],
            impact_metrics={
                "monthly_reduction": str(reduction),
                "total_reduction_over_period": str(total_impact),
            },
        )

    async def _simulate_income_increase(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        increase_amount = request.get("monthly_income_increase")
        percent_increase = request.get("percent_increase")

        baseline_income = snapshot.avg_monthly_income
        if increase_amount is not None:
            increase = _to_decimal(increase_amount)
        elif percent_increase is not None:
            increase = baseline_income * (_to_decimal(percent_increase) / Decimal("100"))
        else:
            raise WhatIfError("Provide monthly_income_increase or percent_increase")

        if increase <= 0:
            raise WhatIfError("Income increase must be positive")

        delta = increase
        projections = self._build_projections(snapshot, months, delta_per_month=delta)
        total_impact = increase * Decimal(str(months))

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.INCOME_INCREASE.value,
            label="Income increase",
            snapshot=snapshot,
            months=months,
            delta_per_month=delta,
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "The income increase applies every month and is fully retained.",
                "Taxes and deductions are not modeled.",
            ],
            impact_metrics={
                "monthly_income_increase": str(increase),
                "total_extra_income": str(total_impact),
            },
        )

    async def _simulate_emergency_expense(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        amount = _to_decimal(request.get("amount", 0))
        if amount <= 0:
            raise WhatIfError("amount must be positive")
        month_number = int(request.get("month_number", 1))
        if month_number < 1 or month_number > months:
            raise WhatIfError(f"month_number must be between 1 and {months}")
        source_account_id = request.get("source_account_id")
        await self._validate_account(source_account_id, permission="use")

        one_time_deltas = {month_number: -amount}
        projections = self._build_projections(
            snapshot, months, delta_per_month=Decimal("0"), one_time_deltas=one_time_deltas
        )

        # Total impact is just the one-time outflow; ending balance reflects it.
        total_impact = -amount
        source_balance = await self._account_balance(source_account_id) if source_account_id else snapshot.total_assets

        warnings = []
        if source_balance < amount:
            warnings.append({
                "severity": "high",
                "message": f"The source account balance ({source_balance}) may not cover the emergency expense ({amount}).",
            })

        month_point = projections[month_number - 1]
        if month_point["scenario_balance"] < 0:
            warnings.append({
                "severity": "high",
                "message": "This scenario projects a negative balance after the emergency expense.",
            })

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.EMERGENCY_EXPENSE.value,
            label="Emergency expense",
            snapshot=snapshot,
            months=months,
            delta_per_month=Decimal("0"),
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "The emergency expense is a one-time outflow.",
                "Source account balance is based on current ledger balances.",
            ],
            warnings=warnings,
            impact_metrics={
                "emergency_amount": str(amount),
                "month_number": str(month_number),
                "source_account_balance": str(source_balance),
            },
        )

    async def _simulate_cancel_subscription(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        subscription_id = request.get("subscription_id")
        if subscription_id is None:
            raise WhatIfError("subscription_id is required")
        subscription = await self._validate_subscription(subscription_id)
        monthly_amount = _monthly_equivalent(_to_decimal(subscription.amount), subscription.frequency)

        delta = monthly_amount
        projections = self._build_projections(snapshot, months, delta_per_month=delta)
        total_impact = monthly_amount * Decimal(str(months))

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.CANCEL_SUBSCRIPTION.value,
            label=f"Cancel subscription: {subscription.name}",
            snapshot=snapshot,
            months=months,
            delta_per_month=delta,
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                f"Subscription '{subscription.name}' is cancelled immediately.",
                "The freed-up cash flow is fully retained.",
            ],
            impact_metrics={
                "subscription_monthly_amount": str(monthly_amount),
                "subscription_frequency": subscription.frequency,
                "total_savings": str(total_impact),
            },
        )

    async def _simulate_goal_contribution(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        goal_id = request.get("goal_id")
        if goal_id is None:
            raise WhatIfError("goal_id is required")
        goal = await self._validate_goal(goal_id)
        extra = _to_decimal(request.get("monthly_extra_contribution", 0))
        if extra <= 0:
            raise WhatIfError("monthly_extra_contribution must be positive")

        current_monthly = _to_decimal(goal.monthly_contribution)
        new_monthly = current_monthly + extra
        target = _to_decimal(goal.target_amount)
        current = _to_decimal(goal.current_amount)
        remaining = target - current

        baseline_months = remaining / current_monthly if current_monthly > 0 else None
        new_months = remaining / new_monthly if new_monthly > 0 else None
        months_saved = None
        if baseline_months is not None and new_months is not None:
            months_saved = baseline_months - new_months

        projected_extra = extra * Decimal(str(months))
        projected_progress = (current + projected_extra) / target * Decimal("100") if target > 0 else Decimal("0")

        # Net flow impact is zero because this is a reallocation.
        projections = self._build_projections(snapshot, months, delta_per_month=Decimal("0"))
        total_impact = Decimal("0")

        impact_metrics = {
            "goal_name": goal.name,
            "current_monthly_contribution": str(current_monthly),
            "new_monthly_contribution": str(new_monthly),
            "projected_extra_over_period": str(projected_extra),
            "projected_progress_percent": f"{projected_progress:.2f}",
        }
        if baseline_months is not None:
            impact_metrics["baseline_months_to_goal"] = f"{baseline_months:.2f}"
        if new_months is not None:
            impact_metrics["new_months_to_goal"] = f"{new_months:.2f}"
        if months_saved is not None:
            impact_metrics["months_saved"] = f"{months_saved:.2f}"

        warnings = []
        if snapshot.avg_monthly_net_flow < Decimal("0") and extra > snapshot.avg_monthly_net_flow.abs():
            warnings.append({
                "severity": "medium",
                "message": "Your current average net cash flow is negative; extra contributions may require drawing down savings.",
            })

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.GOAL_CONTRIBUTION_INCREASE.value,
            label=f"Increase contribution to goal: {goal.name}",
            snapshot=snapshot,
            months=months,
            delta_per_month=Decimal("0"),
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "The extra contribution is a reallocation of existing cash flow.",
                "Goal progress does not account for investment returns or market changes.",
            ],
            warnings=warnings,
            impact_metrics=impact_metrics,
        )

    async def _simulate_new_payment(
        self, snapshot: FinancialSnapshot, months: int, request: dict[str, Any]
    ) -> dict[str, Any]:
        down_payment = _to_decimal(request.get("down_payment", 0))
        monthly_payment = _to_decimal(request.get("monthly_payment", 0))
        if monthly_payment <= 0:
            raise WhatIfError("monthly_payment must be positive")

        one_time_deltas = {}
        if down_payment > 0:
            one_time_deltas[1] = -down_payment

        delta = -monthly_payment
        projections = self._build_projections(
            snapshot, months, delta_per_month=delta, one_time_deltas=one_time_deltas
        )
        total_impact = -(down_payment + monthly_payment * Decimal(str(months)))

        warnings = []
        ending_balance = projections[-1]["scenario_balance"]
        three_month_expenses = snapshot.avg_monthly_expenses * Decimal("3")
        if ending_balance < three_month_expenses:
            warnings.append({
                "severity": "high",
                "message": "This payment could leave your projected balance below a 3-month expense emergency reserve.",
            })
        if ending_balance < 0:
            warnings.append({
                "severity": "high",
                "message": "This payment projects a negative balance during the period.",
            })

        return self._assemble_result(
            scenario_type=WhatIfScenarioType.NEW_MONTHLY_PAYMENT.value,
            label="New monthly payment",
            snapshot=snapshot,
            months=months,
            delta_per_month=delta,
            total_impact=total_impact,
            projections=projections,
            assumptions=[
                "Down payment (if any) occurs in month 1.",
                "Monthly payment continues for the full projection period.",
                "No financing interest, fees, or resale value is modeled.",
            ],
            warnings=warnings,
            impact_metrics={
                "down_payment": str(down_payment),
                "monthly_payment": str(monthly_payment),
                "total_outflow": str(-total_impact),
                "projected_ending_balance": str(ending_balance),
            },
        )

    # ------------------------------------------------------------------
    # Projection builder
    # ------------------------------------------------------------------
    def _build_projections(
        self,
        snapshot: FinancialSnapshot,
        months: int,
        delta_per_month: Decimal,
        one_time_deltas: Optional[dict[int, Decimal]] = None,
    ) -> list[dict[str, Any]]:
        one_time_deltas = one_time_deltas or {}
        baseline_balance = snapshot.total_assets
        scenario_balance = snapshot.total_assets
        projections = []
        today = date.today()
        for month in range(1, months + 1):
            month_delta = one_time_deltas.get(month, Decimal("0"))
            baseline_net = snapshot.avg_monthly_net_flow
            scenario_net = baseline_net + delta_per_month + month_delta
            baseline_balance += baseline_net
            scenario_balance += scenario_net
            projections.append({
                "month_number": month,
                "month_label": (today + timedelta(days=30 * month)).strftime("%Y-%m"),
                "baseline_net_flow": baseline_net,
                "scenario_net_flow": scenario_net,
                "baseline_balance": baseline_balance,
                "scenario_balance": scenario_balance,
            })
        return projections

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------
    def _assemble_result(
        self,
        scenario_type: str,
        label: str,
        snapshot: FinancialSnapshot,
        months: int,
        delta_per_month: Decimal,
        total_impact: Decimal,
        projections: list[dict[str, Any]],
        assumptions: list[str],
        impact_metrics: dict[str, str],
        warnings: Optional[list[dict[str, str]]] = None,
    ) -> dict[str, Any]:
        warnings = warnings or []
        baseline_monthly_net = snapshot.avg_monthly_net_flow
        scenario_monthly_net = baseline_monthly_net + delta_per_month

        # Confidence is lower when we have little historical data.
        confidence = Confidence.HIGH
        if snapshot.avg_monthly_income == 0 and snapshot.avg_monthly_expenses == 0:
            confidence = Confidence.LOW
            warnings.append({
                "severity": "medium",
                "message": "No recent income or expense history was found; projections are highly uncertain.",
            })
        elif snapshot.avg_monthly_income == 0 or snapshot.avg_monthly_expenses == 0:
            confidence = Confidence.MEDIUM

        # Generic warning for negative projected ending balance.
        if projections and projections[-1]["scenario_balance"] < 0:
            if not any("negative balance" in w["message"].lower() for w in warnings):
                warnings.append({
                    "severity": "high",
                    "message": "The scenario projects a negative ending balance.",
                })

        # Disclaimer is always added by the router layer, but include a marker here.
        return {
            "scenario_type": scenario_type,
            "scenario_label": label,
            "currency": snapshot.currency,
            "months": months,
            "starting_balance": snapshot.total_assets,
            "baseline_monthly_net_flow": baseline_monthly_net,
            "scenario_monthly_net_flow": scenario_monthly_net,
            "total_impact": total_impact,
            "ending_balance_baseline": projections[-1]["baseline_balance"],
            "ending_balance_scenario": projections[-1]["scenario_balance"],
            "confidence": confidence.value,
            "assumptions": [{"description": a} for a in assumptions],
            "warnings": warnings,
            "monthly_projections": projections,
            "impact_metrics": impact_metrics,
            "narrative": "",
        }

    # ------------------------------------------------------------------
    # Goal helpers
    # ------------------------------------------------------------------
    def _goal_impact_metrics(self, goal: Goal, extra_monthly: Decimal) -> dict[str, str]:
        target = _to_decimal(goal.target_amount)
        current = _to_decimal(goal.current_amount)
        current_monthly = _to_decimal(goal.monthly_contribution)
        new_monthly = current_monthly + extra_monthly
        remaining = target - current

        metrics: dict[str, str] = {"linked_goal": goal.name}
        if current_monthly > 0:
            baseline_months = remaining / current_monthly
            metrics["baseline_months_to_goal"] = f"{baseline_months:.2f}"
        if new_monthly > 0:
            new_months = remaining / new_monthly
            metrics["new_months_to_goal"] = f"{new_months:.2f}"
            if current_monthly > 0:
                months_saved = (remaining / current_monthly) - new_months
                metrics["months_saved"] = f"{months_saved:.2f}"
        return metrics

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------
    def _deterministic_narrative(self, result: dict[str, Any]) -> str:
        lines = [
            f"Scenario: {result['scenario_label']}.",
            f"Over {result['months']} months, the projected impact is {result['total_impact']} {result['currency']}.",
            f"Baseline ending balance: {result['ending_balance_baseline']} {result['currency']}.",
            f"Scenario ending balance: {result['ending_balance_scenario']} {result['currency']}.",
        ]
        if result["warnings"]:
            lines.append("Warnings:")
            for warning in result["warnings"]:
                lines.append(f"- {warning['message']}")
        lines.append("Assumptions:")
        for assumption in result["assumptions"]:
            lines.append(f"- {assumption['description']}")
        lines.append(
            "This is an educational projection, not a guarantee of future results."
        )
        return "\n".join(lines)

    async def _generate_narrative(self, result: dict[str, Any]) -> str:
        """Generate a narrative using the LLM when available; otherwise deterministic."""
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, used, limit = await cost_controller.check_limit()
        client = LLMClient()

        if not allowed or not client.is_configured():
            return self._deterministic_narrative(result)

        try:
            response = await client.complete(
                messages=what_if_structured_prompt(result),
                temperature=0.7,
                max_tokens=700,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="what_if",
                user_id=self.user.id if self.user else None,
            )
            return self.safety.sanitize(response.content)
        except LLMError:
            return self._deterministic_narrative(result)
