"""Family goal service with visibility and role-based access control."""

from __future__ import annotations

from datetime import date, timedelta
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

        account = None
        if data.account_id is not None:
            result = await self.db.execute(
                select(Account).where(
                    Account.id == data.account_id,
                    Account.tenant_id == self.tenant_id,
                )
            )
            account = result.scalar_one_or_none()
            if account is None:
                raise FamilyGoalServiceError("Account not found")
            access = FamilyAccountAccessService(self.db, self.tenant_id, self.user)
            if not await access.can_view_account(account):
                raise FamilyGoalServiceError("You do not have access to the selected account")

        contribution = GoalContribution(
            tenant_id=self.tenant_id,
            goal_id=goal.id,
            amount=data.amount,
            date=data.date,
            description=data.description,
            contributed_by_user_id=self.user.id,
            account_id=data.account_id,
        )
        self.db.add(contribution)

        goal.current_amount += data.amount
        if goal.current_amount >= goal.target_amount:
            goal.status = GoalStatus.COMPLETED.value

        await self.db.commit()
        await self.db.refresh(contribution)
        return contribution

    async def list_contributions(self, goal_id: int) -> List[GoalContribution]:
        goal = await self.get_goal(goal_id)
        result = await self.db.execute(
            select(GoalContribution)
            .where(GoalContribution.goal_id == goal.id)
            .order_by(GoalContribution.date.desc())
        )
        return list(result.scalars().all())

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
