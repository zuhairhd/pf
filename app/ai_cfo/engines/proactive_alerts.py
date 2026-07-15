"""Proactive Alerts engine for the AI Personal CFO.

The engine detects important financial conditions for a tenant and creates safe
in-app notifications through the existing NotificationDeliveryService. It does
not modify financial records.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import proactive_alert_structured_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import (
    Account,
    Bill,
    Goal,
    GoalStatus,
    JournalEntry,
    JournalLine,
    Loan,
    Notification,
    NotificationChannel,
    NotificationType,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.notifications.services import NotificationDeliveryService


class ProactiveAlertType(str, enum.Enum):
    BILL_DUE_SOON = "bill_due_soon"
    BILL_OVERDUE = "bill_overdue"
    SUBSCRIPTION_RENEWAL_SOON = "subscription_renewal_soon"
    HIGH_SPENDING_ANOMALY = "high_spending_anomaly"
    NEGATIVE_CASH_FLOW = "negative_cash_flow"
    LOW_EMERGENCY_FUND = "low_emergency_fund"
    GOAL_DEADLINE_RISK = "goal_deadline_risk"
    DEBT_PRESSURE = "debt_pressure"


class ProactiveAlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ProactiveAlertCandidate:
    """A detected alert that could become a notification."""

    alert_type: ProactiveAlertType
    severity: ProactiveAlertSeverity
    notification_type: NotificationType
    title: str
    message: str
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None


class ProactiveAlertsError(Exception):
    """Raised when proactive alert generation fails."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Any) -> Decimal:
    return _to_decimal(value).quantize(Decimal("0.001"))


class ProactiveAlertsEngine:
    """Read-only proactive alert detector and notification creator."""

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
        self.notification_service = NotificationDeliveryService(db, tenant_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def preview(self) -> list[ProactiveAlertCandidate]:
        """Detect alerts without persisting notifications."""
        if not self.settings.PROACTIVE_ALERTS_ENABLED:
            return []
        return await self._detect_all()

    async def run(
        self,
        *,
        include_llm_wording: bool = False,
    ) -> dict[str, Any]:
        """Detect alerts and create in-app notifications, deduped by day."""
        if not self.settings.PROACTIVE_ALERTS_ENABLED:
            return {"created": 0, "skipped": 0, "candidates": 0}

        if self.user is None:
            raise ProactiveAlertsError("A user is required to create notifications", 400)

        candidates = await self._detect_all()
        created = 0
        skipped = 0
        for candidate in candidates:
            if await self._exists_today(candidate):
                skipped += 1
                continue

            message = candidate.message
            if include_llm_wording:
                message = await self._enhance_message(candidate)

            await self.notification_service.create_notification(
                user_id=self.user.id,
                notification_type=candidate.notification_type,
                title=candidate.title,
                message=message,
                channel=NotificationChannel.IN_APP,
                related_entity_type=candidate.related_entity_type,
                related_entity_id=candidate.related_entity_id,
            )
            created += 1

        return {"created": created, "skipped": skipped, "candidates": len(candidates)}

    # ------------------------------------------------------------------
    # Detection orchestration
    # ------------------------------------------------------------------
    async def _detect_all(self) -> list[ProactiveAlertCandidate]:
        candidates: list[ProactiveAlertCandidate] = []
        candidates.extend(await self._detect_bills())
        candidates.extend(await self._detect_subscriptions())
        candidates.extend(await self._detect_spending_anomaly())
        candidates.extend(await self._detect_cash_flow())
        candidates.extend(await self._detect_emergency_fund())
        candidates.extend(await self._detect_goal_risks())
        candidates.extend(await self._detect_debt_pressure())
        return candidates

    # ------------------------------------------------------------------
    # Bill alerts
    # ------------------------------------------------------------------
    async def _detect_bills(self) -> list[ProactiveAlertCandidate]:
        today = date.today()
        cutoff = today + timedelta(days=self.settings.ALERT_BILL_DUE_DAYS)
        candidates: list[ProactiveAlertCandidate] = []

        result = await self.db.execute(
            select(Bill)
            .where(Bill.tenant_id == self.tenant_id)
            .where(Bill.is_active.is_(True))
            .where(Bill.is_paid.is_(False))
            .where(Bill.due_date >= today)
            .where(Bill.due_date <= cutoff)
        )
        for bill in result.scalars().all():
            days_until = (bill.due_date - today).days
            severity = ProactiveAlertSeverity.CRITICAL if days_until <= 1 else ProactiveAlertSeverity.WARNING
            candidates.append(ProactiveAlertCandidate(
                alert_type=ProactiveAlertType.BILL_DUE_SOON,
                severity=severity,
                notification_type=NotificationType.BILL_DUE,
                title=f"Bill due soon: {bill.name}",
                message=(
                    f"Your bill '{bill.name}' from {bill.provider} is due on "
                    f"{bill.due_date.isoformat()} (typical amount {bill.typical_amount:.3f} "
                    f"{self._currency()}). Please review and schedule payment if needed."
                ),
                related_entity_type="bill",
                related_entity_id=bill.id,
            ))

        result = await self.db.execute(
            select(Bill)
            .where(Bill.tenant_id == self.tenant_id)
            .where(Bill.is_active.is_(True))
            .where(Bill.is_paid.is_(False))
            .where(Bill.due_date < today)
        )
        for bill in result.scalars().all():
            days_overdue = (today - bill.due_date).days
            severity = ProactiveAlertSeverity.CRITICAL if days_overdue > 7 else ProactiveAlertSeverity.WARNING
            candidates.append(ProactiveAlertCandidate(
                alert_type=ProactiveAlertType.BILL_OVERDUE,
                severity=severity,
                notification_type=NotificationType.BILL_OVERDUE,
                title=f"Bill overdue: {bill.name}",
                message=(
                    f"Your bill '{bill.name}' from {bill.provider} was due on "
                    f"{bill.due_date.isoformat()} (typical amount {bill.typical_amount:.3f} "
                    f"{self._currency()}) and is now {days_overdue} day(s) overdue. "
                    f"Please arrange payment as soon as possible."
                ),
                related_entity_type="bill",
                related_entity_id=bill.id,
            ))

        return candidates

    # ------------------------------------------------------------------
    # Subscription alerts
    # ------------------------------------------------------------------
    async def _detect_subscriptions(self) -> list[ProactiveAlertCandidate]:
        today = date.today()
        cutoff = today + timedelta(days=self.settings.ALERT_SUBSCRIPTION_RENEWAL_DAYS)
        candidates: list[ProactiveAlertCandidate] = []

        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == self.tenant_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE.value)
            .where(Subscription.next_billing_date >= today)
            .where(Subscription.next_billing_date <= cutoff)
        )
        for sub in result.scalars().all():
            days_until = (sub.next_billing_date - today).days
            severity = ProactiveAlertSeverity.WARNING if days_until <= 2 else ProactiveAlertSeverity.INFO
            candidates.append(ProactiveAlertCandidate(
                alert_type=ProactiveAlertType.SUBSCRIPTION_RENEWAL_SOON,
                severity=severity,
                notification_type=NotificationType.SUBSCRIPTION_RENEWAL,
                title=f"Subscription renewal: {sub.name}",
                message=(
                    f"Your subscription '{sub.name}' from {sub.provider} will renew on "
                    f"{sub.next_billing_date.isoformat()} for {sub.amount:.3f} "
                    f"{self._currency()} ({sub.frequency})."
                ),
                related_entity_type="subscription",
                related_entity_id=sub.id,
            ))

        return candidates

    # ------------------------------------------------------------------
    # Spending anomaly
    # ------------------------------------------------------------------
    async def _detect_spending_anomaly(self) -> list[ProactiveAlertCandidate]:
        today = date.today()
        recent_start = today - timedelta(days=30)
        baseline_start = today - timedelta(days=90)
        baseline_end = today - timedelta(days=30)

        recent_expense = await self._expense_total(recent_start, today)
        baseline_expense = await self._expense_total(baseline_start, baseline_end)

        baseline_monthly = baseline_expense / Decimal("2")  # 60-day baseline -> monthly avg
        if baseline_monthly <= 0:
            return []

        threshold_pct = self.settings.ALERT_SPENDING_ANOMALY_PERCENT / Decimal("100")
        if recent_expense <= baseline_monthly * (Decimal("1") + threshold_pct):
            return []

        excess = recent_expense - baseline_monthly
        candidates = [ProactiveAlertCandidate(
            alert_type=ProactiveAlertType.HIGH_SPENDING_ANOMALY,
            severity=ProactiveAlertSeverity.WARNING,
            notification_type=NotificationType.ANOMALY_DETECTED,
            title="Spending higher than usual",
            message=(
                f"Your spending over the last 30 days ({recent_expense:.3f} {self._currency()}) "
                f"is higher than the recent 60-day monthly average ({baseline_monthly:.3f} "
                f"{self._currency()}) by {excess:.3f} {self._currency()}. "
                f"Review your expense categories to see what changed."
            ),
            related_entity_type="tenant",
            related_entity_id=self.tenant_id,
        )]
        return candidates

    async def _expense_total(self, start_date: date, end_date: date) -> Decimal:
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), Decimal("0")))
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Expense")
            .where(JournalEntry.date >= start_date)
            .where(JournalEntry.date < end_date)
        )
        return _to_decimal(result.scalar())

    # ------------------------------------------------------------------
    # Cash-flow risk
    # ------------------------------------------------------------------
    async def _detect_cash_flow(self) -> list[ProactiveAlertCandidate]:
        avg_income = await self._avg_monthly_flow("Income")
        avg_expenses = await self._avg_monthly_flow("Expense")
        net_flow = avg_income - avg_expenses
        threshold = self.settings.ALERT_LOW_CASHFLOW_THRESHOLD

        if net_flow >= threshold and avg_income > 0:
            return []

        severity = ProactiveAlertSeverity.WARNING if avg_income > 0 else ProactiveAlertSeverity.INFO
        if net_flow < Decimal("0"):
            severity = ProactiveAlertSeverity.CRITICAL

        candidates = [ProactiveAlertCandidate(
            alert_type=ProactiveAlertType.NEGATIVE_CASH_FLOW,
            severity=severity,
            notification_type=NotificationType.AI_INSIGHT,
            title="Cash-flow risk detected",
            message=(
                f"Your average monthly net cash flow over the last 90 days is "
                f"{net_flow:.3f} {self._currency()} (income {avg_income:.3f}, expenses "
                f"{avg_expenses:.3f}). Expenses are exceeding or near income; review "
                f"discretionary spending or look for ways to increase income."
            ),
            related_entity_type="tenant",
            related_entity_id=self.tenant_id,
        )]
        return candidates

    # ------------------------------------------------------------------
    # Emergency fund risk
    # ------------------------------------------------------------------
    async def _detect_emergency_fund(self) -> list[ProactiveAlertCandidate]:
        avg_expenses = await self._avg_monthly_flow("Expense")
        total_assets = await self._total_assets()

        if avg_expenses <= 0:
            return []

        months_of_expenses = total_assets / avg_expenses
        target_months = self.settings.ALERT_EMERGENCY_FUND_MONTHS
        if months_of_expenses >= target_months:
            return []

        severity = ProactiveAlertSeverity.CRITICAL if months_of_expenses < Decimal("0.5") else ProactiveAlertSeverity.WARNING
        gap = (target_months * avg_expenses) - total_assets
        candidates = [ProactiveAlertCandidate(
            alert_type=ProactiveAlertType.LOW_EMERGENCY_FUND,
            severity=severity,
            notification_type=NotificationType.AI_INSIGHT,
            title="Emergency fund is low",
            message=(
                f"Your liquid assets ({total_assets:.3f} {self._currency()}) cover about "
                f"{months_of_expenses:.1f} month(s) of average expenses. The target is at "
                f"least {target_months} month(s). Consider building a buffer of "
                f"{gap:.3f} {self._currency()}."
            ),
            related_entity_type="tenant",
            related_entity_id=self.tenant_id,
        )]
        return candidates

    # ------------------------------------------------------------------
    # Goal deadline risk
    # ------------------------------------------------------------------
    async def _detect_goal_risks(self) -> list[ProactiveAlertCandidate]:
        today = date.today()
        result = await self.db.execute(
            select(Goal)
            .where(Goal.tenant_id == self.tenant_id)
            .where(Goal.status == GoalStatus.ACTIVE.value)
        )
        goals = result.scalars().all()

        candidates: list[ProactiveAlertCandidate] = []
        for goal in goals:
            target = _to_decimal(goal.target_amount)
            current = _to_decimal(goal.current_amount)
            remaining = max(target - current, Decimal("0"))
            if remaining <= 0:
                continue

            contribution = _to_decimal(goal.monthly_contribution)
            target_date = goal.target_date
            if target_date is None:
                continue
            if target_date <= today:
                candidates.append(ProactiveAlertCandidate(
                    alert_type=ProactiveAlertType.GOAL_DEADLINE_RISK,
                    severity=ProactiveAlertSeverity.CRITICAL,
                    notification_type=NotificationType.GOAL_MILESTONE,
                    title=f"Goal deadline passed: {goal.name}",
                    message=(
                        f"Your goal '{goal.name}' target date was {target_date.isoformat()} "
                        f"but the remaining amount is {remaining:.3f} {self._currency()}. "
                        f"Consider revising the target date or increasing contributions."
                    ),
                    related_entity_type="goal",
                    related_entity_id=goal.id,
                ))
                continue

            months_to_target = max((target_date - today).days / 30, 1)
            required_monthly = remaining / Decimal(str(months_to_target))
            if required_monthly <= contribution:
                continue

            shortfall = required_monthly - contribution
            severity = ProactiveAlertSeverity.WARNING if months_to_target > 3 else ProactiveAlertSeverity.CRITICAL
            candidates.append(ProactiveAlertCandidate(
                alert_type=ProactiveAlertType.GOAL_DEADLINE_RISK,
                severity=severity,
                notification_type=NotificationType.GOAL_MILESTONE,
                title=f"Goal may miss deadline: {goal.name}",
                message=(
                    f"Your goal '{goal.name}' needs {required_monthly:.3f} {self._currency()}/month "
                    f"to reach the target by {target_date.isoformat()}, but your current "
                    f"contribution is {contribution:.3f} {self._currency()}. Increase by "
                    f"{shortfall:.3f} {self._currency()}/month to stay on track."
                ),
                related_entity_type="goal",
                related_entity_id=goal.id,
            ))

        return candidates

    # ------------------------------------------------------------------
    # Debt pressure
    # ------------------------------------------------------------------
    async def _detect_debt_pressure(self) -> list[ProactiveAlertCandidate]:
        result = await self.db.execute(
            select(Loan).where(
                Loan.tenant_id == self.tenant_id,
                Loan.is_active.is_(True),
                Loan.is_paid_off.is_(False),
                Loan.current_balance > 0,
            )
        )
        loans = result.scalars().all()

        total_balance = Decimal("0")
        total_minimum = Decimal("0")
        underwater: list[str] = []
        for loan in loans:
            balance = _to_decimal(loan.current_balance)
            rate = _to_decimal(loan.interest_rate)
            minimum = _to_decimal(loan.minimum_payment)
            total_balance += balance
            total_minimum += minimum if minimum > 0 else balance * Decimal("0.02")
            monthly_interest = balance * (rate / Decimal("12"))
            if minimum > 0 and minimum < monthly_interest:
                underwater.append(loan.name)

        # Also consider liability accounts if no loan records.
        if not loans:
            result = await self.db.execute(
                select(Account).where(
                    Account.tenant_id == self.tenant_id,
                    Account.account_type == "Liability",
                )
            )
            accounts = result.scalars().all()
            for account in accounts:
                balance = await self._account_balance(account.id)
                if balance > 0:
                    total_balance += balance
                    total_minimum += balance * Decimal("0.02")

        if total_balance <= 0:
            return []

        avg_income = await self._avg_monthly_flow("Income")
        dti = (total_minimum / avg_income) if avg_income > 0 else Decimal("0")
        threshold = self.settings.ALERT_DEBT_TO_INCOME_THRESHOLD

        if dti < threshold and not underwater:
            return []

        severity = ProactiveAlertSeverity.CRITICAL if underwater or dti > Decimal("0.5") else ProactiveAlertSeverity.WARNING
        message_parts = [(
            f"Your total minimum debt obligations are {total_minimum:.3f} "
            f"{self._currency()} per month against an average income of "
            f"{avg_income:.3f} {self._currency()} (debt-to-minimum-income ratio "
            f"{dti:.2%})."
        )]
        if underwater:
            message_parts.append(
                f"The following loans have minimum payments that do not cover monthly interest: "
                f"{', '.join(underwater)}."
            )
        message_parts.append(
            "Review your debt payoff plan or consider the debt optimizer for guidance."
        )

        candidates = [ProactiveAlertCandidate(
            alert_type=ProactiveAlertType.DEBT_PRESSURE,
            severity=severity,
            notification_type=NotificationType.AI_INSIGHT,
            title="Debt pressure warning",
            message=" ".join(message_parts),
            related_entity_type="tenant",
            related_entity_id=self.tenant_id,
        )]
        return candidates

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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
            total += _to_decimal(debit_sum) - _to_decimal(credit_sum)
        return total

    async def _account_balance(self, account_id: int) -> Decimal:
        agg = await self.db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            ).where(JournalLine.account_id == account_id)
        )
        debit_sum, credit_sum = agg.one()
        return _to_decimal(credit_sum) - _to_decimal(debit_sum)

    def _currency(self) -> str:
        if self.user and getattr(self.user, "currency", None):
            return self.user.currency
        return self.settings.CURRENCY_DEFAULT

    async def _exists_today(self, candidate: ProactiveAlertCandidate) -> bool:
        """Prevent duplicate notifications for the same entity/type/user/day."""
        if self.user is None:
            return False
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        result = await self.db.execute(
            select(func.count(Notification.id))
            .where(Notification.tenant_id == self.tenant_id)
            .where(Notification.user_id == self.user.id)
            .where(Notification.notification_type == candidate.notification_type)
            .where(Notification.related_entity_type == candidate.related_entity_type)
            .where(Notification.related_entity_id == candidate.related_entity_id)
            .where(Notification.created_at >= today_start)
            .where(Notification.created_at < today_end)
        )
        return (result.scalar() or 0) > 0

    # ------------------------------------------------------------------
    # LLM wording enhancement
    # ------------------------------------------------------------------
    async def _enhance_message(self, candidate: ProactiveAlertCandidate) -> str:
        cost_controller = CostController(self.db, self.tenant_id)
        allowed, used, limit = await cost_controller.check_limit()
        client = LLMClient()

        if not allowed or not client.is_configured():
            return candidate.message

        try:
            candidate_dict = {
                "alert_type": candidate.alert_type.value,
                "severity": candidate.severity.value,
                "title": candidate.title,
                "message": candidate.message,
                "related_entity_type": candidate.related_entity_type,
                "related_entity_id": candidate.related_entity_id,
            }
            response = await client.complete(
                messages=proactive_alert_structured_prompt(candidate_dict),
                temperature=0.7,
                max_tokens=300,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="proactive_alert",
                user_id=self.user.id if self.user else None,
            )
            return self.safety.sanitize(response.content)
        except LLMError:
            return candidate.message
