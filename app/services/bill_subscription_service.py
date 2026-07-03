"""Services for bills, subscriptions, and fixed-commitment summaries."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import Bill, Subscription
from app.models.subscription import SubscriptionStatus


FREQUENCY_DAYS = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
    "yearly": 365,
}


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
            typical_amount=data["typical_amount"],
            due_date=data["due_date"],
            frequency=data.get("frequency", "monthly"),
            is_auto_pay=data.get("is_auto_pay", False),
            payment_method=data.get("payment_method"),
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
        for field in ("name", "provider", "typical_amount", "due_date", "frequency", "is_auto_pay", "payment_method"):
            if field in data and data[field] is not None:
                setattr(bill, field, data[field])
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def delete(self, bill: Bill) -> None:
        await self.db.delete(bill)
        await self.db.commit()

    async def mark_paid(self, bill: Bill) -> Bill:
        """Mark a bill as paid.

        Accounting-entry creation is intentionally deferred to BILL-801A so that
        this card stays focused on the Bills/Subscriptions API surface and does
        not bypass the double-entry engine.
        """
        bill.is_paid = True
        bill.paid_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(bill)
        return bill

    async def mark_unpaid(self, bill: Bill) -> Bill:
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
            amount=data["amount"],
            frequency=data.get("frequency", "monthly"),
            next_billing_date=data["next_billing_date"],
            category=data.get("category"),
            account_id=data.get("account_id"),
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
        for field in ("name", "provider", "amount", "frequency", "next_billing_date", "category", "account_id"):
            if field in data and data[field] is not None:
                setattr(subscription, field, data[field])
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription

    async def delete(self, subscription: Subscription) -> None:
        await self.db.delete(subscription)
        await self.db.commit()

    async def mark_paid(self, subscription: Subscription) -> Subscription:
        """Record that the latest renewal has been paid.

        The next billing date is advanced by one period. No journal entry is
        created here; see BILL-801A for accounting-engine integration.
        """
        days = FREQUENCY_DAYS.get(subscription.frequency, 30)
        subscription.next_billing_date = subscription.next_billing_date + timedelta(days=days)
        await self.db.commit()
        await self.db.refresh(subscription)
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
