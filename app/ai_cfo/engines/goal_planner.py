"""Deterministic Goal Planner for the AI Personal CFO.

The planner is read-only: it never creates or modifies goals, contributions,
accounts, journal entries, or transactions. It analyzes visible goals,
cash-flow trends, and timelines to produce feasibility and prioritization
projections, then optionally asks the LLM for a short narrative.
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
from app.ai_cfo.llm.prompts import goal_planner_structured_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import Account, Goal, GoalStatus, JournalEntry, JournalLine, User


class GoalPlannerError(Exception):
    """Raised when a goal plan cannot be generated."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class GoalPlanMode(str, enum.Enum):
    SINGLE_GOAL_FEASIBILITY = "single_goal_feasibility"
    HYPOTHETICAL_GOAL = "hypothetical_goal"
    MULTI_GOAL_PRIORITIZATION = "multi_goal_prioritization"
    DEADLINE_RESCUE = "deadline_rescue"
    FAMILY_GOAL_PLAN = "family_goal_plan"


class GoalPriorityStrategy(str, enum.Enum):
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
    """Aggregated cash-flow picture used for goal planning."""

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


class GoalPlanner:
    """Read-only goal planning engine."""

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
        avg_income = await self._avg_monthly_flow("Income")
        avg_expenses = await self._avg_monthly_flow("Expense")
        return CashFlowSnapshot(
            avg_monthly_income=avg_income,
            avg_monthly_expenses=avg_expenses,
            avg_monthly_net_flow=avg_income - avg_expenses,
            currency=self._currency(),
        )

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

    def _currency(self) -> str:
        if self.user and getattr(self.user, "currency", None):
            return self.user.currency
        return self.settings.CURRENCY_DEFAULT

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    async def _validate_goal(self, goal_id: int) -> Goal:
        result = await self.db.execute(
            select(Goal).where(Goal.id == goal_id, Goal.tenant_id == self.tenant_id)
        )
        goal = result.scalar_one_or_none()
        if goal is None:
            raise GoalPlannerError("Goal not found in tenant", 404)
        if self.user is not None:
            from app.services.family_goal_service import FamilyGoalService

            goal_service = FamilyGoalService(self.db, self.tenant_id, self.user)
            if not await goal_service.can_view_goal(goal):
                raise GoalPlannerError("You do not have permission to view this goal", 403)
        return goal

    async def _load_visible_goals(
        self,
        goal_ids: Optional[list[int]] = None,
        family_id: Optional[int] = None,
    ) -> list[Goal]:
        stmt = select(Goal).where(
            Goal.tenant_id == self.tenant_id,
            Goal.status == GoalStatus.ACTIVE.value,
        )
        if goal_ids:
            stmt = stmt.where(Goal.id.in_(goal_ids))
        if family_id is not None:
            stmt = stmt.where(Goal.family_id == family_id)

        result = await self.db.execute(stmt)
        goals = list(result.scalars().all())

        visible = []
        for goal in goals:
            if self.user is not None:
                from app.services.family_goal_service import FamilyGoalService

                goal_service = FamilyGoalService(self.db, self.tenant_id, self.user)
                if not await goal_service.can_view_goal(goal):
                    if goal_ids and goal.id in goal_ids:
                        raise GoalPlannerError(
                            "You do not have permission to view this goal", 403
                        )
                    continue
            visible.append(goal)
        return visible

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------
    async def plan(self, mode: GoalPlanMode, request: dict[str, Any]) -> dict[str, Any]:
        if mode == GoalPlanMode.SINGLE_GOAL_FEASIBILITY:
            return await self._single_goal_feasibility(request)
        if mode == GoalPlanMode.HYPOTHETICAL_GOAL:
            return await self._hypothetical_goal(request)
        if mode == GoalPlanMode.MULTI_GOAL_PRIORITIZATION:
            return await self._multi_goal_prioritization(request)
        if mode == GoalPlanMode.DEADLINE_RESCUE:
            return await self._deadline_rescue(request)
        if mode == GoalPlanMode.FAMILY_GOAL_PLAN:
            return await self._family_goal_plan(request)
        raise GoalPlannerError(f"Unsupported planning mode: {mode.value}")

    async def prioritize(self, request: dict[str, Any]) -> dict[str, Any]:
        """Convenience wrapper that always runs multi-goal prioritization."""
        return await self._multi_goal_prioritization(request)

    # ------------------------------------------------------------------
    # Mode: Single goal feasibility
    # ------------------------------------------------------------------
    async def _single_goal_feasibility(self, request: dict[str, Any]) -> dict[str, Any]:
        goal_id = request.get("goal_id")
        if goal_id is None:
            raise GoalPlannerError("goal_id is required")
        goal = await self._validate_goal(goal_id)

        snapshot = await self.load_snapshot()
        target_date_override = request.get("target_date")
        monthly_contribution_override = request.get("monthly_contribution")

        plan = self._plan_goal(
            goal,
            snapshot,
            monthly_contribution=_to_decimal(monthly_contribution_override)
            if monthly_contribution_override is not None
            else None,
            target_date_override=target_date_override,
        )

        result = {
            "mode": GoalPlanMode.SINGLE_GOAL_FEASIBILITY.value,
            "currency": snapshot.currency,
            "goal": plan,
            "assumptions": [
                {"description": "Projections use current goal balance and posted income/expense averages."},
                {"description": "Contributions are assumed to continue unchanged unless overridden."},
            ],
            "warnings": plan.get("warnings", []),
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Mode: Hypothetical goal
    # ------------------------------------------------------------------
    async def _hypothetical_goal(self, request: dict[str, Any]) -> dict[str, Any]:
        target_amount = _to_decimal(request.get("target_amount", 0))
        if target_amount <= 0:
            raise GoalPlannerError("target_amount must be positive")

        current_amount = max(_to_decimal(request.get("current_amount", 0)), Decimal("0"))
        target_date = request.get("target_date")
        monthly_contribution = request.get("monthly_contribution")
        goal_name = request.get("goal_name", "Hypothetical goal")

        snapshot = await self.load_snapshot()
        remaining = max(target_amount - current_amount, Decimal("0"))

        months_to_completion: Optional[int] = None
        required_monthly: Optional[Decimal] = None
        projected_completion: Optional[date] = None
        on_track = True
        deadline_risk = "low"
        warnings: list[dict[str, str]] = []

        if monthly_contribution is not None:
            contribution = _to_decimal(monthly_contribution)
            if contribution <= 0:
                raise GoalPlannerError("monthly_contribution must be positive")
            if remaining > 0:
                months_to_completion = math.ceil(float(remaining / contribution))
                projected_completion = date.today() + timedelta(days=30 * months_to_completion)
            if target_date and projected_completion:
                on_track = projected_completion <= date.fromisoformat(target_date)
                months_to_target = max((date.fromisoformat(target_date) - date.today()).days / 30, 1)
                required_monthly = _money(remaining / Decimal(str(months_to_target)))
                if not on_track:
                    deadline_risk = "high"
                    warnings.append({
                        "severity": "high",
                        "message": (
                            f"At {contribution}/month, the goal would be reached around "
                            f"{projected_completion.isoformat()}, after the target date."
                        ),
                    })
        elif target_date is not None:
            target = date.fromisoformat(target_date)
            if target <= date.today():
                raise GoalPlannerError("target_date must be in the future")
            months_to_target = max((target - date.today()).days / 30, 1)
            required_monthly = _money(remaining / Decimal(str(months_to_target)))
            months_to_completion = math.ceil(float(remaining / required_monthly)) if required_monthly > 0 else None
            projected_completion = (
                date.today() + timedelta(days=30 * months_to_completion)
                if months_to_completion is not None
                else None
            )
            if required_monthly > snapshot.avg_monthly_net_flow:
                warnings.append({
                    "severity": "medium",
                    "message": (
                        f"Required monthly contribution ({required_monthly}) exceeds "
                        f"recent average net cash flow ({snapshot.avg_monthly_net_flow})."
                    ),
                })

        feasibility = self._feasibility_rating(
            required_monthly, snapshot.avg_monthly_net_flow, on_track
        )

        result = {
            "mode": GoalPlanMode.HYPOTHETICAL_GOAL.value,
            "currency": snapshot.currency,
            "goal_name": goal_name,
            "target_amount": _money(target_amount),
            "current_amount": _money(current_amount),
            "remaining_amount": _money(remaining),
            "target_date": target_date,
            "monthly_contribution": _money(monthly_contribution) if monthly_contribution is not None else None,
            "required_monthly_contribution": required_monthly,
            "months_to_completion": months_to_completion,
            "projected_completion_date": projected_completion.isoformat() if projected_completion else None,
            "on_track": on_track,
            "deadline_risk": deadline_risk,
            "feasibility": feasibility,
            "assumptions": [
                {"description": "Projections assume contributions are made every month without interruption."},
                {"description": "Income/expense averages are based on posted journal entries from the last 90 days."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Mode: Multi-goal prioritization
    # ------------------------------------------------------------------
    async def _multi_goal_prioritization(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        available_monthly = _to_decimal(request.get("available_monthly_savings", 0))
        if available_monthly <= 0:
            raise GoalPlannerError("available_monthly_savings must be positive")

        strategy = GoalPriorityStrategy(request.get("strategy", GoalPriorityStrategy.EQUAL_SPLIT.value))
        goal_ids = request.get("goal_ids")
        months = int(request.get("months", 12))

        goals = await self._load_visible_goals(goal_ids)
        if not goals:
            raise GoalPlannerError("No visible active goals found for this tenant", 404)

        allocations = self._allocate_to_goals(goals, available_monthly, strategy)
        goal_items = []
        goals_at_risk = []
        total_gap = Decimal("0")

        for goal, allocation in allocations:
            plan = self._plan_goal(goal, snapshot, monthly_contribution=allocation)
            goal_items.append(plan)
            if plan["deadline_risk"] == "high":
                goals_at_risk.append(plan["goal_id"])
            gap = max(_to_decimal(plan["remaining_amount"]) - (allocation * Decimal(str(months))), Decimal("0"))
            total_gap += gap

        total_allocated = sum(a for _, a in allocations)
        unallocated = _money(available_monthly - total_allocated)

        warnings: list[dict[str, str]] = []
        if goals_at_risk:
            warnings.append({
                "severity": "medium",
                "message": f"{len(goals_at_risk)} goal(s) are at risk of missing their target dates.",
            })
        if total_gap > 0:
            warnings.append({
                "severity": "low",
                "message": f"Total remaining funding gap over {months} months is approximately {total_gap} {snapshot.currency}.",
            })

        result = {
            "mode": GoalPlanMode.MULTI_GOAL_PRIORITIZATION.value,
            "currency": snapshot.currency,
            "strategy": strategy.value,
            "available_monthly_savings": _money(available_monthly),
            "total_allocated": _money(total_allocated),
            "unallocated": unallocated,
            "goal_count": len(goals),
            "goals": goal_items,
            "goals_at_risk": goals_at_risk,
            "total_funding_gap": _money(total_gap),
            "assumptions": [
                {"description": "Allocation is based on the selected strategy and visible active goals."},
                {"description": "Projected completion assumes the allocated monthly amount continues unchanged."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Mode: Deadline rescue
    # ------------------------------------------------------------------
    async def _deadline_rescue(self, request: dict[str, Any]) -> dict[str, Any]:
        goal_id = request.get("goal_id")
        if goal_id is None:
            raise GoalPlannerError("goal_id is required")
        goal = await self._validate_goal(goal_id)

        target_date_str = request.get("target_date")
        if target_date_str is None:
            if goal.target_date is None:
                raise GoalPlannerError("target_date is required when the goal has no target date")
            target_date = goal.target_date
        else:
            target_date = date.fromisoformat(target_date_str)

        available_monthly = request.get("available_monthly_savings")
        snapshot = await self.load_snapshot()

        target = _to_decimal(goal.target_amount)
        current = _to_decimal(goal.current_amount)
        remaining = max(target - current, Decimal("0"))

        months_to_target = max((target_date - date.today()).days / 30, 1)
        required_monthly = _money(remaining / Decimal(str(months_to_target)))
        current_monthly = _to_decimal(goal.monthly_contribution)
        shortfall = _money(max(required_monthly - current_monthly, Decimal("0")))

        warnings: list[dict[str, str]] = []
        if target_date <= date.today():
            warnings.append({
                "severity": "high",
                "message": "Target date is today or in the past.",
            })
        if required_monthly > snapshot.avg_monthly_net_flow:
            warnings.append({
                "severity": "medium",
                "message": (
                    f"Required monthly contribution ({required_monthly}) exceeds "
                    f"recent average net cash flow ({snapshot.avg_monthly_net_flow})."
                ),
            })

        options = [
            {
                "option": "increase_contribution",
                "description": f"Increase monthly contribution by {shortfall} to reach the target on time.",
                "new_monthly_contribution": _money(current_monthly + shortfall),
            },
            {
                "option": "extend_deadline",
                "description": "Push the target date later to reduce the required monthly contribution.",
            },
            {
                "option": "reduce_target",
                "description": "Reduce the target amount so the current contribution reaches it by the deadline.",
                "suggested_target": _money(current_monthly * Decimal(str(months_to_target)) + current),
            },
        ]

        if available_monthly is not None:
            available = _to_decimal(available_monthly)
            reallocate_amount = _money(max(available - current_monthly, Decimal("0")))
            if reallocate_amount > 0:
                options.append({
                    "option": "reallocate",
                    "description": (
                        f"Reallocate up to {reallocate_amount}/month from lower-priority goals "
                        f"to close the {shortfall} gap."
                    ),
                })

        result = {
            "mode": GoalPlanMode.DEADLINE_RESCUE.value,
            "currency": snapshot.currency,
            "goal_id": goal.id,
            "goal_name": goal.name,
            "target_date": target_date.isoformat(),
            "target_amount": _money(target),
            "current_amount": _money(current),
            "remaining_amount": _money(remaining),
            "current_monthly_contribution": _money(current_monthly),
            "required_monthly_contribution": required_monthly,
            "shortfall": shortfall,
            "months_to_target": math.ceil(months_to_target),
            "options": options,
            "assumptions": [
                {"description": "The deadline is treated as the target completion date."},
                {"description": "Current goal balance and monthly contribution are unchanged."},
            ],
            "warnings": warnings,
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Mode: Family goal plan
    # ------------------------------------------------------------------
    async def _family_goal_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        snapshot = await self.load_snapshot()
        family_id = request.get("family_id")
        goal_ids = request.get("goal_ids")
        monthly_contribution = _to_decimal(request.get("monthly_family_contribution", 0))
        if monthly_contribution <= 0:
            raise GoalPlannerError("monthly_family_contribution must be positive")
        months = int(request.get("months", 12))

        goals = await self._load_visible_goals(goal_ids, family_id=family_id)
        if not goals:
            raise GoalPlannerError("No visible active goals found for this family", 404)

        allocations = self._allocate_to_goals(
            goals, monthly_contribution, GoalPriorityStrategy.EQUAL_SPLIT
        )
        goal_items = []
        for goal, allocation in allocations:
            plan = self._plan_goal(goal, snapshot, monthly_contribution=allocation)
            goal_items.append(plan)

        total_allocated = sum(a for _, a in allocations)
        result = {
            "mode": GoalPlanMode.FAMILY_GOAL_PLAN.value,
            "currency": snapshot.currency,
            "family_id": family_id,
            "monthly_family_contribution": _money(monthly_contribution),
            "total_allocated": _money(total_allocated),
            "goal_count": len(goals),
            "goals": goal_items,
            "assumptions": [
                {"description": "Family plan allocates the shared monthly contribution across visible goals."},
                {"description": "Equal split is used for family goal allocation."},
            ],
            "warnings": [],
            "confidence": self._confidence(snapshot),
            "narrative": "",
        }
        result["narrative"] = await self._narrative(result, request)
        return result

    # ------------------------------------------------------------------
    # Core goal planning logic
    # ------------------------------------------------------------------
    def _plan_goal(
        self,
        goal: Goal,
        snapshot: CashFlowSnapshot,
        monthly_contribution: Optional[Decimal] = None,
        target_date_override: Optional[str] = None,
    ) -> dict[str, Any]:
        target = _to_decimal(goal.target_amount)
        current = _to_decimal(goal.current_amount)
        remaining = max(target - current, Decimal("0"))

        contribution = (
            _to_decimal(monthly_contribution)
            if monthly_contribution is not None
            else _to_decimal(goal.monthly_contribution)
        )

        target_date = (
            date.fromisoformat(target_date_override)
            if target_date_override
            else goal.target_date
        )

        months_to_completion: Optional[int] = None
        projected_completion: Optional[date] = None
        required_monthly: Optional[Decimal] = None
        on_track = True
        deadline_risk = "low"
        warnings: list[dict[str, str]] = []

        if contribution > 0 and remaining > 0:
            months_to_completion = math.ceil(float(remaining / contribution))
            projected_completion = date.today() + timedelta(days=30 * months_to_completion)
            if target_date:
                on_track = projected_completion <= target_date
                if not on_track:
                    deadline_risk = "high"
                    warnings.append({
                        "severity": "high",
                        "message": (
                            f"At {contribution}/month, '{goal.name}' would be reached around "
                            f"{projected_completion.isoformat()}, after the target date."
                        ),
                    })
        elif contribution == 0 and remaining > 0:
            on_track = False
            deadline_risk = "high"
            warnings.append({
                "severity": "high",
                "message": f"'{goal.name}' has no monthly contribution set and will not progress.",
            })

        if target_date and remaining > 0:
            months_to_target = max((target_date - date.today()).days / 30, 1)
            required_monthly = _money(remaining / Decimal(str(months_to_target)))
            if deadline_risk != "high" and (contribution == 0 or required_monthly > contribution):
                deadline_risk = "medium"

        progress_percent = (current / target * Decimal("100")) if target > 0 else Decimal("0")

        return {
            "goal_id": goal.id,
            "goal_name": goal.name,
            "target_amount": _money(target),
            "current_amount": _money(current),
            "remaining_amount": _money(remaining),
            "monthly_contribution": _money(contribution),
            "required_monthly_contribution": required_monthly,
            "months_to_completion": months_to_completion,
            "projected_completion_date": projected_completion.isoformat() if projected_completion else None,
            "target_date": target_date.isoformat() if target_date else None,
            "on_track": on_track,
            "deadline_risk": deadline_risk,
            "progress_percent": f"{progress_percent:.2f}",
            "priority": goal.priority,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Allocation strategies
    # ------------------------------------------------------------------
    def _allocate_to_goals(
        self,
        goals: list[Goal],
        monthly_available: Decimal,
        strategy: GoalPriorityStrategy,
    ) -> list[tuple[Goal, Decimal]]:
        if strategy == GoalPriorityStrategy.EQUAL_SPLIT:
            per_goal = _money(monthly_available / Decimal(str(len(goals))))
            return [(g, per_goal) for g in goals]

        if strategy == GoalPriorityStrategy.PRIORITY_FIRST:
            sorted_goals = sorted(goals, key=lambda g: (g.priority, g.id))
        elif strategy == GoalPriorityStrategy.CLOSEST_DEADLINE:
            sorted_goals = sorted(
                goals,
                key=lambda g: (g.target_date or date.max, g.priority, g.id),
            )
        elif strategy == GoalPriorityStrategy.LOWEST_GAP_FIRST:
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
        allocated_ids = {g.id for g, _ in allocations}
        for goal in sorted_goals:
            if goal.id not in allocated_ids:
                allocations.append((goal, Decimal("0")))
        return allocations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _feasibility_rating(
        self,
        required_monthly: Optional[Decimal],
        avg_net_flow: Decimal,
        on_track: bool,
    ) -> str:
        if required_monthly is None:
            return "unknown"
        if required_monthly == 0:
            return "achieved"
        if not on_track:
            return "challenging"
        if required_monthly <= avg_net_flow * Decimal("0.5"):
            return "high"
        if required_monthly <= avg_net_flow:
            return "medium"
        return "low"

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
        mode = result.get("mode", "goal_plan")
        lines = [f"Goal planning mode: {mode}."]

        if mode == GoalPlanMode.SINGLE_GOAL_FEASIBILITY.value:
            goal = result.get("goal", {})
            lines.append(f"Goal: {goal.get('goal_name')}.")
            lines.append(
                f"Remaining amount: {goal.get('remaining_amount')} {result['currency']}."
            )
            if goal.get("required_monthly_contribution"):
                lines.append(
                    f"Required monthly contribution: {goal['required_monthly_contribution']} "
                    f"{result['currency']}."
                )
            if goal.get("months_to_completion"):
                lines.append(f"Months to completion: {goal['months_to_completion']}.")
            lines.append(f"On track: {goal.get('on_track')}. Deadline risk: {goal.get('deadline_risk')}.")
        elif mode == GoalPlanMode.HYPOTHETICAL_GOAL.value:
            lines.append(f"Goal: {result.get('goal_name')}.")
            lines.append(
                f"Target: {result.get('target_amount')} {result['currency']}; "
                f"remaining: {result.get('remaining_amount')} {result['currency']}."
            )
            if result.get("required_monthly_contribution"):
                lines.append(
                    f"Required monthly contribution: {result['required_monthly_contribution']} "
                    f"{result['currency']}."
                )
            lines.append(f"Feasibility: {result.get('feasibility')}.")
        elif mode == GoalPlanMode.MULTI_GOAL_PRIORITIZATION.value:
            lines.append(
                f"Allocating {result.get('available_monthly_savings')} {result['currency']}/month "
                f"across {result.get('goal_count')} goals using {result.get('strategy')}."
            )
            lines.append(f"Goals at risk: {len(result.get('goals_at_risk', []))}.")
        elif mode == GoalPlanMode.DEADLINE_RESCUE.value:
            lines.append(
                f"To reach '{result.get('goal_name')}' by {result.get('target_date')}, "
                f"contribute {result.get('required_monthly_contribution')} {result['currency']}/month."
            )
            if result.get("shortfall"):
                lines.append(f"Shortfall vs current contribution: {result['shortfall']} {result['currency']}.")
        elif mode == GoalPlanMode.FAMILY_GOAL_PLAN.value:
            lines.append(
                f"Family plan allocates {result.get('monthly_family_contribution')} "
                f"{result['currency']}/month across {result.get('goal_count')} visible goals."
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
                messages=goal_planner_structured_prompt(result),
                temperature=0.7,
                max_tokens=700,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="goal_planner",
                user_id=self.user.id if self.user else None,
            )
            return self.safety.sanitize(response.content)
        except LLMError:
            return self._deterministic_narrative(result)
