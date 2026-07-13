"""Deterministic Savings Optimizer for the AI Personal CFO.

The optimizer is read-only: it never writes transfers, journal entries, accounts,
goals, or budgets. It analyzes cash flow, emergency-fund adequacy, and goal
progress, then recommends savings allocations and timelines. An optional LLM
narrative is generated only when configured and within budget.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import savings_optimizer_structured_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import Account, Goal, GoalStatus, JournalEntry, JournalLine, User


class SavingsOptimizerError(Exception):
    """Raised when a savings optimization cannot be run."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SavingsModeType(str, enum.Enum):
    EMERGENCY_FUND = "emergency_fund"
    SAVINGS_CAPACITY = "savings_capacity"
    GOAL_ALLOCATION = "goal_allocation"
    REDUCE_SPENDING = "reduce_spending"
    COMPARE_STRATEGIES = "compare_strategies"


class AllocationStrategy(str, enum.Enum):
    EQUAL_SPLIT = "equal_split"
    PRIORITY_FIRST = "priority_first"
    CLOSEST_DEADLINE = "closest_deadline"
    LOWEST_GAP_FIRST = "lowest_gap_first"


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class CashFlowSnapshot:
    """Aggregated cash-flow picture used for savings projections."""

    total_assets: Decimal
    avg_monthly_income: Decimal
    avg_monthly_expenses: Decimal
    avg_monthly_net_flow: Decimal
    currency: str


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Any) -> Decimal:
    return _to_decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _signed_balance(account_type: str, debit_sum: Decimal, credit_sum: Decimal) -> Decimal:
    if account_type in ("Asset", "Expense"):
        return debit_sum - credit_sum
    return credit_sum - debit_sum


class SavingsOptimizer:
    """Read-only savings optimizer."""

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
    async def load_snapshot(self) -> CashFlowSnapshot:
        total_assets = await self._total_assets()
        avg_income = await self._avg_monthly_flow("Income")
        avg_expenses = await self._avg_monthly_flow("Expense")
        return CashFlowSnapshot(
            total_assets=total_assets,
            avg_monthly_income=avg_income,
            avg_monthly_expenses=avg_expenses,
            avg_monthly_net_flow=avg_income - avg_expenses,
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
        total = Decimal("0")
        for account_type, debit_sum, credit_sum in result.all():
            total += _signed_balance(
                account_type, _to_decimal(debit_sum), _to_decimal(credit_sum)
            )
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
            select(Account.account_type, Account.tenant_id).where(Account.id == account_id)
        )
        row = result.one_or_none()
        if row is None or row.tenant_id != self.tenant_id:
            raise SavingsOptimizerError("Account not found in tenant", 404)

        agg = await self.db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            ).where(JournalLine.account_id == account_id)
        )
        debit_sum, credit_sum = agg.one()
        return _signed_balance(row.account_type, _to_decimal(debit_sum), _to_decimal(credit_sum))

    def _currency(self) -> str:
        if self.user and getattr(self.user, "currency", None):
            return self.user.currency
        return self.settings.CURRENCY_DEFAULT

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    async def _validate_account(self, account_id: Optional[int]) -> Optional[Account]:
        if account_id is None:
            return None
        result = await self.db.execute(
            select(Account).where(Account.id == account_id, Account.tenant_id == self.tenant_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise SavingsOptimizerError("Account not found in tenant", 404)
        if self.user is not None:
            from app.services.family_account_access_service import FamilyAccountAccessService

            access = FamilyAccountAccessService(self.db, self.tenant_id, self.user)
            if not await access.can_view_account(account):
                raise SavingsOptimizerError("You do not have permission to view this account", 403)
        return account

    async def _validate_goal(self, goal_id: int) -> Goal:
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if goal is None:
            raise SavingsOptimizerError("Goal not found in tenant", 404)
        if self.user is not None:
            from app.services.family_goal_service import FamilyGoalService

            goal_service = FamilyGoalService(self.db, self.tenant_id, self.user)
            if not await goal_service.can_view_goal(goal):
                raise SavingsOptimizerError("You do not have permission to view this goal", 403)
        return goal

    async def _load_visible_goals(self, goal_ids: Optional[list[int]] = None) -> list[Goal]:
        stmt = select(Goal).where(
            Goal.tenant_id == self.tenant_id,
            Goal.status == GoalStatus.ACTIVE.value,
        )
        if goal_ids:
            stmt = stmt.where(Goal.id.in_(goal_ids))
        result = await self.db.execute(stmt)
        goals = list(result.scalars().all())

        visible = []
        for goal in goals:
            if self.user is not None:
                from app.services.family_goal_service import FamilyGoalService

                goal_service = FamilyGoalService(self.db, self.tenant_id, self.user)
                if not await goal_service.can_view_goal(goal):
                    # If the caller explicitly asked for this goal, raise a clear 403.
                    if goal_ids and goal.id in goal_ids:
                        raise SavingsOptimizerError(
                            "You do not have permission to view this goal", 403
                        )
                    continue
            visible.append(goal)
        return visible

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------
    async def optimize(
        self,
        mode: SavingsModeType,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if mode == SavingsModeType.EMERGENCY_FUND:
            return await self._emergency_fund(request)
        if mode == SavingsModeType.SAVINGS_CAPACITY:
            return await self._savings_capacity(request)
        if mode == SavingsModeType.GOAL_ALLOCATION:
            return await self._goal_allocation(request)
        if mode == SavingsModeType.REDUCE_SPENDING:
            return await self._reduce_spending(request)
        if mode == SavingsModeType.COMPARE_STRATEGIES:
            return await self._compare_strategies(request)
        raise SavingsOptimizerError(f"Unsupported savings mode: {mode.value}")

    async def compare(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Convenience wrapper that always runs the strategy comparison mode."""
        return await self._compare_strategies(request)

    # ------------------------------------------------------------------
    # Mode: Emergency fund
    # ------------------------------------------------------------------
    async def _emergency_fund(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        target_months = max(_to_decimal(request.get("target_months_of_expenses", 3)), Decimal("0"))
        monthly_contribution = _to_decimal(request.get("monthly_contribution", 0))
        if monthly_contribution < 0:
            raise SavingsOptimizerError("monthly_contribution cannot be negative")

        account_id = request.get("account_id")
        await self._validate_account(account_id)
        current_savings = await self._account_balance(account_id) if account_id else Decimal("0")

        monthly_expenses = snapshot.avg_monthly_expenses
        target_amount = _money(monthly_expenses * target_months)
        gap_amount = _money(max(target_amount - current_savings, Decimal("0")))

        months_to_target: Optional[int] = None
        if monthly_contribution > 0 and gap_amount > 0:
            months_to_target = math.ceil(float(gap_amount / monthly_contribution))
        elif gap_amount <= 0:
            months_to_target = 0

        risk_level = self._emergency_fund_risk(current_savings, monthly_expenses, target_amount)

        warnings: list[dict[str, str]] = []
        if monthly_expenses == 0:
            warnings.append({
                "severity": "medium",
                "message": "No recent expense history found; emergency fund target is uncertain.",
            })
        if monthly_contribution > 0 and monthly_contribution < monthly_expenses * Decimal("0.05"):
            warnings.append({
                "severity": "low",
                "message": "Monthly contribution is low relative to expenses; reaching the target may take a long time.",
            })

        months = int(request.get("months", 12))
        projections = self._build_projections(current_savings, monthly_contribution, months)

        result = {
            "mode": SavingsModeType.EMERGENCY_FUND.value,
            "currency": snapshot.currency,
            "target_months_of_expenses": str(target_months),
            "monthly_expenses": _money(monthly_expenses),
            "target_amount": target_amount,
            "current_savings": _money(current_savings),
            "gap_amount": gap_amount,
            "months_to_target": months_to_target,
            "monthly_contribution": _money(monthly_contribution),
            "risk_level": risk_level,
            "projected_emergency_balance": projections[-1]["balance"] if projections else _money(current_savings),
            "monthly_projections": projections,
            "assumptions": [
                {"description": "Monthly expenses are based on the 90-day average of posted expenses."},
                {"description": "Contributions are added at the end of each month."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    def _emergency_fund_risk(
        self, current_savings: Decimal, monthly_expenses: Decimal, target_amount: Decimal
    ) -> str:
        if monthly_expenses <= 0:
            return "unknown"
        months_of_expenses = current_savings / monthly_expenses
        if current_savings >= target_amount:
            return "low"
        if months_of_expenses >= Decimal("1"):
            return "medium"
        return "high"

    # ------------------------------------------------------------------
    # Mode: Savings capacity
    # ------------------------------------------------------------------
    async def _savings_capacity(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        target_rate = request.get("target_savings_rate")
        target_savings_rate = _to_decimal(target_rate) if target_rate is not None else None
        months = int(request.get("months", 12))

        income = snapshot.avg_monthly_income
        expenses = snapshot.avg_monthly_expenses
        disposable = income - expenses
        current_rate = Decimal("0")
        if income > 0:
            current_rate = ((income - expenses) / income * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        suggested_min = _money(max(disposable * Decimal("0.20"), Decimal("0")))
        suggested_max = _money(max(disposable * Decimal("0.50"), Decimal("0")))

        warnings: list[dict[str, str]] = []
        if disposable < 0:
            warnings.append({
                "severity": "high",
                "message": "Average monthly expenses exceed income; there is no discretionary savings capacity.",
            })
        elif disposable == 0:
            warnings.append({
                "severity": "medium",
                "message": "Average monthly income equals expenses; any savings will require increasing income or reducing spending.",
            })

        target_monthly_savings: Optional[Decimal] = None
        savings_gap: Optional[Decimal] = None
        if target_savings_rate is not None:
            if target_savings_rate < 0 or target_savings_rate > 100:
                raise SavingsOptimizerError("target_savings_rate must be between 0 and 100")
            target_monthly_savings = _money(income * (target_savings_rate / Decimal("100")))
            savings_gap = _money(max(target_monthly_savings - disposable, Decimal("0")))
            if savings_gap > 0:
                warnings.append({
                    "severity": "medium",
                    "message": f"Target savings rate requires an additional {savings_gap} {snapshot.currency} per month in savings.",
                })

        projections = self._build_projections(
            snapshot.total_assets, suggested_min if disposable > 0 else Decimal("0"), months
        )

        result = {
            "mode": SavingsModeType.SAVINGS_CAPACITY.value,
            "currency": snapshot.currency,
            "avg_monthly_income": _money(income),
            "avg_monthly_expenses": _money(expenses),
            "avg_monthly_net_flow": _money(disposable),
            "current_savings_rate_percent": str(current_rate),
            "target_savings_rate_percent": str(target_savings_rate) if target_savings_rate is not None else None,
            "target_monthly_savings": target_monthly_savings,
            "savings_gap": savings_gap,
            "suggested_monthly_savings_min": suggested_min,
            "suggested_monthly_savings_max": suggested_max,
            "projected_total_savings": projections[-1]["cumulative_savings"] if projections else Decimal("0"),
            "monthly_projections": projections,
            "assumptions": [
                {"description": "Income and expense averages are based on posted journal entries from the last 90 days."},
                {"description": "Suggested savings range assumes 20-50% of disposable income can be saved."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Mode: Goal allocation
    # ------------------------------------------------------------------
    async def _goal_allocation(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        monthly_available = _to_decimal(request.get("monthly_available_savings", 0))
        if monthly_available <= 0:
            raise SavingsOptimizerError("monthly_available_savings must be positive")

        strategy = AllocationStrategy(request.get("strategy", AllocationStrategy.EQUAL_SPLIT.value))
        goal_ids = request.get("goal_ids")
        months = int(request.get("months", 12))

        goals = await self._load_visible_goals(goal_ids)
        if not goals:
            raise SavingsOptimizerError("No visible active goals found for this tenant", 404)

        allocations = self._allocate_to_goals(goals, monthly_available, strategy)
        goal_items = []
        for goal, allocation in allocations:
            target = _to_decimal(goal.target_amount)
            current = _to_decimal(goal.current_amount)
            remaining = max(target - current, Decimal("0"))
            new_monthly = _to_decimal(goal.monthly_contribution) + allocation
            projected_extra = allocation * Decimal(str(months))
            projected_progress = ((current + projected_extra) / target * Decimal("100")) if target > 0 else Decimal("0")
            months_to_completion = None
            if new_monthly > 0 and remaining > 0:
                months_to_completion = math.ceil(float(remaining / new_monthly))
            goal_items.append({
                "goal_id": goal.id,
                "goal_name": goal.name,
                "target_amount": target,
                "current_amount": current,
                "remaining_amount": remaining,
                "monthly_contribution": _to_decimal(goal.monthly_contribution),
                "recommended_allocation": allocation,
                "new_monthly_contribution": new_monthly,
                "projected_progress_percent": f"{projected_progress:.2f}",
                "months_to_completion": months_to_completion,
                "priority": goal.priority,
                "target_date": goal.target_date.isoformat() if goal.target_date else None,
            })

        total_allocated = sum(a for _, a in allocations)
        unallocated = _money(monthly_available - total_allocated)

        projections = self._build_projections(
            sum(_to_decimal(g.current_amount) for g in goals),
            total_allocated,
            months,
        )

        result = {
            "mode": SavingsModeType.GOAL_ALLOCATION.value,
            "currency": snapshot.currency,
            "strategy": strategy.value,
            "monthly_available_savings": _money(monthly_available),
            "total_allocated": _money(total_allocated),
            "unallocated": unallocated,
            "goal_count": len(goals),
            "goals": goal_items,
            "projected_total_progress": projections[-1]["balance"] if projections else Decimal("0"),
            "monthly_projections": projections,
            "assumptions": [
                {"description": "Allocation is based on the selected strategy and visible active goals."},
                {"description": "Projected progress assumes the recommended allocation continues unchanged."},
            ],
            "warnings": [],
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    def _allocate_to_goals(
        self,
        goals: list[Goal],
        monthly_available: Decimal,
        strategy: AllocationStrategy,
    ) -> list[tuple[Goal, Decimal]]:
        if strategy == AllocationStrategy.EQUAL_SPLIT:
            per_goal = _money(monthly_available / Decimal(str(len(goals))))
            return [(g, per_goal) for g in goals]

        if strategy == AllocationStrategy.PRIORITY_FIRST:
            sorted_goals = sorted(goals, key=lambda g: (g.priority, g.id))
        elif strategy == AllocationStrategy.CLOSEST_DEADLINE:
            sorted_goals = sorted(
                goals,
                key=lambda g: (g.target_date or date.max, g.priority, g.id),
            )
        elif strategy == AllocationStrategy.LOWEST_GAP_FIRST:
            sorted_goals = sorted(
                goals,
                key=lambda g: (_to_decimal(g.target_amount) - _to_decimal(g.current_amount), g.priority, g.id),
            )
        else:
            sorted_goals = goals

        allocations: list[tuple[Goal, Decimal]] = []
        remaining = monthly_available
        for goal in sorted_goals:
            gap = max(_to_decimal(goal.target_amount) - _to_decimal(goal.current_amount), Decimal("0"))
            allocation = _money(min(remaining, gap))
            allocations.append((goal, allocation))
            remaining -= allocation
            if remaining <= 0:
                break
        # Ensure any goals not reached by sequential allocation get 0.
        allocated_ids = {g.id for g, _ in allocations}
        for goal in sorted_goals:
            if goal.id not in allocated_ids:
                allocations.append((goal, Decimal("0")))
        return allocations

    # ------------------------------------------------------------------
    # Mode: Reduce spending to save more
    # ------------------------------------------------------------------
    async def _reduce_spending(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        target_monthly_savings = _to_decimal(request.get("target_monthly_savings", 0))
        if target_monthly_savings <= 0:
            raise SavingsOptimizerError("target_monthly_savings must be positive")
        months = int(request.get("months", 12))

        income = snapshot.avg_monthly_income
        expenses = snapshot.avg_monthly_expenses
        disposable = income - expenses
        gap = _money(max(target_monthly_savings - disposable, Decimal("0")))

        candidates = await self._expense_candidates(gap)

        warnings: list[dict[str, str]] = []
        if gap > 0:
            warnings.append({
                "severity": "medium",
                "message": f"To save {target_monthly_savings} per month, reduce spending by at least {gap} {snapshot.currency}.",
            })
        if disposable < 0:
            warnings.append({
                "severity": "high",
                "message": "Current expenses already exceed income; any savings target requires spending cuts or income growth.",
            })

        projections = self._build_projections(
            snapshot.total_assets,
            min(target_monthly_savings, disposable) if disposable > 0 else Decimal("0"),
            months,
        )

        result = {
            "mode": SavingsModeType.REDUCE_SPENDING.value,
            "currency": snapshot.currency,
            "avg_monthly_income": _money(income),
            "avg_monthly_expenses": _money(expenses),
            "target_monthly_savings": _money(target_monthly_savings),
            "current_monthly_savings_capacity": _money(max(disposable, Decimal("0"))),
            "required_spending_reduction": gap,
            "expense_reduction_candidates": candidates,
            "projected_total_savings": projections[-1]["cumulative_savings"] if projections else Decimal("0"),
            "monthly_projections": projections,
            "assumptions": [
                {"description": "Spending reductions are applied immediately and sustained."},
                {"description": "Income remains at the 90-day average."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    async def _expense_candidates(self, gap: Decimal) -> list[dict[str, Any]]:
        since = date.today() - timedelta(days=90)
        result = await self.db.execute(
            select(
                Account.id,
                Account.name,
                Account.account_type,
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")).label("total_debit"),
            )
            .join(JournalLine, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Expense")
            .where(JournalEntry.date >= since)
            .group_by(Account.id, Account.name, Account.account_type)
            .order_by(func.coalesce(func.sum(JournalLine.debit), Decimal("0")).desc())
        )
        candidates = []
        for row in result.all():
            total = _to_decimal(row.total_debit)
            if total <= 0:
                continue
            monthly = total / Decimal("3")
            suggested_reduction = _money(min(monthly * Decimal("0.10"), gap)) if gap > 0 else _money(monthly * Decimal("0.10"))
            candidates.append({
                "account_id": row.id,
                "account_name": row.name,
                "avg_monthly_expense": _money(monthly),
                "suggested_reduction": suggested_reduction,
            })
        return candidates[:5]

    # ------------------------------------------------------------------
    # Mode: Compare strategies
    # ------------------------------------------------------------------
    async def _compare_strategies(self, request: dict[str, Any]) -> dict[str, Any]:
        monthly_available = _to_decimal(request.get("monthly_available_savings", 0))
        if monthly_available <= 0:
            raise SavingsOptimizerError("monthly_available_savings must be positive")
        goal_ids = request.get("goal_ids")
        months = int(request.get("months", 12))

        strategies = [
            AllocationStrategy.EQUAL_SPLIT,
            AllocationStrategy.PRIORITY_FIRST,
            AllocationStrategy.CLOSEST_DEADLINE,
            AllocationStrategy.LOWEST_GAP_FIRST,
        ]
        results = []
        for strategy in strategies:
            run = await self.optimize(
                SavingsModeType.GOAL_ALLOCATION,
                {
                    "monthly_available_savings": str(monthly_available),
                    "strategy": strategy.value,
                    "goal_ids": goal_ids,
                    "months": months,
                },
            )
            results.append({
                "strategy": strategy.value,
                "total_allocated": run["total_allocated"],
                "unallocated": run["unallocated"],
                "projected_total_progress": run["projected_total_progress"],
                "goal_count": run["goal_count"],
            })

        # Recommend the strategy with the lowest unallocated (most capital directed to goals).
        best = min(results, key=lambda r: r["unallocated"])
        recommendation = (
            f"{best['strategy']} is projected to allocate the most toward your goals "
            f"({best['total_allocated']} {self._currency()}). Equal split may be fairest if all goals are equally important."
        )

        snapshot = await self.load_snapshot()
        result = {
            "mode": SavingsModeType.COMPARE_STRATEGIES.value,
            "currency": snapshot.currency,
            "monthly_available_savings": _money(monthly_available),
            "goal_count": results[0]["goal_count"] if results else 0,
            "strategies": results,
            "recommended_strategy": best["strategy"],
            "recommendation": recommendation,
            "assumptions": [
                {"description": "Comparison uses the same monthly available savings across all strategies."},
                {"description": "Recommendation favors the strategy that directs the most money toward goals."},
            ],
            "warnings": [],
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Projection builder
    # ------------------------------------------------------------------
    def _build_projections(
        self,
        starting_balance: Decimal,
        monthly_addition: Decimal,
        months: int,
    ) -> list[dict[str, Any]]:
        balance = _to_decimal(starting_balance)
        cumulative = Decimal("0")
        projections = []
        today = date.today()
        for month in range(1, months + 1):
            balance += monthly_addition
            cumulative += monthly_addition
            projections.append({
                "month_number": month,
                "month_label": (today + timedelta(days=30 * month)).strftime("%Y-%m"),
                "balance": _money(balance),
                "cumulative_savings": _money(cumulative),
                "monthly_addition": _money(monthly_addition),
            })
        return projections

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------
    def _confidence(self, snapshot: CashFlowSnapshot) -> str:
        if snapshot.avg_monthly_income == 0 and snapshot.avg_monthly_expenses == 0:
            return Confidence.LOW.value
        if snapshot.avg_monthly_income == 0 or snapshot.avg_monthly_expenses == 0:
            return Confidence.MEDIUM.value
        return Confidence.HIGH.value

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------
    def _deterministic_narrative(self, result: dict[str, Any]) -> str:
        mode = result.get("mode", "savings")
        lines = [f"Savings mode: {mode}."]
        if mode == SavingsModeType.EMERGENCY_FUND.value:
            lines.append(
                f"Target emergency fund: {result['target_amount']} {result['currency']} "
                f"({result['target_months_of_expenses']} months of expenses)."
            )
            lines.append(f"Current savings: {result['current_savings']} {result['currency']}.")
            lines.append(f"Gap: {result['gap_amount']} {result['currency']}.")
            if result.get("months_to_target") is not None:
                lines.append(f"Estimated months to target: {result['months_to_target']}.")
            lines.append(f"Risk level: {result['risk_level']}.")
        elif mode == SavingsModeType.SAVINGS_CAPACITY.value:
            lines.append(
                f"Average monthly net flow: {result['avg_monthly_net_flow']} {result['currency']}."
            )
            lines.append(
                f"Current savings rate: {result['current_savings_rate_percent']}%."
            )
            lines.append(
                f"Suggested monthly savings range: {result['suggested_monthly_savings_min']} - "
                f"{result['suggested_monthly_savings_max']} {result['currency']}."
            )
        elif mode == SavingsModeType.GOAL_ALLOCATION.value:
            lines.append(
                f"Allocating {result['monthly_available_savings']} {result['currency']} across "
                f"{result['goal_count']} goals using {result['strategy']}."
            )
            lines.append(f"Total allocated: {result['total_allocated']} {result['currency']}.")
        elif mode == SavingsModeType.REDUCE_SPENDING.value:
            lines.append(
                f"To save {result['target_monthly_savings']} {result['currency']} per month, "
                f"reduce spending by {result['required_spending_reduction']} {result['currency']}."
            )
        elif mode == SavingsModeType.COMPARE_STRATEGIES.value:
            lines.append(
                f"Recommended allocation strategy: {result['recommended_strategy']} "
                f"({result['recommendation']})"
            )

        if result.get("warnings"):
            lines.append("Warnings:")
            for warning in result["warnings"]:
                lines.append(f"- {warning['message']}")
        lines.append(
            "This is an educational projection, not a guarantee of future results."
        )
        return "\n".join(lines)

    async def _narrative(self, result: dict[str, Any], request: dict[str, Any]) -> str:
        if not request.get("include_narrative"):
            return self._deterministic_narrative(result)

        cost_controller = CostController(self.db, self.tenant_id)
        allowed, used, limit = await cost_controller.check_limit()
        client = LLMClient()

        if not allowed or not client.is_configured():
            return self._deterministic_narrative(result)

        try:
            response = await client.complete(
                messages=savings_optimizer_structured_prompt(result),
                temperature=0.7,
                max_tokens=700,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="savings_optimizer",
                user_id=self.user.id if self.user else None,
            )
            return self.safety.sanitize(response.content)
        except LLMError:
            return self._deterministic_narrative(result)
