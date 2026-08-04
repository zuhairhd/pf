"""Family goal service with visibility and role-based access control."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    Family,
    FamilyMember,
    FamilyRole,
    Goal,
    GoalContribution,
    GoalStatus,
    GoalVisibility,
    User,
)
from app.schemas.goal import FamilyGoalCreate, FamilyGoalUpdate, GoalContributionCreate
from app.schemas.accounting import TransferCreate
from app.services.accounting_service import AccountingService
from app.services.family_account_access_service import FamilyAccountAccessService
from app.services.family_service import FamilyService


class FamilyGoalServiceError(Exception):
    """Raised when a family goal operation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FamilyGoalService:
    """CRUD, contributions, and permission checks for family goals."""

    def __init__(self, db: AsyncSession, tenant_id: int, user: User):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self._family_service = FamilyService(db, tenant_id, user)

    # -----------------------------------------------------------------------
    # Role helpers
    # -----------------------------------------------------------------------

    async def _get_family(self) -> Optional[Family]:
        return await self._family_service.get_family()

    async def _get_role(self) -> FamilyRole:
        return await self._family_service.get_role()

    async def _get_member(self) -> Optional[FamilyMember]:
        """Return the current user's active family member record, if any."""
        family = await self._get_family()
        if family is None:
            return None
        result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.family_id == family.id,
                FamilyMember.tenant_id == self.tenant_id,
                FamilyMember.user_id == self.user.id,
                FamilyMember.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    def _is_elevated(self, role: FamilyRole) -> bool:
        return role in (FamilyRole.HEAD, FamilyRole.PARENT)

    # -----------------------------------------------------------------------
    # Permission checks
    # -----------------------------------------------------------------------

    async def can_view_goal(self, goal: Goal) -> bool:
        role = await self._get_role()
        if self._is_elevated(role):
            return True
        if goal.visibility in (GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value):
            return True
        if goal.visibility == GoalVisibility.PRIVATE.value:
            return goal.owner_user_id is not None and goal.owner_user_id == self.user.id
        return False

    async def can_manage_goal(self, goal: Goal) -> bool:
        role = await self._get_role()
        if self._is_elevated(role):
            return True
        if role == FamilyRole.ADULT:
            if goal.visibility in (GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value):
                return True
            if goal.visibility == GoalVisibility.PRIVATE.value:
                return goal.owner_user_id is not None and goal.owner_user_id == self.user.id
        return False

    async def can_contribute_to_goal(self, goal: Goal) -> bool:
        role = await self._get_role()
        if self._is_elevated(role):
            return True
        if role == FamilyRole.ADULT:
            return True
        if goal.visibility in (GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value):
            return role == FamilyRole.TEEN
        if goal.visibility == GoalVisibility.PRIVATE.value and goal.owner_user_id == self.user.id:
            return role in (FamilyRole.TEEN, FamilyRole.CHILD)
        return False

    async def require_view(self, goal: Goal) -> None:
        if not await self.can_view_goal(goal):
            raise FamilyGoalServiceError("You do not have permission to view this goal")

    async def require_manage(self, goal: Goal) -> None:
        if not await self.can_manage_goal(goal):
            raise FamilyGoalServiceError("You do not have permission to manage this goal")

    async def require_contribute(self, goal: Goal) -> None:
        if not await self.can_contribute_to_goal(goal):
            raise FamilyGoalServiceError("You do not have permission to contribute to this goal")

    # -----------------------------------------------------------------------
    # Goal CRUD
    # -----------------------------------------------------------------------

    async def create_family_goal(self, data: FamilyGoalCreate) -> Goal:
        family = await self._get_family()
        if family is None:
            raise FamilyGoalServiceError("No family profile exists for this tenant")

        role = await self._get_role()
        if role == FamilyRole.VIEWER:
            raise FamilyGoalServiceError("Permission denied: viewers cannot create goals")
        if role in (FamilyRole.CHILD,) and data.visibility != GoalVisibility.PRIVATE.value:
            raise FamilyGoalServiceError("Permission denied: child members can only create private goals")

        goal = Goal(
            tenant_id=self.tenant_id,
            family_id=family.id,
            owner_user_id=self.user.id,
            name=data.name,
            goal_type=data.goal_type,
            target_amount=data.target_amount,
            current_amount=Decimal('0'),
            target_date=data.target_date,
            monthly_contribution=data.monthly_contribution,
            description=data.description,
            priority=data.priority,
            visibility=data.visibility,
            status=GoalStatus.ACTIVE.value,
        )
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    async def _get_goal(self, goal_id: int) -> Optional[Goal]:
        result = await self.db.execute(
            select(Goal).where(
                Goal.id == goal_id,
                Goal.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_visible_goals(self) -> List[Goal]:
        family = await self._get_family()
        if family is None:
            return []

        role = await self._get_role()
        query = select(Goal).where(Goal.tenant_id == self.tenant_id, Goal.family_id == family.id)

        if not self._is_elevated(role):
            if role == FamilyRole.ADULT:
                query = query.where(
                    (Goal.visibility.in_((GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value)))
                    | ((Goal.visibility == GoalVisibility.PRIVATE.value) & (Goal.owner_user_id == self.user.id))
                )
            elif role == FamilyRole.TEEN:
                query = query.where(
                    Goal.visibility.in_((GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value))
                )
            elif role == FamilyRole.CHILD:
                query = query.where(
                    (Goal.visibility == GoalVisibility.FAMILY.value)
                    | ((Goal.visibility == GoalVisibility.PRIVATE.value) & (Goal.owner_user_id == self.user.id))
                )
            else:  # VIEWER
                query = query.where(
                    Goal.visibility.in_((GoalVisibility.SHARED.value, GoalVisibility.FAMILY.value))
                )

        result = await self.db.execute(query.order_by(Goal.priority, Goal.created_at))
        return list(result.scalars().all())

    async def get_goal(self, goal_id: int) -> Goal:
        goal = await self._get_goal(goal_id)
        if goal is None:
            raise FamilyGoalServiceError("Goal not found")
        await self.require_view(goal)
        return goal

    async def update_goal(self, goal_id: int, data: FamilyGoalUpdate) -> Goal:
        goal = await self.get_goal(goal_id)
        await self.require_manage(goal)

        update_data = data.model_dump(exclude_unset=True)
        for field in ("name", "target_amount", "target_date", "monthly_contribution", "priority", "description", "status", "visibility"):
            if field in update_data and update_data[field] is not None:
                setattr(goal, field, update_data[field])

        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    async def cancel_goal(self, goal_id: int) -> Goal:
        goal = await self.get_goal(goal_id)
        await self.require_manage(goal)
        goal.status = GoalStatus.CANCELLED.value
        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    async def complete_goal(self, goal_id: int) -> Goal:
        goal = await self.get_goal(goal_id)
        await self.require_manage(goal)
        goal.status = GoalStatus.COMPLETED.value
        await self.db.commit()
        await self.db.refresh(goal)
        return goal

    # -----------------------------------------------------------------------
    # Contributions
    # -----------------------------------------------------------------------

    async def add_contribution(self, goal_id: int, data: GoalContributionCreate) -> GoalContribution:
        goal = await self.get_goal(goal_id)
        await self.require_contribute(goal)

        if data.amount <= 0:
            raise FamilyGoalServiceError("Contribution amount must be positive")

        access = FamilyAccountAccessService(self.db, self.tenant_id, self.user)
        source_account = None
        destination_account = None

        # Legacy account link (progress-only visibility check).
        if data.account_id is not None:
            account = await self._get_account(data.account_id)
            if account is None:
                raise FamilyGoalServiceError("Account not found")
            if not await access.can_view_account(account):
                raise FamilyGoalServiceError("You do not have access to the selected account")

        if data.post_to_accounting:
            if data.source_account_id is None or data.destination_account_id is None:
                raise FamilyGoalServiceError(
                    "Posting to accounting requires both source_account_id and destination_account_id"
                )
            if data.source_account_id == data.destination_account_id:
                raise FamilyGoalServiceError("Source and destination accounts must be different")

            source_account = await self._get_account(data.source_account_id)
            destination_account = await self._get_account(data.destination_account_id)
            if source_account is None:
                raise FamilyGoalServiceError("Source account not found")
            if destination_account is None:
                raise FamilyGoalServiceError("Destination account not found")

            for acc, label in ((source_account, "Source"), (destination_account, "Destination")):
                if acc.account_type != "Asset":
                    raise FamilyGoalServiceError(f"{label} account must be an Asset account for goal contributions")
                if not await access.can_use_account_for_posting(acc):
                    raise FamilyGoalServiceError(f"You do not have permission to use the {label.lower()} account")

        contribution = GoalContribution(
            tenant_id=self.tenant_id,
            goal_id=goal.id,
            amount=data.amount,
            date=data.date,
            description=data.description,
            contributed_by_user_id=self.user.id,
            account_id=data.account_id,
            source_account_id=data.source_account_id,
            destination_account_id=data.destination_account_id,
            posting_status="pending" if data.post_to_accounting else "progress_only",
        )
        self.db.add(contribution)

        goal.current_amount += data.amount
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED.value

        await self.db.commit()
        await self.db.refresh(contribution)

        if data.post_to_accounting and source_account is not None and destination_account is not None:
            contribution = await self._post_contribution_to_accounting(contribution, goal)

        return contribution

    async def _get_account(self, account_id: int) -> Optional[Account]:
        result = await self.db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _post_contribution_to_accounting(self, contribution: GoalContribution, goal: Goal) -> GoalContribution:
        """Create or return the journal entry for a contribution. Idempotent."""
        if contribution.journal_entry_id is not None:
            contribution.posting_status = "posted"
            await self.db.commit()
            await self.db.refresh(contribution)
            return contribution

        accounting = AccountingService(self.db, self.tenant_id)
        reference = f"GOAL-{self.tenant_id}-{goal.id}-{contribution.id}"

        try:
            entry = await accounting.create_transfer(
                TransferCreate(
                    date=contribution.date,
                    from_account_id=contribution.source_account_id,
                    to_account_id=contribution.destination_account_id,
                    amount=contribution.amount,
                    narration=f"Goal contribution: {goal.name}",
                )
            )
            # create_transfer generates its own reference; overwrite with our
            # deterministic tenant-aware reference so idempotency lookups work.
            entry.reference = reference
            contribution.journal_entry_id = entry.id
            contribution.posting_status = "posted"
            await self.db.commit()
            await self.db.refresh(contribution)
        except Exception as exc:
            contribution.posting_status = "failed"
            await self.db.commit()
            await self.db.refresh(contribution)
            raise FamilyGoalServiceError(f"Failed to post contribution to accounting: {exc}")

        return contribution

    async def get_contribution(self, goal_id: int, contribution_id: int) -> GoalContribution:
        goal = await self.get_goal(goal_id)
        result = await self.db.execute(
            select(GoalContribution).where(
                GoalContribution.id == contribution_id,
                GoalContribution.goal_id == goal.id,
                GoalContribution.tenant_id == self.tenant_id,
            )
        )
        contribution = result.scalar_one_or_none()
        if contribution is None:
            raise FamilyGoalServiceError("Contribution not found")
        return contribution

    async def list_contributions(self, goal_id: int) -> List[GoalContribution]:
        goal = await self.get_goal(goal_id)
        result = await self.db.execute(
            select(GoalContribution)
            .where(GoalContribution.goal_id == goal.id)
            .order_by(GoalContribution.date.desc())
        )
        return list(result.scalars().all())

    async def post_contribution_to_accounting(
        self, goal_id: int, contribution_id: int
    ) -> GoalContribution:
        """Post (or re-fetch) the accounting journal entry for an existing contribution."""
        contribution = await self.get_contribution(goal_id, contribution_id)
        goal = await self.get_goal(goal_id)
        await self.require_contribute(goal)
        return await self._post_contribution_to_accounting(contribution, goal)

    async def reverse_contribution(
        self,
        goal_id: int,
        contribution_id: int,
        reason: Optional[str] = None,
        reversal_date: Optional[date] = None,
    ) -> GoalContribution:
        """Reverse a posted goal contribution's journal entry.

        Idempotent: if a reversal already exists, it is returned unchanged and
        no new journal entry is created. Reversing is a stricter action than
        contributing, so it uses require_manage() (HEAD/PARENT always allowed;
        ADULT only for shared/family goals or their own private goal) rather
        than the more permissive require_contribute() used by add_contribution
        -- matching the FAM-1305 allowance-payment-reversal precedent, where
        undoing a posted amount is gated more tightly than creating one.

        Progress-only contributions (no journal_entry_id) cannot be reversed
        here -- there is no posting to undo. The original journal entry and
        its lines are never deleted or mutated; only reversal metadata is
        recorded on the contribution and the reversal entry itself.
        """
        contribution = await self.get_contribution(goal_id, contribution_id)
        goal = await self.get_goal(goal_id)
        await self.require_manage(goal)

        if contribution.journal_entry_id is None:
            raise FamilyGoalServiceError(
                "This contribution was never posted to accounting and cannot be reversed"
            )

        if contribution.reversal_journal_entry_id:
            return contribution

        accounting = AccountingService(self.db, self.tenant_id)
        reversal = await accounting.reverse_journal_entry(
            contribution.journal_entry_id,
            reversal_date=reversal_date,
            reason=reason or f"Goal contribution reversed: {goal.name}",
            created_by=self.user.id,
        )

        contribution.reversal_journal_entry_id = reversal.id
        contribution.posting_status = "reversed"
        contribution.reversed_at = datetime.utcnow()
        contribution.reversed_by_user_id = self.user.id
        contribution.reversal_reason = reason

        # Exclude the reversed amount from active goal progress. current_amount
        # is a running total incremented at contribution time (not re-derived
        # from summing contributions), so it must be decremented explicitly.
        goal.current_amount -= contribution.amount
        if goal.current_amount < 0:
            goal.current_amount = Decimal("0")
        if goal.status == GoalStatus.COMPLETED.value and goal.current_amount < goal.target_amount:
            goal.status = GoalStatus.ACTIVE.value

        await self.db.commit()
        await self.db.refresh(contribution)
        return contribution

    async def get_progress(self, goal_id: int) -> Dict:
        goal = await self.get_goal(goal_id)
        contributions = await self.list_contributions(goal.id)

        target = float(goal.target_amount)
        current = float(goal.current_amount)
        progress = (current / target * 100) if target > 0 else 0
        remaining = target - current

        monthly = float(goal.monthly_contribution)
        if monthly > 0:
            months_to_completion = remaining / monthly
            estimated_completion = date.today() + timedelta(days=int(months_to_completion * 30))
        else:
            months_to_completion = None
            estimated_completion = None

        return {
            "goal": goal,
            "target": target,
            "current": current,
            "remaining": remaining,
            "progress_percentage": round(progress, 1),
            "monthly_contribution": monthly,
            "months_to_completion": months_to_completion,
            "estimated_completion": estimated_completion,
            "contributions": contributions,
            "is_on_track": estimated_completion is None or (goal.target_date and estimated_completion <= goal.target_date),
        }

    # -----------------------------------------------------------------------
    # Dashboard helpers
    # -----------------------------------------------------------------------

    async def get_active_family_goals_summary(self) -> Dict:
        goals = await self.list_visible_goals()
        active = [g for g in goals if g.status == GoalStatus.ACTIVE.value]
        total_target = sum(float(g.target_amount) for g in active)
        total_current = sum(float(g.current_amount) for g in active)
        return {
            "goals": active,
            "total_goals": len(active),
            "total_target": total_target,
            "total_current": total_current,
            "remaining": total_target - total_current,
            "overall_progress": round((total_current / total_target * 100), 1) if total_target > 0 else 0,
        }
