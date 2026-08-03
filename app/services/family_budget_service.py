"""Family budget service: visibility, permissions, CRUD, and budget-vs-actual.

Budgets are conceptually closer to accounts than to goals: they can be
private (owner-only), shared (adults), or family-wide, and a tenant does
not need a Family profile to use private budgets. Role resolution and
account-visibility enforcement are delegated to FamilyAccountAccessService
so budget permissions stay consistent with account permissions.

This service never creates transactions or journal entries, and never
modifies account balances — budget-vs-actual figures are read-only
aggregates over posted journal lines.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, BudgetCategory, Family, JournalEntry, JournalLine, User
from app.models.budget import BudgetStatus, BudgetVisibility
from app.models.family import FamilyRole
from app.schemas.budget import (
    BudgetCategoryCreate,
    BudgetCategoryUpdate,
    FamilyBudgetCreate,
    FamilyBudgetUpdate,
)
from app.services.family_account_access_service import FamilyAccountAccessService


class FamilyBudgetServiceError(Exception):
    """Raised when a family budget operation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FamilyBudgetService:
    """CRUD, permission checks, and budget-vs-actual calculations for budgets."""

    def __init__(self, db: AsyncSession, tenant_id: int, user: User):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self.access = FamilyAccountAccessService(db, tenant_id, user)

    # -----------------------------------------------------------------------
    # Role/family helpers
    # -----------------------------------------------------------------------

    async def _get_role(self) -> FamilyRole:
        return await self.access.get_role()

    def _is_elevated(self, role: FamilyRole) -> bool:
        return role in (FamilyRole.HEAD, FamilyRole.PARENT)

    async def _get_family(self) -> Optional[Family]:
        result = await self.db.execute(
            select(Family).where(Family.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    # -----------------------------------------------------------------------
    # Permission checks
    # -----------------------------------------------------------------------

    async def can_user_view_budget(self, budget: Budget) -> bool:
        """Whether the current user may view this budget."""
        role = await self._get_role()
        if self._is_elevated(role):
            return True

        if budget.visibility == BudgetVisibility.SHARED.value:
            return role in (FamilyRole.ADULT, FamilyRole.TEEN, FamilyRole.VIEWER)

        if budget.visibility == BudgetVisibility.FAMILY.value:
            return role in (FamilyRole.ADULT, FamilyRole.TEEN, FamilyRole.CHILD, FamilyRole.VIEWER)

        if budget.visibility == BudgetVisibility.PRIVATE.value:
            return budget.owner_user_id is not None and budget.owner_user_id == self.user.id

        return False

    async def can_user_manage_budget(self, budget: Budget) -> bool:
        """Whether the current user may edit, archive, or manage this budget's categories."""
        role = await self._get_role()
        if self._is_elevated(role):
            return True

        if budget.visibility in (BudgetVisibility.SHARED.value, BudgetVisibility.FAMILY.value):
            return role == FamilyRole.ADULT

        if budget.visibility == BudgetVisibility.PRIVATE.value:
            if role in (FamilyRole.ADULT, FamilyRole.TEEN):
                return budget.owner_user_id == self.user.id
            return False

        return False

    def _can_create(self, role: FamilyRole, visibility: str) -> bool:
        if role == FamilyRole.VIEWER:
            return False
        if role == FamilyRole.CHILD:
            # Child role is view-only for budgets (no create/manage rights).
            return False
        if self._is_elevated(role):
            return True
        if role == FamilyRole.ADULT:
            return True
        if role == FamilyRole.TEEN:
            return visibility == BudgetVisibility.PRIVATE.value
        return False

    async def require_view(self, budget: Budget) -> None:
        if not await self.can_user_view_budget(budget):
            raise FamilyBudgetServiceError("You do not have permission to view this budget")

    async def require_manage(self, budget: Budget) -> None:
        if not await self.can_user_manage_budget(budget):
            raise FamilyBudgetServiceError("You do not have permission to manage this budget")

    # -----------------------------------------------------------------------
    # Budget CRUD
    # -----------------------------------------------------------------------

    async def create_budget(self, data: FamilyBudgetCreate) -> Budget:
        role = await self._get_role()
        if not self._can_create(role, data.visibility):
            raise FamilyBudgetServiceError("Permission denied: you cannot create a budget with this visibility")

        if data.end_date < data.start_date:
            raise FamilyBudgetServiceError("end_date must be on or after start_date")

        family = await self._get_family()
        total_budgeted = sum((cat.budgeted_amount for cat in data.categories), Decimal("0"))

        budget = Budget(
            tenant_id=self.tenant_id,
            family_id=family.id if family else None,
            owner_user_id=self.user.id,
            created_by_user_id=self.user.id,
            name=data.name,
            period=data.period,
            start_date=data.start_date,
            end_date=data.end_date,
            currency=data.currency,
            visibility=data.visibility,
            status=BudgetStatus.ACTIVE.value,
            is_active=True,
            total_budgeted=total_budgeted,
            total_actual=Decimal("0"),
        )
        self.db.add(budget)
        await self.db.flush()

        for cat_data in data.categories:
            await self._validate_category_account(cat_data.account_id)
            category = BudgetCategory(
                budget_id=budget.id,
                name=cat_data.name,
                account_id=cat_data.account_id,
                budgeted_amount=cat_data.budgeted_amount,
                alert_threshold=cat_data.alert_threshold,
            )
            self.db.add(category)

        await self.db.commit()
        await self.db.refresh(budget)
        return budget

    async def _get_budget_raw(self, budget_id: int) -> Optional[Budget]:
        result = await self.db.execute(
            select(Budget).where(
                Budget.id == budget_id,
                Budget.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_budget(self, budget_id: int) -> Budget:
        budget = await self._get_budget_raw(budget_id)
        if budget is None:
            raise FamilyBudgetServiceError("Budget not found")
        await self.require_view(budget)
        return budget

    async def list_visible_budgets_for_user(self) -> list[Budget]:
        """Return budgets in the tenant the current user is allowed to see."""
        role = await self._get_role()
        query = select(Budget).where(Budget.tenant_id == self.tenant_id)

        if not self._is_elevated(role):
            if role == FamilyRole.ADULT:
                query = query.where(
                    or_(
                        Budget.visibility.in_(
                            (BudgetVisibility.SHARED.value, BudgetVisibility.FAMILY.value)
                        ),
                        and_(
                            Budget.visibility == BudgetVisibility.PRIVATE.value,
                            Budget.owner_user_id == self.user.id,
                        ),
                    )
                )
            elif role == FamilyRole.TEEN:
                query = query.where(
                    or_(
                        Budget.visibility.in_(
                            (BudgetVisibility.SHARED.value, BudgetVisibility.FAMILY.value)
                        ),
                        and_(
                            Budget.visibility == BudgetVisibility.PRIVATE.value,
                            Budget.owner_user_id == self.user.id,
                        ),
                    )
                )
            elif role == FamilyRole.CHILD:
                query = query.where(
                    or_(
                        Budget.visibility == BudgetVisibility.FAMILY.value,
                        and_(
                            Budget.visibility == BudgetVisibility.PRIVATE.value,
                            Budget.owner_user_id == self.user.id,
                        ),
                    )
                )
            else:  # VIEWER
                query = query.where(
                    Budget.visibility.in_(
                        (BudgetVisibility.SHARED.value, BudgetVisibility.FAMILY.value)
                    )
                )

        result = await self.db.execute(query.order_by(Budget.start_date.desc(), Budget.created_at.desc()))
        return list(result.scalars().all())

    async def update_budget(self, budget_id: int, data: FamilyBudgetUpdate) -> Budget:
        budget = await self.get_budget(budget_id)
        await self.require_manage(budget)

        update_data = data.model_dump(exclude_unset=True)
        if "start_date" in update_data or "end_date" in update_data:
            new_start = update_data.get("start_date", budget.start_date)
            new_end = update_data.get("end_date", budget.end_date)
            if new_end < new_start:
                raise FamilyBudgetServiceError("end_date must be on or after start_date")

        for field in ("name", "start_date", "end_date", "visibility", "status"):
            if field in update_data and update_data[field] is not None:
                setattr(budget, field, update_data[field])

        if "status" in update_data and update_data["status"] is not None:
            budget.is_active = update_data["status"] == BudgetStatus.ACTIVE.value

        await self.db.commit()
        await self.db.refresh(budget)
        return budget

    async def archive_budget(self, budget_id: int) -> Budget:
        budget = await self.get_budget(budget_id)
        await self.require_manage(budget)
        budget.status = BudgetStatus.ARCHIVED.value
        budget.is_active = False
        await self.db.commit()
        await self.db.refresh(budget)
        return budget

    # -----------------------------------------------------------------------
    # Budget categories
    # -----------------------------------------------------------------------

    async def _validate_category_account(self, account_id: Optional[int]) -> Optional[Account]:
        if account_id is None:
            return None
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise FamilyBudgetServiceError("Account not found in this tenant")
        if account.account_type != "Expense":
            raise FamilyBudgetServiceError("Budget categories must link to an Expense account")
        if not await self.access.can_view_account(account):
            raise FamilyBudgetServiceError("You do not have access to the selected account")
        return account

    async def _get_category(self, budget: Budget, category_id: int) -> BudgetCategory:
        result = await self.db.execute(
            select(BudgetCategory).where(
                BudgetCategory.id == category_id,
                BudgetCategory.budget_id == budget.id,
            )
        )
        category = result.scalar_one_or_none()
        if category is None:
            raise FamilyBudgetServiceError("Budget category not found")
        return category

    async def create_budget_category(self, budget_id: int, data: BudgetCategoryCreate) -> BudgetCategory:
        budget = await self.get_budget(budget_id)
        await self.require_manage(budget)
        await self._validate_category_account(data.account_id)

        category = BudgetCategory(
            budget_id=budget.id,
            name=data.name,
            account_id=data.account_id,
            budgeted_amount=data.budgeted_amount,
            alert_threshold=data.alert_threshold,
        )
        self.db.add(category)
        budget.total_budgeted = budget.total_budgeted + data.budgeted_amount
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def update_budget_category(
        self, budget_id: int, category_id: int, data: BudgetCategoryUpdate
    ) -> BudgetCategory:
        budget = await self.get_budget(budget_id)
        await self.require_manage(budget)
        category = await self._get_category(budget, category_id)

        update_data = data.model_dump(exclude_unset=True)
        if "account_id" in update_data:
            await self._validate_category_account(update_data["account_id"])

        old_amount = category.budgeted_amount
        for field in ("name", "account_id", "budgeted_amount", "alert_threshold"):
            if field in update_data and update_data[field] is not None:
                setattr(category, field, update_data[field])

        if "budgeted_amount" in update_data and update_data["budgeted_amount"] is not None:
            budget.total_budgeted = budget.total_budgeted - old_amount + category.budgeted_amount

        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete_budget_category(self, budget_id: int, category_id: int) -> None:
        budget = await self.get_budget(budget_id)
        await self.require_manage(budget)
        category = await self._get_category(budget, category_id)

        budget.total_budgeted = max(budget.total_budgeted - category.budgeted_amount, Decimal("0"))
        await self.db.delete(category)
        await self.db.commit()

    # -----------------------------------------------------------------------
    # Budget vs actual (read-only; never persists financial data)
    # -----------------------------------------------------------------------

    async def _category_actual(self, account_id: Optional[int], start: date, end: date) -> Decimal:
        """Sum posted expense-account debit activity for a category within the budget period."""
        if account_id is None:
            return Decimal("0")
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalLine.debit), Decimal("0")))
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(JournalLine.account_id == account_id)
            .where(JournalEntry.tenant_id == self.tenant_id)
            .where(JournalEntry.date >= start)
            .where(JournalEntry.date <= end)
        )
        return result.scalar() or Decimal("0")

    async def calculate_budget_actuals(self, budget: Budget) -> list[dict]:
        """Return per-category actual/remaining/percent, computed fresh (not persisted)."""
        categories = []
        for category in budget.categories:
            actual = await self._category_actual(category.account_id, budget.start_date, budget.end_date)
            remaining = category.budgeted_amount - actual
            if category.budgeted_amount > 0:
                percent_used = (actual / category.budgeted_amount * Decimal("100")).quantize(Decimal("0.01"))
            else:
                percent_used = Decimal("0") if actual == 0 else Decimal("100")

            account_name = None
            if category.account_id is not None:
                account = await self._validate_category_account_silent(category.account_id)
                if account is not None:
                    account_name = account.name

            categories.append({
                "id": category.id,
                "budget_id": category.budget_id,
                "name": category.name,
                "account_id": category.account_id,
                "account_name": account_name,
                "budgeted_amount": category.budgeted_amount,
                "actual_amount": actual,
                "remaining_amount": remaining,
                "percent_used": percent_used,
                "alert_threshold": category.alert_threshold,
                "is_over_budget": percent_used >= Decimal("100"),
                "is_near_limit": category.alert_threshold <= percent_used < Decimal("100"),
            })
        return categories

    async def _validate_category_account_silent(self, account_id: int) -> Optional[Account]:
        """Look up an account without raising; used for read-only display of the name."""
        result = await self.db.execute(
            select(Account).where(Account.id == account_id, Account.tenant_id == self.tenant_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            return None
        if not await self.access.can_view_account(account):
            return None
        return account

    async def calculate_budget_summary(self, budget_id: int) -> dict:
        """Return a full read-only budget-vs-actual summary for a budget."""
        budget = await self.get_budget(budget_id)
        categories = await self.calculate_budget_actuals(budget)

        total_planned = sum((c["budgeted_amount"] for c in categories), Decimal("0"))
        total_actual = sum((c["actual_amount"] for c in categories), Decimal("0"))
        total_remaining = total_planned - total_actual
        percent_used = (
            (total_actual / total_planned * Decimal("100")).quantize(Decimal("0.01"))
            if total_planned > 0
            else Decimal("0")
        )

        over_budget_ids = [c["id"] for c in categories if c["is_over_budget"]]
        near_limit_ids = [c["id"] for c in categories if c["is_near_limit"]]

        return {
            "budget": budget,
            "categories": categories,
            "total_planned": total_planned,
            "total_actual": total_actual,
            "total_remaining": total_remaining,
            "percent_used": percent_used,
            "currency": budget.currency,
            "over_budget_category_ids": over_budget_ids,
            "near_limit_category_ids": near_limit_ids,
        }

    # -----------------------------------------------------------------------
    # Dashboard-facing summary (follow-up: DB-1106A Family Budget Dashboard Widget)
    # -----------------------------------------------------------------------

    async def get_active_family_budgets_summary(self) -> dict:
        """Lightweight aggregate for a future dashboard widget (DB-1106A)."""
        budgets = await self.list_visible_budgets_for_user()
        active = [b for b in budgets if b.status == BudgetStatus.ACTIVE.value]

        total_planned = Decimal("0")
        total_actual = Decimal("0")
        over_budget_count = 0
        near_limit_count = 0

        for budget in active:
            summary = await self.calculate_budget_summary(budget.id)
            total_planned += summary["total_planned"]
            total_actual += summary["total_actual"]
            if summary["over_budget_category_ids"]:
                over_budget_count += 1
            elif summary["near_limit_category_ids"]:
                near_limit_count += 1

        return {
            "active_budgets_count": len(active),
            "total_planned": total_planned,
            "total_actual": total_actual,
            "over_budget_count": over_budget_count,
            "near_limit_count": near_limit_count,
            "currency": active[0].currency if active else "OMR",
        }
