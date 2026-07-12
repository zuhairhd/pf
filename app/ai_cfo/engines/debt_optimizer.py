"""Deterministic Debt Optimizer for the AI Personal CFO.

The optimizer is read-only: it never writes loan payments, journal entries,
accounts, or loan balances. It projects debt payoff timelines using loan data
and/or liability accounts, then optionally asks the LLM for a short narrative.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_cfo.llm.client import LLMClient, LLMError
from app.ai_cfo.llm.cost_control import CostController
from app.ai_cfo.llm.prompts import debt_optimizer_structured_prompt
from app.ai_cfo.llm.safety import SafetyFilter
from app.config import Settings, get_settings
from app.models import Account, JournalEntry, JournalLine, Loan, User


class DebtOptimizerError(Exception):
    """Raised when a debt optimization cannot be run."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DebtStrategyType(str, enum.Enum):
    AVALANCHE = "avalanche"
    SNOWBALL = "snowball"
    CUSTOM_ORDER = "custom_order"


class Confidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DebtItem:
    """A normalized debt item used for projections."""

    id: int
    name: str
    source: str  # "loan" or "account"
    balance: Decimal
    annual_rate: Decimal
    minimum_payment: Decimal
    is_assumed_minimum: bool
    is_assumed_rate: bool


MAX_PROJECTION_MONTHS = 600
DEFAULT_MIN_PAYMENT_PCT = Decimal("0.02")


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Any) -> Decimal:
    return _to_decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


class DebtOptimizer:
    """Read-only debt payoff optimizer."""

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
    async def load_debts(
        self,
        loan_ids: Optional[list[int]] = None,
        account_ids: Optional[list[int]] = None,
    ) -> list[DebtItem]:
        """Load normalized debt items from loans and/or liability accounts."""
        debts: list[DebtItem] = []
        assumptions: list[str] = []

        # 1. Try loan model records first.
        stmt = select(Loan).where(
            Loan.tenant_id == self.tenant_id,
            Loan.is_active.is_(True),
            Loan.is_paid_off.is_(False),
            Loan.current_balance > 0,
        )
        if loan_ids:
            stmt = stmt.where(Loan.id.in_(loan_ids))
        result = await self.db.execute(stmt)
        loans = result.scalars().all()

        for loan in loans:
            balance = _to_decimal(loan.current_balance)
            rate = _to_decimal(loan.interest_rate)
            min_payment = _to_decimal(loan.minimum_payment)
            is_assumed_min = False
            if min_payment <= 0:
                monthly_rate = rate / Decimal("12")
                interest = _money(balance * monthly_rate)
                min_payment = _money(max(balance * DEFAULT_MIN_PAYMENT_PCT, interest))
                is_assumed_min = True
                assumptions.append(
                    f"'{loan.name}' minimum payment was assumed as {min_payment} "
                    f"because none was provided."
                )
            debts.append(
                DebtItem(
                    id=loan.id,
                    name=loan.name,
                    source="loan",
                    balance=balance,
                    annual_rate=rate,
                    minimum_payment=min_payment,
                    is_assumed_minimum=is_assumed_min,
                    is_assumed_rate=False,
                )
            )

        # 2. Fall back to / augment with liability accounts if requested or if no loans.
        load_accounts = bool(account_ids)
        if not debts and not loan_ids:
            load_accounts = True

        if load_accounts:
            acct_stmt = select(Account).where(
                Account.tenant_id == self.tenant_id,
                Account.account_type == "Liability",
            )
            if account_ids:
                acct_stmt = acct_stmt.where(Account.id.in_(account_ids))
            # Respect family visibility for automatic loads.
            if self.user is not None:
                acct_stmt = acct_stmt.where(
                    (Account.visibility != "private")
                    | (Account.owner_user_id == self.user.id)
                    | (Account.owner_user_id.is_(None))
                )
            acct_result = await self.db.execute(acct_stmt)
            accounts = acct_result.scalars().all()

            linked_account_ids = {loan.account_id for loan in loans if loan.account_id}
            for account in accounts:
                if account.id in linked_account_ids:
                    continue
                balance = await self._account_balance(account.id)
                if balance <= 0:
                    continue
                # Liability accounts typically do not store rates/payments.
                debts.append(
                    DebtItem(
                        id=account.id,
                        name=account.name,
                        source="account",
                        balance=balance,
                        annual_rate=Decimal("0"),
                        minimum_payment=_money(balance * DEFAULT_MIN_PAYMENT_PCT),
                        is_assumed_minimum=True,
                        is_assumed_rate=True,
                    )
                )
                assumptions.append(
                    f"'{account.name}' interest rate and minimum payment were assumed "
                    "because the liability account does not store them."
                )

        return debts, assumptions

    async def _account_balance(self, account_id: int) -> Decimal:
        agg = await self.db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), Decimal("0")),
                func.coalesce(func.sum(JournalLine.credit), Decimal("0")),
            ).where(JournalLine.account_id == account_id)
        )
        debit_sum, credit_sum = agg.one()
        # Liability normal balance is credit.
        return _to_decimal(credit_sum) - _to_decimal(debit_sum)

    async def _validate_account(self, account_id: int) -> Account:
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise DebtOptimizerError("Account not found in tenant", 404)
        if self.user is not None:
            from app.services.family_account_access_service import FamilyAccountAccessService

            access = FamilyAccountAccessService(self.db, self.tenant_id, self.user)
            if not await access.can_view_account(account):
                raise DebtOptimizerError(
                    "You do not have permission to view this account", 403
                )
        return account

    async def _avg_monthly_income(self, lookback_months: int = 3) -> Decimal:
        since = date.today() - timedelta(days=30 * lookback_months)
        aggregate = func.coalesce(func.sum(JournalLine.credit), Decimal("0"))
        result = await self.db.execute(
            select(aggregate)
            .join(Account, JournalLine.account_id == Account.id)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(Account.tenant_id == self.tenant_id)
            .where(Account.account_type == "Income")
            .where(JournalEntry.date >= since)
        )
        total = _to_decimal(result.scalar())
        return total / Decimal(str(lookback_months))

    def _currency(self) -> str:
        if self.user and getattr(self.user, "currency", None):
            return self.user.currency
        return self.settings.CURRENCY_DEFAULT

    # ------------------------------------------------------------------
    # Strategy sorting
    # ------------------------------------------------------------------
    def _sort_debts(
        self,
        strategy: DebtStrategyType,
        debts: list[DebtItem],
        custom_order: Optional[list[int]] = None,
    ) -> list[DebtItem]:
        if strategy == DebtStrategyType.AVALANCHE:
            return sorted(
                debts,
                key=lambda d: (-d.annual_rate, d.balance, d.name),
            )
        if strategy == DebtStrategyType.SNOWBALL:
            return sorted(
                debts,
                key=lambda d: (d.balance, -d.annual_rate, d.name),
            )
        # custom_order
        order_map = {id_: idx for idx, id_ in enumerate(custom_order or [])}
        return sorted(
            debts,
            key=lambda d: (order_map.get(d.id, len(order_map) + 1), -d.annual_rate, d.balance),
        )

    # ------------------------------------------------------------------
    # Projection engine
    # ------------------------------------------------------------------
    def _amortize(
        self,
        debts: list[DebtItem],
        extra_monthly: Decimal,
    ) -> tuple[int, Decimal, Decimal, list[dict[str, Any]], dict[int, int]]:
        """Project payoff using the given extra monthly payment.

        Returns (months, total_paid, total_interest, schedule, payoff_months).
        """
        balances = {d.id: d.balance for d in debts}
        monthly_rates = {d.id: d.annual_rate / Decimal("12") for d in debts}
        minimums = {d.id: d.minimum_payment for d in debts}

        total_paid = Decimal("0")
        total_interest = Decimal("0")
        schedule: list[dict[str, Any]] = []
        payoff_months: dict[int, int] = {}

        month = 0
        while month < MAX_PROJECTION_MONTHS:
            if all(b <= 0 for b in balances.values()):
                break
            month += 1
            month_paid = Decimal("0")
            month_interest = Decimal("0")
            month_principal = Decimal("0")

            for d in debts:
                bal = balances[d.id]
                if bal <= 0:
                    continue
                interest = _money(bal * monthly_rates[d.id])
                min_pay = min(minimums[d.id], bal + interest)
                if min_pay < interest:
                    # Payment does not cover interest; warn caller but avoid runaway growth.
                    min_pay = interest
                principal = min_pay - interest
                if principal > bal:
                    principal = bal
                    min_pay = principal + interest
                balances[d.id] = bal - principal
                month_paid += min_pay
                month_interest += interest
                month_principal += principal
                total_paid += min_pay
                total_interest += interest
                if balances[d.id] <= 0 and d.id not in payoff_months:
                    payoff_months[d.id] = month

            # Allocate extra payment to the first non-zero target debt, cascading.
            remaining_extra = extra_monthly
            for d in debts:
                if remaining_extra <= 0:
                    break
                bal = balances[d.id]
                if bal <= 0:
                    continue
                principal = min(remaining_extra, bal)
                balances[d.id] = bal - principal
                month_paid += principal
                month_principal += principal
                total_paid += principal
                remaining_extra -= principal
                if balances[d.id] <= 0 and d.id not in payoff_months:
                    payoff_months[d.id] = month

            remaining_balance = sum(b for b in balances.values() if b > 0)
            schedule.append({
                "month_number": month,
                "total_paid": _money(total_paid),
                "total_interest": _money(total_interest),
                "total_principal": _money(month_principal),
                "remaining_balance": _money(remaining_balance),
            })

        return month, _money(total_paid), _money(total_interest), schedule, payoff_months

    # ------------------------------------------------------------------
    # Optimization
    # ------------------------------------------------------------------
    async def optimize(
        self,
        strategy: DebtStrategyType,
        extra_monthly_payment: Decimal = Decimal("0"),
        loan_ids: Optional[list[int]] = None,
        account_ids: Optional[list[int]] = None,
        custom_order: Optional[list[int]] = None,
        include_narrative: bool = False,
    ) -> dict[str, Any]:
        """Run a single debt optimization and return a serializable result."""
        if extra_monthly_payment < 0:
            raise DebtOptimizerError("extra_monthly_payment cannot be negative")

        # Validate explicit account IDs.
        if account_ids:
            for aid in account_ids:
                await self._validate_account(aid)

        debts, load_assumptions = await self.load_debts(loan_ids, account_ids)
        if not debts:
            raise DebtOptimizerError("No active debts found for this tenant", 404)

        sorted_debts = self._sort_debts(strategy, debts, custom_order)

        baseline_months, baseline_paid, baseline_interest, _, _ = self._amortize(
            sorted_debts, Decimal("0")
        )
        months, total_paid, total_interest, schedule, payoff_months = self._amortize(
            sorted_debts, extra_monthly_payment
        )

        total_balance = sum(d.balance for d in sorted_debts)
        total_minimum = sum(d.minimum_payment for d in sorted_debts)
        months_saved = max(baseline_months - months, 0)
        interest_saved = _money(baseline_interest - total_interest)

        avg_income = await self._avg_monthly_income()
        debt_to_income: Optional[str] = None
        if avg_income > 0:
            ratio = (total_minimum / avg_income).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            debt_to_income = str(ratio)

        warnings: list[dict[str, str]] = []
        assumptions = load_assumptions.copy()
        assumptions.append(
            "Interest is compounded monthly and rates remain fixed over the projection."
        )
        assumptions.append(
            "Minimum payments continue unchanged unless a debt is paid off early."
        )

        if any(d.is_assumed_minimum for d in sorted_debts):
            assumptions.append(
                "Missing minimum payments were estimated; actual terms may differ."
            )
        if any(d.is_assumed_rate for d in sorted_debts):
            assumptions.append(
                "Missing interest rates were estimated as 0%; actual rates may differ."
            )

        for d in sorted_debts:
            monthly_rate = d.annual_rate / Decimal("12")
            monthly_interest = _money(d.balance * monthly_rate)
            if d.minimum_payment < monthly_interest:
                warnings.append({
                    "severity": "high",
                    "message": (
                        f"'{d.name}' minimum payment ({d.minimum_payment}) does not cover "
                        f"monthly interest ({monthly_interest}); the debt may not reduce."
                    ),
                })

        if months >= MAX_PROJECTION_MONTHS:
            warnings.append({
                "severity": "medium",
                "message": (
                    f"Projection reached the maximum horizon of {MAX_PROJECTION_MONTHS} months; "
                    "some debts may not be fully paid off under these assumptions."
                ),
            })

        if debt_to_income is not None and Decimal(debt_to_income) > Decimal("0.36"):
            warnings.append({
                "severity": "medium",
                "message": (
                    "Debt-to-income ratio is above 36%; consider reviewing minimum obligations."
                ),
            })

        confidence = Confidence.HIGH
        if any(d.is_assumed_rate or d.is_assumed_minimum for d in sorted_debts):
            confidence = Confidence.MEDIUM
        if all(d.is_assumed_rate and d.is_assumed_minimum for d in sorted_debts):
            confidence = Confidence.LOW
        if months >= MAX_PROJECTION_MONTHS or warnings:
            confidence = Confidence.LOW

        payoff_order = [
            {
                "id": d.id,
                "name": d.name,
                "source": d.source,
                "balance": d.balance,
                "annual_rate": d.annual_rate,
                "minimum_payment": d.minimum_payment,
                "payoff_month": payoff_months.get(d.id),
            }
            for d in sorted_debts
        ]

        result = {
            "strategy": strategy.value,
            "currency": self._currency(),
            "total_balance": _money(total_balance),
            "total_minimum_payment": _money(total_minimum),
            "extra_monthly_payment": _money(extra_monthly_payment),
            "debt_to_income_ratio": debt_to_income,
            "payoff_months": months,
            "baseline_months": baseline_months,
            "months_saved": months_saved,
            "total_paid": _money(total_paid),
            "total_interest": _money(total_interest),
            "baseline_total_interest": _money(baseline_interest),
            "interest_saved": interest_saved,
            "debt_count": len(sorted_debts),
            "payoff_order": payoff_order,
            "assumptions": [{"description": a} for a in assumptions],
            "warnings": warnings,
            "confidence": confidence.value,
            "monthly_schedule": schedule,
            "narrative": "",
        }

        if include_narrative:
            result["narrative"] = await self._generate_narrative(result)
        else:
            result["narrative"] = self._deterministic_narrative(result)

        return result

    async def compare(
        self,
        extra_monthly_payment: Decimal = Decimal("0"),
        loan_ids: Optional[list[int]] = None,
        account_ids: Optional[list[int]] = None,
        include_narrative: bool = False,
    ) -> dict[str, Any]:
        """Compare avalanche vs snowball strategies."""
        avalanche = await self.optimize(
            DebtStrategyType.AVALANCHE,
            extra_monthly_payment=extra_monthly_payment,
            loan_ids=loan_ids,
            account_ids=account_ids,
            include_narrative=include_narrative,
        )
        snowball = await self.optimize(
            DebtStrategyType.SNOWBALL,
            extra_monthly_payment=extra_monthly_payment,
            loan_ids=loan_ids,
            account_ids=account_ids,
            include_narrative=include_narrative,
        )

        if avalanche["interest_saved"] >= snowball["interest_saved"]:
            recommendation = (
                "Avalanche is projected to save the most interest. Snowball may provide "
                "quicker psychological wins by paying smaller balances first."
            )
        else:
            recommendation = (
                "Snowball is projected to save the most interest in this case. Compare "
                "payoff timelines to choose the strategy that best fits your motivation."
            )

        return {
            "results": [avalanche, snowball],
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------
    # Narrative
    # ------------------------------------------------------------------
    def _deterministic_narrative(self, result: dict[str, Any]) -> str:
        lines = [
            f"Strategy: {result['strategy']}.",
            f"Total debt balance: {result['total_balance']} {result['currency']}.",
            f"Projected payoff: {result['payoff_months']} months "
            f"(baseline {result['baseline_months']} months).",
            f"Estimated total interest: {result['total_interest']} {result['currency']}.",
            f"Estimated interest saved: {result['interest_saved']} {result['currency']}.",
        ]
        if result["warnings"]:
            lines.append("Warnings:")
            for warning in result["warnings"]:
                lines.append(f"- {warning['message']}")
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
                messages=debt_optimizer_structured_prompt(result),
                temperature=0.7,
                max_tokens=700,
            )
            await cost_controller.record_usage(
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                total_tokens=response.total_tokens,
                cost_usd=response.cost_usd,
                request_type="debt_optimizer",
                user_id=self.user.id if self.user else None,
            )
            return self.safety.sanitize(response.content)
        except LLMError:
            return self._deterministic_narrative(result)
