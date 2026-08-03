"""AI-centric "Today" dashboard service (AI-1223).

Builds a single read-only dashboard payload by composing existing AI CFO
engines and services. This module never creates, updates, or deletes
financial records — it only reads data through existing tenant-scoped
services and engines, all of which are themselves read-only.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_cfo.confidence import ConfidenceScorer
from app.ai_cfo.engines import (
    DebtOptimizer,
    DebtOptimizerError,
    DebtStrategyType,
    ProactiveAlertsEngine,
    ProactiveAlertsError,
    SavingsModeType,
    SavingsOptimizer,
    SavingsOptimizerError,
)
from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import DEFAULT_DISCLAIMER, dashboard_brief_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import User
from app.services.ai_chat import AIChatService
from app.services.ai_memory_service import AIMemoryService
from app.services.bill_subscription_service import CommitmentService
from app.services.family_goal_service import FamilyGoalService
from app.services.health_score_service import HealthScoreService


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _greeting() -> str:
    hour = datetime.utcnow().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


class DashboardAIService:
    """Compose a read-only, AI-centric "Today" dashboard payload."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        user: User,
        settings: Optional[Settings] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self.settings = settings or get_settings()
        self.safety = SafetyFilter()

    async def build_today(self, *, include_narrative: bool = False) -> dict[str, Any]:
        """Build the full Dashboard v2 "Today" payload."""
        health_score = await self._safe_health_score()
        commitments = await self._commitments_summary()
        goals = await self._goals_summary()
        alerts = await self._top_alerts()
        insights = await self._quick_insights()
        has_memory = await self._has_active_memory()

        suggested_actions = self._suggested_actions(health_score, commitments, goals, alerts)
        suggested_questions = AIChatService._suggested_questions_from_history([])
        quick_actions = self._quick_action_links()

        summary_text = self._deterministic_summary(health_score, commitments, goals, alerts)
        used_llm = False
        llm_attempted = False
        if include_narrative:
            llm_attempted = True
            summary_text, used_llm = await self._narrative_summary(
                health_score, commitments, goals, alerts, fallback=summary_text
            )

        confidence = self._confidence(
            health_score=health_score,
            commitments=commitments,
            goals=goals,
            has_memory=has_memory,
            llm_attempted=llm_attempted,
            used_llm=used_llm,
        )

        return {
            "greeting": _greeting(),
            "today": date.today().isoformat(),
            "summary": self.safety.add_disclaimer(summary_text),
            "disclaimer": DEFAULT_DISCLAIMER,
            "health_score": health_score,
            "alerts": alerts,
            "commitments": commitments,
            "goals": goals,
            "insights": insights,
            "suggested_actions": suggested_actions,
            "suggested_questions": suggested_questions,
            "quick_actions": quick_actions,
            "currency": self.settings.CURRENCY_DEFAULT,
            **confidence.to_dict(),
        }

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    async def _safe_health_score(self) -> Optional[dict[str, Any]]:
        try:
            service = HealthScoreService(self.db, self.tenant_id)
            return await service.calculate_score()
        except Exception:
            return None

    async def _commitments_summary(self) -> dict[str, Any]:
        service = CommitmentService(self.db, self.tenant_id)
        summary = await service.summary()
        return {
            "upcoming_bills_count": summary["upcoming_bills_count"],
            "upcoming_bills_total": str(summary["upcoming_bills_total"]),
            "overdue_bills_count": summary["overdue_bills_count"],
            "overdue_bills_total": str(summary["overdue_bills_total"]),
            "upcoming_renewals_count": summary["upcoming_renewals_count"],
            "upcoming_renewals_total": str(summary["upcoming_renewals_total"]),
            "monthly_subscription_total": str(summary["monthly_subscription_total"]),
            "total_fixed_commitments_this_month": str(summary["total_fixed_commitments_this_month"]),
            "currency": self.settings.CURRENCY_DEFAULT,
        }

    async def _goals_summary(self) -> dict[str, Any]:
        service = FamilyGoalService(self.db, tenant_id=self.tenant_id, user=self.user)
        summary = await service.get_active_family_goals_summary()
        return {
            "active_goals_count": summary["total_goals"],
            "total_target": summary["total_target"],
            "total_current": summary["total_current"],
            "remaining": summary["remaining"],
            "overall_progress": summary["overall_progress"],
            "currency": self.settings.CURRENCY_DEFAULT,
        }

    async def _top_alerts(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            engine = ProactiveAlertsEngine(self.db, self.tenant_id, user=self.user)
            candidates = await engine.preview()
        except ProactiveAlertsError:
            return []

        ranked = sorted(
            candidates,
            key=lambda c: _SEVERITY_ORDER.get(c.severity.value, 99),
        )
        return [
            {
                "alert_type": c.alert_type.value,
                "severity": c.severity.value,
                "title": c.title,
                "message": c.message,
                "related_entity_type": c.related_entity_type,
                "related_entity_id": c.related_entity_id,
                "confidence_score": c.confidence_score,
                "confidence_label": c.confidence_label,
            }
            for c in ranked[:limit]
        ]

    async def _quick_insights(self) -> list[dict[str, Any]]:
        insights: list[dict[str, Any]] = []

        savings_insight = await self._savings_insight()
        if savings_insight:
            insights.append(savings_insight)

        debt_insight = await self._debt_insight()
        if debt_insight:
            insights.append(debt_insight)

        return insights

    async def _savings_insight(self) -> Optional[dict[str, Any]]:
        try:
            optimizer = SavingsOptimizer(self.db, self.tenant_id, user=self.user)
            result = await optimizer.optimize(SavingsModeType.EMERGENCY_FUND, {})
        except SavingsOptimizerError:
            return None

        return {
            "type": "savings",
            "title": "Emergency Fund",
            "message": (
                f"Your emergency fund gap is {result['gap_amount']} {result['currency']} "
                f"(risk level: {result['risk_level']})."
            ),
            "confidence_score": result.get("confidence_score"),
            "confidence_label": result.get("confidence_label", result.get("confidence")),
            "link": "/ai/chat?q=" + _url_quote("How is my emergency fund doing?"),
        }

    async def _debt_insight(self) -> Optional[dict[str, Any]]:
        try:
            optimizer = DebtOptimizer(self.db, self.tenant_id, user=self.user)
            result = await optimizer.optimize(DebtStrategyType.AVALANCHE)
        except DebtOptimizerError:
            return None

        return {
            "type": "debt",
            "title": "Debt Payoff",
            "message": (
                f"At your current pace, projected payoff is {result['payoff_months']} months "
                f"(estimated interest saved with avalanche: {result['interest_saved']} {result['currency']})."
            ),
            "confidence_score": result.get("confidence_score"),
            "confidence_label": result.get("confidence_label", result.get("confidence")),
            "link": "/ai/chat?q=" + _url_quote("Which debt should I pay off first?"),
        }

    async def _has_active_memory(self) -> bool:
        try:
            service = AIMemoryService(self.db, self.tenant_id, self.user.id)
            memories = await service.list_memories(active_only=True, limit=1)
            return len(memories) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Suggested actions / quick action links
    # ------------------------------------------------------------------
    def _suggested_actions(
        self,
        health_score: Optional[dict[str, Any]],
        commitments: dict[str, Any],
        goals: dict[str, Any],
        alerts: list[dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []
        if commitments["overdue_bills_count"] > 0:
            actions.append("Review and pay your overdue bills.")
        if commitments["upcoming_bills_count"] > 0:
            actions.append("Check upcoming bills due in the next 7 days.")
        if goals["active_goals_count"] == 0:
            actions.append("Set a savings goal to start tracking progress.")
        elif goals["overall_progress"] < 25:
            actions.append("Consider increasing contributions to your active goals.")
        if health_score is not None and health_score.get("overall_score", 100) < 60:
            actions.append("Review your financial health snapshot for improvement areas.")
        if any(a["severity"] == "critical" for a in alerts):
            actions.append("Address your critical alerts first.")
        if not actions:
            actions.append("You're on track — explore What-If scenarios to plan ahead.")
        return actions[:5]

    def _quick_action_links(self) -> list[dict[str, str]]:
        return [
            {
                "label": "What-If Simulator",
                "description": "Model the impact of a financial decision before you make it.",
                "url": "/ai/chat?q=" + _url_quote("Can you run a what-if scenario with me?"),
                "icon": "bi-graph-up-arrow",
            },
            {
                "label": "Debt Optimizer",
                "description": "Compare avalanche vs. snowball payoff strategies.",
                "url": "/ai/chat?q=" + _url_quote("Which loan should I pay off first?"),
                "icon": "bi-credit-card",
            },
            {
                "label": "Savings Optimizer",
                "description": "Get emergency-fund and savings-rate guidance.",
                "url": "/ai/chat?q=" + _url_quote("How can I improve my savings rate?"),
                "icon": "bi-piggy-bank",
            },
            {
                "label": "Goal Planner",
                "description": "Check feasibility and prioritize your goals.",
                "url": "/ai/chat?q=" + _url_quote("Am I on track for my financial goals?"),
                "icon": "bi-bullseye",
            },
            {
                "label": "AI Chat",
                "description": "Ask your AI Financial Coach anything.",
                "url": "/ai/chat",
                "icon": "bi-stars",
            },
        ]

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------
    def _confidence(
        self,
        *,
        health_score: Optional[dict[str, Any]],
        commitments: dict[str, Any],
        goals: dict[str, Any],
        has_memory: bool,
        llm_attempted: bool = False,
        used_llm: bool = False,
    ):
        scorer = ConfidenceScorer().add("deterministic_calculation")
        if health_score is not None:
            scorer.add("direct_accounting_data")
        else:
            scorer.add("low_transaction_history")
        has_commitments_or_goals = (
            commitments["upcoming_bills_count"] > 0
            or commitments["overdue_bills_count"] > 0
            or goals["active_goals_count"] > 0
        )
        scorer.add_if(has_commitments_or_goals, "sufficient_history")
        scorer.add_if(has_memory, "user_confirmed_memory")
        # An LLM-enhanced narrative never boosts numeric confidence by itself;
        # only a failed/unavailable LLM attempt lowers it.
        scorer.add_if(llm_attempted and not used_llm, "llm_fallback")
        return scorer.build()

    # ------------------------------------------------------------------
    # Narrative (deterministic-first, optional LLM enhancement)
    # ------------------------------------------------------------------
    def _deterministic_summary(
        self,
        health_score: Optional[dict[str, Any]],
        commitments: dict[str, Any],
        goals: dict[str, Any],
        alerts: list[dict[str, Any]],
    ) -> str:
        parts = [f"{_greeting()}! Here's your financial snapshot for today."]
        if health_score is not None:
            parts.append(f"Your financial health score is {health_score['overall_score']}/100.")
        else:
            parts.append("Add accounts and transactions to unlock your health score.")

        if commitments["overdue_bills_count"] > 0:
            parts.append(
                f"You have {commitments['overdue_bills_count']} overdue bill(s) totaling "
                f"{commitments['overdue_bills_total']} {commitments['currency']}."
            )
        elif commitments["upcoming_bills_count"] > 0:
            parts.append(
                f"You have {commitments['upcoming_bills_count']} bill(s) due in the next 7 days."
            )
        else:
            parts.append("No bills are due soon.")

        if goals["active_goals_count"] > 0:
            parts.append(
                f"Your {goals['active_goals_count']} active goal(s) are "
                f"{goals['overall_progress']}% funded on average."
            )

        if alerts:
            parts.append(f"You have {len(alerts)} alert(s) to review below.")

        return " ".join(parts)

    async def _narrative_summary(
        self,
        health_score: Optional[dict[str, Any]],
        commitments: dict[str, Any],
        goals: dict[str, Any],
        alerts: list[dict[str, Any]],
        *,
        fallback: str,
    ) -> tuple[str, bool]:
        """Optionally enhance the brief via LLM; always falls back safely.

        Returns (text, used_llm).
        """
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, _, _ = await cost_controller.check_limit()
        client = LLMClient()

        if not allowed or not client.is_configured():
            return fallback, False

        summary_payload = {
            "health_score": health_score["overall_score"] if health_score else None,
            "top_alert": alerts[0]["title"] if alerts else None,
            "overdue_bills_count": commitments["overdue_bills_count"],
            "upcoming_bills_count": commitments["upcoming_bills_count"],
            "active_goals_count": goals["active_goals_count"],
            "goal_progress_percent": goals["overall_progress"],
        }

        try:
            response = await client.complete(
                messages=dashboard_brief_prompt(summary_payload),
                temperature=0.7,
                max_tokens=200,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="dashboard_brief",
                user_id=self.user.id,
            )
            text = self.safety.sanitize(response.content).replace(f"\n\n*{DEFAULT_DISCLAIMER}*", "")
            return text, True
        except LLMError:
            return fallback, False


def _url_quote(text: str) -> str:
    """Minimal URL-encoding for query string values without extra deps."""
    from urllib.parse import quote

    return quote(text)
