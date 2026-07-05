"""Services for bills, subscriptions, and fixed-commitment summaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import Account, Bill, JournalEntry, Subscription
from app.models.subscription import SubscriptionStatus
from app.schemas.accounting import JournalEntryCreate, JournalLineCreate
from app.services.accounting_service import AccountingService


FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
    "yearly": 365,
}


def _coerce_date(value) -> date:
    """Convert a date-like payload value into a Python date."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Unsupported date value: {value!r}")


def _coerce_decimal(value) -> Decimal:
    """Convert a numeric payload value into a Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class BillService:
    """CRUD and status operations for bills."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def _base_query(self):
        return select(Bill).where(Bill.tenant_id == self.tenant_id)

    async def create(self, data: dict) -> Bill:
        bill = Bill(
            tenant_id=self.tenant_id,
            name=data["name"],
            provider=data["provider"],
            typical_amount=_coerce_decimal(data["typical_amount"]),
            due_date=_coerce_date(data["due_date"]),
            frequency=data.get("frequency", "monthly"),
            is_auto_pay=data.get("is_auto_pay", False),
            payment_method=data.get("payment_method"),
            payment_account_id=data.get("payment_account_id"),
            expense_account_id=data.get("expense_account_id"),
            is_active=True,
            is_paid=False,
        )
        self.db.add(bill)
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def list_bills(self, *, status: Optional[str] = None) -> List[Bill]:
        query = self._base_query()
        if status == "paid":
            query = query.where(Bill.is_paid.is_(True))
        elif status == "overdue":
            query = query.where(
                and_(Bill.is_paid.is_(False), Bill.is_active.is_(True), Bill.due_date < date.today())
            )
        elif status == "upcoming":
            query = query.where(
                and_(Bill.is_paid.is_(False), Bill.is_active.is_(True), Bill.due_date >= date.today())
            )
        elif status == "cancelled":
            query = query.where(Bill.is_active.is_(False))
        result = await self.db.execute(query.order_by(Bill.due_date))
        return list(result.scalars().all())

    async def get(self, bill_id: int) -> Optional[Bill]:
        result = await self.db.execute(
            self._base_query().where(Bill.id == bill_id)
        )
        return result.scalar_one_or_none()

    async def update(self, bill: Bill, data: dict) -> Bill:
        for field in (
            "name",
            "provider",
            "typical_amount",
            "due_date",
            "frequency",
            "is_auto_pay",
            "payment_method",
            "payment_account_id",
            "expense_account_id",
        ):
            if field in data and data[field] is not None:
                value = data[field]
                if field == "due_date":
                    value = _coerce_date(value)
                elif field == "typical_amount":
                    value = _coerce_decimal(value)
                setattr(bill, field, value)
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def delete(self, bill: Bill) -> None:
        await self.db.delete(bill)
        await self.db.commit()

    async def _get_account(self, account_id: int) -> Optional[Account]:
        """Fetch a tenant account by ID."""
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_payment_account(account: Account) -> None:
        if account.account_type != "Asset":
            raise ValueError("Payment account must be an Asset account")

    @staticmethod
    def _validate_expense_account(account: Account) -> None:
        if account.account_type != "Expense":
            raise ValueError("Expense account must be an Expense account")

    async def _create_payment_journal_entry(
        self,
        *,
        amount: Decimal,
        payment_date: date,
        narration: str,
        reference: str,
        line_description: Optional[str],
        payment_account: Account,
        expense_account: Account,
        source: str,
    ) -> JournalEntry:
        """Create a balanced double-entry journal entry for a payment."""
        existing = await self.db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == self.tenant_id,
                JournalEntry.reference == reference,
            )
        )
        existing_entry = existing.scalar_one_or_none()
        if existing_entry is not None:
            return existing_entry

        accounting = AccountingService(self.db, self.tenant_id)
        entry = await accounting.create_journal_entry(
            JournalEntryCreate(
                date=payment_date,
                narration=narration,
                reference=reference,
                lines=[
                    JournalLineCreate(
                        account_id=expense_account.id,
                        debit=amount,
                        credit=Decimal("0"),
                        description=line_description or narration,
                    ),
                    JournalLineCreate(
                        account_id=payment_account.id,
                        debit=Decimal("0"),
                        credit=amount,
                        description=line_description or narration,
                    ),
                ],
            )
        )
        entry.source = source
        await self.db.commit()
        return entry

    async def mark_paid(self, bill: Bill, data: Optional[dict] = None) -> Bill:
        """Mark a bill as paid and post a balanced journal entry.

        Idempotent: if ``payment_journal_entry_id`` is already set, the existing
        journal entry is reused and no new entry is created.
        """
        data = data or {}
        if bill.payment_journal_entry_id:
            return bill

        payment_account_id = data.get("payment_account_id") or bill.payment_account_id
        expense_account_id = data.get("expense_account_id") or bill.expense_account_id
        if not payment_account_id:
            raise ValueError("Payment account is required")
        if not expense_account_id:
            raise ValueError("Expense account is required")

        payment_account = await self._get_account(payment_account_id)
        if payment_account is None:
            raise ValueError("Payment account not found")
        self._validate_payment_account(payment_account)

        expense_account = await self._get_account(expense_account_id)
        if expense_account is None:
            raise ValueError("Expense account not found")
        self._validate_expense_account(expense_account)

        payment_date = data.get("payment_date")
        if isinstance(payment_date, str):
            payment_date = date.fromisoformat(payment_date)
        if payment_date is None:
            payment_date = date.today()

        narration = f"Bill payment: {bill.name}"
        reference = f"BILL-{self.tenant_id}-{bill.id}"
        line_description = data.get("notes")

        entry = await self._create_payment_journal_entry(
            amount=bill.typical_amount,
            payment_date=payment_date,
            narration=narration,
            reference=reference,
            line_description=line_description,
            payment_account=payment_account,
            expense_account=expense_account,
            source="bill_payment",
        )

        bill.is_paid = True
        bill.paid_at = datetime.utcnow()
        bill.payment_account_id = payment_account.id
        bill.expense_account_id = expense_account.id
        bill.payment_journal_entry_id = entry.id
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def mark_unpaid(self, bill: Bill) -> Bill:
        """Revert a bill to unpaid.

        Bills with a posted payment journal entry cannot be marked unpaid because
        the accounting engine does not yet support journal-entry reversal.
        """
        if bill.payment_journal_entry_id:
            raise ValueError(
                "Cannot mark bill unpaid: a payment journal entry has already been posted"
            )
        bill.is_paid = False
        bill.paid_at = None
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def cancel(self, bill: Bill) -> Bill:
        bill.is_active = False
        await self.db.commit()
        await self.db.refresh(bill)
        return bill


class SubscriptionService:
    """CRUD and status operations for subscriptions."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def _base_query(self):
        return select(Subscription).where(Subscription.tenant_id == self.tenant_id)

    async def create(self, data: dict) -> Subscription:
        subscription = Subscription(
            tenant_id=self.tenant_id,
            name=data["name"],
            provider=data["provider"],
            amount=_coerce_decimal(data["amount"]),
            frequency=data.get("frequency", "monthly"),
            next_billing_date=_coerce_date(data["next_billing_date"]),
            category=data.get("category"),
            account_id=data.get("account_id"),
            payment_account_id=data.get("payment_account_id"),
            expense_account_id=data.get("expense_account_id"),
            status=SubscriptionStatus.ACTIVE,
            is_active=True,
        )
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def list_subscriptions(self, *, status: Optional[str] = None) -> List[Subscription]:
        query = self._base_query()
        if status == "active":
            query = query.where(Subscription.status == SubscriptionStatus.ACTIVE)
        elif status == "paused":
            query = query.where(Subscription.status == SubscriptionStatus.PAUSED)
        elif status == "cancelled":
            query = query.where(Subscription.status == SubscriptionStatus.CANCELLED)
        result = await self.db.execute(query.order_by(Subscription.next_billing_date))
        return list(result.scalars().all())

    async def get(self, subscription_id: int) -> Optional[Subscription]:
        result = await self.db.execute(
            self._base_query().where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def update(self, subscription: Subscription, data: dict) -> Subscription:
        for field in (
            "name",
            "provider",
            "amount",
            "frequency",
            "next_billing_date",
            "category",
            "account_id",
            "payment_account_id",
            "expense_account_id",
        ):
            if field in data and data[field] is not None:
                value = data[field]
                if field == "next_billing_date":
                    value = _coerce_date(value)
                elif field == "amount":
                    value = _coerce_decimal(value)
                setattr(subscription, field, value)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def delete(self, subscription: Subscription) -> None:
        await self.db.delete(subscription)
        await self.db.commit()

    async def _get_account(self, account_id: int) -> Optional[Account]:
        """Fetch a tenant account by ID."""
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _validate_payment_account(account: Account) -> None:
        if account.account_type != "Asset":
            raise ValueError("Payment account must be an Asset account")

    @staticmethod
    def _validate_expense_account(account: Account) -> None:
        if account.account_type != "Expense":
            raise ValueError("Expense account must be an Expense account")

    async def _create_payment_journal_entry(
        self,
        *,
        amount: Decimal,
        payment_date: date,
        narration: str,
        reference: str,
        line_description: Optional[str],
        payment_account: Account,
        expense_account: Account,
        source: str,
    ) -> JournalEntry:
        """Create a balanced double-entry journal entry for a payment."""
        existing = await self.db.execute(
            select(JournalEntry).where(
                JournalEntry.tenant_id == self.tenant_id,
                JournalEntry.reference == reference,
            )
        )
        existing_entry = existing.scalar_one_or_none()
        if existing_entry is not None:
            return existing_entry

        accounting = AccountingService(self.db, self.tenant_id)
        entry = await accounting.create_journal_entry(
            JournalEntryCreate(
                date=payment_date,
                narration=narration,
                reference=reference,
                lines=[
                    JournalLineCreate(
                        account_id=expense_account.id,
                        debit=amount,
                        credit=Decimal("0"),
                        description=line_description or narration,
                    ),
                    JournalLineCreate(
                        account_id=payment_account.id,
                        debit=Decimal("0"),
                        credit=amount,
                        description=line_description or narration,
                    ),
                ],
            )
        )
        entry.source = source
        await self.db.commit()
        return entry

    async def mark_paid(self, subscription: Subscription, data: Optional[dict] = None) -> Subscription:
        """Record that the latest renewal has been paid, post a journal entry, and advance billing.

        Idempotent: if ``payment_journal_entry_id`` is already set, the existing
        journal entry is reused and no new entry is created.
        """
        data = data or {}

        if subscription.payment_journal_entry_id:
            return subscription

        payment_account_id = data.get("payment_account_id") or subscription.payment_account_id
        expense_account_id = data.get("expense_account_id") or subscription.expense_account_id
        if not payment_account_id:
            raise ValueError("Payment account is required")
        if not expense_account_id:
            raise ValueError("Expense account is required")

        payment_account = await self._get_account(payment_account_id)
        if payment_account is None:
            raise ValueError("Payment account not found")
        self._validate_payment_account(payment_account)

        expense_account = await self._get_account(expense_account_id)
        if expense_account is None:
            raise ValueError("Expense account not found")
        self._validate_expense_account(expense_account)

        payment_date = data.get("payment_date")
        if isinstance(payment_date, str):
            payment_date = date.fromisoformat(payment_date)
        if payment_date is None:
            payment_date = date.today()

        narration = f"Subscription payment: {subscription.name}"
        reference = f"SUB-{self.tenant_id}-{subscription.id}"
        line_description = data.get("notes")

        entry = await self._create_payment_journal_entry(
            amount=subscription.amount,
            payment_date=payment_date,
            narration=narration,
            reference=reference,
            line_description=line_description,
            payment_account=payment_account,
            expense_account=expense_account,
            source="subscription_payment",
        )
        subscription.payment_account_id = payment_account.id
        subscription.expense_account_id = expense_account.id
        subscription.payment_journal_entry_id = entry.id

        days = FREQUENCY_DAYS.get(subscription.frequency, 30)
        subscription.next_billing_date = subscription.next_billing_date + timedelta(days=days)
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def mark_unpaid(self, subscription: Subscription) -> Subscription:
        """Block reverting a paid subscription if a journal entry was posted.

        The accounting engine does not yet support journal-entry reversal.
        """
        if subscription.payment_journal_entry_id:
            raise ValueError(
                "Cannot mark subscription unpaid: a payment journal entry has already been posted"
            )
        return subscription

    async def cancel(self, subscription: Subscription) -> Subscription:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.is_active = False
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def pause(self, subscription: Subscription) -> Subscription:
        subscription.status = SubscriptionStatus.PAUSED
        subscription.is_active = False
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def activate(self, subscription: Subscription) -> Subscription:
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.is_active = True
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    @staticmethod
    def days_until_renewal(subscription: Subscription) -> int:
        delta = subscription.next_billing_date - date.today()
        return delta.days

    @staticmethod
    def monthly_equivalent(subscription: Subscription) -> Decimal:
        """Return the exact monthly cost equivalent for the subscription."""
        amount = subscription.amount
        freq = subscription.frequency
        if freq == "daily":
            return (amount * Decimal("365") / Decimal("12")).quantize(Decimal("0.001"))
        if freq == "weekly":
            return (amount * Decimal("52") / Decimal("12")).quantize(Decimal("0.001"))
        if freq == "monthly":
            return amount.quantize(Decimal("0.001"))
        if freq == "quarterly":
            return (amount / Decimal("3")).quantize(Decimal("0.001"))
        if freq == "yearly":
            return (amount / Decimal("12")).quantize(Decimal("0.001"))
        return amount.quantize(Decimal("0.001"))

    @staticmethod
    def yearly_equivalent(subscription: Subscription) -> Decimal:
        """Return the exact yearly cost equivalent for the subscription."""
        amount = subscription.amount
        freq = subscription.frequency
        if freq == "daily":
            return (amount * Decimal("365")).quantize(Decimal("0.001"))
        if freq == "weekly":
            return (amount * Decimal("52")).quantize(Decimal("0.001"))
        if freq == "monthly":
            return (amount * Decimal("12")).quantize(Decimal("0.001"))
        if freq == "quarterly":
            return (amount * Decimal("4")).quantize(Decimal("0.001"))
        if freq == "yearly":
            return amount.quantize(Decimal("0.001"))
        return amount.quantize(Decimal("0.001"))


class CommitmentService:
    """Dashboard-style summaries of upcoming bills and subscriptions."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        self.bill_service = BillService(db, tenant_id)
        self.subscription_service = SubscriptionService(db, tenant_id)

    async def upcoming_bills(self, days: int = 7) -> List[Bill]:
        cutoff = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(Bill)
            .where(Bill.tenant_id == self.tenant_id)
            .where(Bill.is_paid.is_(False))
            .where(Bill.is_active.is_(True))
            .where(Bill.due_date <= cutoff)
            .order_by(Bill.due_date)
        )
        return list(result.scalars().all())

    async def overdue_bills(self) -> List[Bill]:
        return await self.bill_service.list_bills(status="overdue")

    async def upcoming_renewals(self, days: int = 30) -> List[Subscription]:
        cutoff = date.today() + timedelta(days=days)
        result = await self.db.execute(
            select(Subscription)
            .where(Subscription.tenant_id == self.tenant_id)
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
            .where(Subscription.next_billing_date <= cutoff)
            .order_by(Subscription.next_billing_date)
        )
        return list(result.scalars().all())

    async def monthly_subscription_total(self) -> Decimal:
        subscriptions = await self.subscription_service.list_subscriptions(status="active")
        total = Decimal("0")
        for sub in subscriptions:
            total += self.subscription_service.monthly_equivalent(sub)
        return total.quantize(Decimal("0.001"))

    async def summary(self) -> dict:
        upcoming = await self.upcoming_bills(7)
        overdue = await self.overdue_bills()
        renewals = await self.upcoming_renewals(30)
        monthly_subs = await self.monthly_subscription_total()

        upcoming_total = sum((b.typical_amount for b in upcoming), Decimal("0"))
        overdue_total = sum((b.typical_amount for b in overdue), Decimal("0"))
        renewals_total = sum((s.amount for s in renewals), Decimal("0"))

        return {
            "upcoming_bills_count": len(upcoming),
            "upcoming_bills_total": upcoming_total.quantize(Decimal("0.001")),
            "overdue_bills_count": len(overdue),
            "overdue_bills_total": overdue_total.quantize(Decimal("0.001")),
            "upcoming_renewals_count": len(renewals),
            "upcoming_renewals_total": renewals_total.quantize(Decimal("0.001")),
            "monthly_subscription_total": monthly_subs,
            "total_fixed_commitments_this_month": (upcoming_total + monthly_subs).quantize(Decimal("0.001")),
        }
