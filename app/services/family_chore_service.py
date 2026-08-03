"""Family chore and allowance tracking service (FAM-1304).

Chores are tenant/family-scoped tasks that can be assigned to a family
member with an allowance amount. Completions are submitted by the
assigned member and approved/rejected by a head or parent.

Role resolution is delegated to FamilyAccountAccessService so permissions
stay consistent with the rest of the family finance module. A tenant does
not need a Family profile to resolve a role (falls back to tenant
OWNER/ADMIN -> HEAD, else VIEWER), matching FamilyBudgetService.

Permission summary (see docs/audits/FAM-1304_ALLOWANCE_CHORES_IMPLEMENTATION_REPORT.md
for the full matrix):
  - HEAD/PARENT: create/manage/approve everything; view all chores and the
    full allowance summary.
  - ADULT: view all family chores (broad visibility, like shared/family
    budgets) and their own allowance summary; cannot create, manage, or
    approve chores (no elevated-permission flag exists yet for chores).
  - TEEN/CHILD: view and submit completions only for chores assigned to
    themselves; cannot create/manage/approve; own allowance summary only.
  - VIEWER: read-only view of all family chores; cannot submit or approve.

This service never creates transactions, journal entries, or modifies
account balances. Posting earned allowance through the accounting engine
is deferred to FAM-1305.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Family, FamilyChore, FamilyChoreCompletion, FamilyMember, User
from app.models.family import FamilyRole
from app.models.family_chore import ChoreCompletionStatus, ChoreStatus
from app.schemas.family_chore import ChoreCompletionCreate, ChoreCreate, ChoreUpdate
from app.services.family_account_access_service import FamilyAccountAccessService


class FamilyChoreServiceError(Exception):
    """Raised when a family chore operation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FamilyChoreService:
    """CRUD, permission checks, and allowance summary calculations for chores."""

    def __init__(self, db: AsyncSession, tenant_id: int, user: User):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self.access = FamilyAccountAccessService(db, tenant_id, user)

    # -----------------------------------------------------------------------
    # Role/family/member helpers
    # -----------------------------------------------------------------------

    async def get_role(self) -> FamilyRole:
        return await self.access.get_role()

    def _is_elevated(self, role: FamilyRole) -> bool:
        return role in (FamilyRole.HEAD, FamilyRole.PARENT)

    async def _get_family(self) -> Optional[Family]:
        result = await self.db.execute(
            select(Family).where(Family.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    async def _get_own_member(self) -> Optional[FamilyMember]:
        """Return the current user's own active FamilyMember record, if any."""
        result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.tenant_id == self.tenant_id,
                FamilyMember.user_id == self.user.id,
                FamilyMember.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def _get_member(self, member_id: int) -> Optional[FamilyMember]:
        result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # -----------------------------------------------------------------------
    # Permission checks
    # -----------------------------------------------------------------------

    async def can_user_view_chore(self, chore: FamilyChore) -> bool:
        """Whether the current user may view this chore."""
        role = await self.get_role()
        if self._is_elevated(role) or role in (FamilyRole.ADULT, FamilyRole.VIEWER):
            return True
        if role in (FamilyRole.TEEN, FamilyRole.CHILD):
            own_member = await self._get_own_member()
            return (
                own_member is not None
                and chore.assigned_to_member_id is not None
                and chore.assigned_to_member_id == own_member.id
            )
        return False

    async def can_user_manage_chore(self, chore: Optional[FamilyChore] = None) -> bool:
        """Whether the current user may create, update, or archive chores.

        HEAD/PARENT only. ADULT does not currently have an elevated
        permission flag for chore management, matching the FAM-1304 spec
        ("adult: create chores only if current family permissions allow;
        otherwise no" — no such flag exists yet, so the default is no).
        """
        role = await self.get_role()
        return self._is_elevated(role)

    async def can_user_submit_completion(self, chore: FamilyChore) -> bool:
        """Whether the current user may submit a completion for this chore."""
        role = await self.get_role()
        if role == FamilyRole.VIEWER:
            return False
        own_member = await self._get_own_member()
        if own_member is None:
            # Tenant owner/admin acting as HEAD without a FamilyMember record
            # can still submit on behalf of the family if self-assigned;
            # otherwise there is no member identity to attribute the
            # completion to.
            return False
        return (
            chore.assigned_to_member_id is not None
            and chore.assigned_to_member_id == own_member.id
        )

    async def can_user_approve_completion(self) -> bool:
        """Whether the current user may approve/reject chore completions.

        HEAD/PARENT only, matching "approve only if elevated permission
        exists; otherwise no" for every other role.
        """
        role = await self.get_role()
        return self._is_elevated(role)

    async def require_view(self, chore: FamilyChore) -> None:
        if not await self.can_user_view_chore(chore):
            raise FamilyChoreServiceError("You do not have permission to view this chore")

    async def require_manage(self) -> None:
        if not await self.can_user_manage_chore():
            raise FamilyChoreServiceError("You do not have permission to manage chores")

    async def require_approve(self) -> None:
        if not await self.can_user_approve_completion():
            raise FamilyChoreServiceError("You do not have permission to approve chore completions")

    # -----------------------------------------------------------------------
    # Chore CRUD
    # -----------------------------------------------------------------------

    async def create_chore(self, data: ChoreCreate) -> FamilyChore:
        await self.require_manage()

        family = await self._get_family()
        if family is None:
            raise FamilyChoreServiceError("No family profile exists for this tenant")

        if data.assigned_to_member_id is not None:
            member = await self._get_member(data.assigned_to_member_id)
            if member is None or member.family_id != family.id:
                raise FamilyChoreServiceError("Assigned member not found in this family")

        chore = FamilyChore(
            tenant_id=self.tenant_id,
            family_id=family.id,
            title=data.title,
            description=data.description,
            assigned_to_member_id=data.assigned_to_member_id,
            created_by_user_id=self.user.id,
            allowance_amount=data.allowance_amount,
            currency=data.currency,
            frequency=data.frequency,
            due_date=data.due_date,
            status=ChoreStatus.ACTIVE.value,
            requires_approval=data.requires_approval,
        )
        self.db.add(chore)
        await self.db.commit()
        await self.db.refresh(chore)
        return chore

    async def _get_chore_raw(self, chore_id: int) -> Optional[FamilyChore]:
        result = await self.db.execute(
            select(FamilyChore).where(
                FamilyChore.id == chore_id,
                FamilyChore.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_chore(self, chore_id: int) -> FamilyChore:
        chore = await self._get_chore_raw(chore_id)
        if chore is None:
            raise FamilyChoreServiceError("Chore not found")
        await self.require_view(chore)
        return chore

    async def list_visible_chores_for_user(self) -> list[FamilyChore]:
        """Return chores in the tenant the current user is allowed to see."""
        role = await self.get_role()
        query = select(FamilyChore).where(FamilyChore.tenant_id == self.tenant_id)

        if role in (FamilyRole.TEEN, FamilyRole.CHILD):
            own_member = await self._get_own_member()
            if own_member is None:
                return []
            query = query.where(FamilyChore.assigned_to_member_id == own_member.id)
        # HEAD/PARENT/ADULT/VIEWER see all chores in the tenant family.

        result = await self.db.execute(
            query.order_by(FamilyChore.due_date.is_(None), FamilyChore.due_date, FamilyChore.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_chore(self, chore_id: int, data: ChoreUpdate) -> FamilyChore:
        chore = await self.get_chore(chore_id)
        await self.require_manage()

        update_data = data.model_dump(exclude_unset=True)
        if "assigned_to_member_id" in update_data and update_data["assigned_to_member_id"] is not None:
            member = await self._get_member(update_data["assigned_to_member_id"])
            if member is None or member.family_id != chore.family_id:
                raise FamilyChoreServiceError("Assigned member not found in this family")

        for field in (
            "title", "description", "assigned_to_member_id", "allowance_amount",
            "frequency", "due_date", "status", "requires_approval",
        ):
            if field in update_data:
                setattr(chore, field, update_data[field])

        await self.db.commit()
        await self.db.refresh(chore)
        return chore

    async def archive_chore(self, chore_id: int) -> FamilyChore:
        chore = await self.get_chore(chore_id)
        await self.require_manage()
        chore.status = ChoreStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(chore)
        return chore

    # -----------------------------------------------------------------------
    # Completions
    # -----------------------------------------------------------------------

    async def submit_completion(self, chore_id: int, data: ChoreCompletionCreate) -> FamilyChoreCompletion:
        chore = await self.get_chore(chore_id)
        if not await self.can_user_submit_completion(chore):
            raise FamilyChoreServiceError("You do not have permission to submit a completion for this chore")

        own_member = await self._get_own_member()
        completion = FamilyChoreCompletion(
            tenant_id=self.tenant_id,
            chore_id=chore.id,
            family_id=chore.family_id,
            completed_by_member_id=own_member.id,
            completed_at=data.completed_at or datetime.utcnow(),
            submitted_notes=data.submitted_notes,
            status=ChoreCompletionStatus.SUBMITTED.value,
            earned_amount=Decimal("0"),
        )
        self.db.add(completion)
        await self.db.commit()
        await self.db.refresh(completion)
        return completion

    async def _get_completion_raw(self, completion_id: int) -> Optional[FamilyChoreCompletion]:
        result = await self.db.execute(
            select(FamilyChoreCompletion).where(
                FamilyChoreCompletion.id == completion_id,
                FamilyChoreCompletion.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_completion(self, completion_id: int) -> FamilyChoreCompletion:
        completion = await self._get_completion_raw(completion_id)
        if completion is None:
            raise FamilyChoreServiceError("Chore completion not found")
        chore = await self._get_chore_raw(completion.chore_id)
        if chore is not None:
            await self.require_view(chore)
        return completion

    async def list_completions(self, chore_id: int) -> list[FamilyChoreCompletion]:
        chore = await self.get_chore(chore_id)
        result = await self.db.execute(
            select(FamilyChoreCompletion)
            .where(FamilyChoreCompletion.chore_id == chore.id)
            .where(FamilyChoreCompletion.tenant_id == self.tenant_id)
            .order_by(FamilyChoreCompletion.completed_at.desc())
        )
        return list(result.scalars().all())

    async def approve_completion(
        self, completion_id: int, earned_amount: Optional[Decimal] = None
    ) -> FamilyChoreCompletion:
        completion = await self._get_completion_raw(completion_id)
        if completion is None:
            raise FamilyChoreServiceError("Chore completion not found")
        await self.require_approve()

        chore = await self._get_chore_raw(completion.chore_id)
        completion.status = ChoreCompletionStatus.APPROVED.value
        completion.approved_by_user_id = self.user.id
        completion.approved_at = datetime.utcnow()
        completion.rejection_reason = None
        completion.earned_amount = (
            earned_amount if earned_amount is not None
            else (chore.allowance_amount if chore is not None else Decimal("0"))
        )
        await self.db.commit()
        await self.db.refresh(completion)
        return completion

    async def reject_completion(self, completion_id: int, rejection_reason: str) -> FamilyChoreCompletion:
        completion = await self._get_completion_raw(completion_id)
        if completion is None:
            raise FamilyChoreServiceError("Chore completion not found")
        await self.require_approve()

        if not rejection_reason or not rejection_reason.strip():
            raise FamilyChoreServiceError("A rejection reason is required")

        completion.status = ChoreCompletionStatus.REJECTED.value
        completion.approved_by_user_id = self.user.id
        completion.approved_at = datetime.utcnow()
        completion.rejection_reason = rejection_reason.strip()
        completion.earned_amount = Decimal("0")
        await self.db.commit()
        await self.db.refresh(completion)
        return completion

    # -----------------------------------------------------------------------
    # Allowance summary (read-only; no accounting posting — see FAM-1305)
    # -----------------------------------------------------------------------

    async def get_allowance_summary(self) -> dict:
        """Return a read-only allowance summary scoped to what the user may see.

        HEAD/PARENT: summary across all family members.
        Everyone else: summary limited to their own completions only.
        """
        role = await self.get_role()
        family = await self._get_family()
        if family is None:
            return {
                "currency": self.user.currency or "OMR",
                "pending_approval_amount": Decimal("0"),
                "approved_earned_amount": Decimal("0"),
                "rejected_amount": Decimal("0"),
                "by_member": [],
            }

        query = (
            select(FamilyChoreCompletion)
            .where(FamilyChoreCompletion.tenant_id == self.tenant_id)
            .where(FamilyChoreCompletion.family_id == family.id)
        )

        if not self._is_elevated(role):
            own_member = await self._get_own_member()
            if own_member is None:
                return {
                    "currency": family.currency,
                    "pending_approval_amount": Decimal("0"),
                    "approved_earned_amount": Decimal("0"),
                    "rejected_amount": Decimal("0"),
                    "by_member": [],
                }
            query = query.where(FamilyChoreCompletion.completed_by_member_id == own_member.id)

        result = await self.db.execute(query)
        completions = list(result.scalars().all())

        pending_total = Decimal("0")
        approved_total = Decimal("0")
        rejected_total = Decimal("0")
        by_member_map: dict[int, dict] = {}

        # Preload chores to get allowance_amount for pending completions.
        chore_ids = {c.chore_id for c in completions}
        chores_by_id: dict[int, FamilyChore] = {}
        if chore_ids:
            chore_result = await self.db.execute(
                select(FamilyChore).where(FamilyChore.id.in_(chore_ids))
            )
            chores_by_id = {c.id: c for c in chore_result.scalars().all()}

        member_ids = {c.completed_by_member_id for c in completions}
        members_by_id: dict[int, FamilyMember] = {}
        if member_ids:
            member_result = await self.db.execute(
                select(FamilyMember).where(FamilyMember.id.in_(member_ids))
            )
            members_by_id = {m.id: m for m in member_result.scalars().all()}

        for completion in completions:
            member = members_by_id.get(completion.completed_by_member_id)
            member_key = completion.completed_by_member_id
            if member_key not in by_member_map:
                by_member_map[member_key] = {
                    "member_id": member_key,
                    "member_name": (
                        f"{member.first_name} {member.last_name}".strip()
                        if member else "Unknown"
                    ),
                    "pending_approval_amount": Decimal("0"),
                    "approved_earned_amount": Decimal("0"),
                    "rejected_amount": Decimal("0"),
                }

            if completion.status == ChoreCompletionStatus.SUBMITTED.value:
                chore = chores_by_id.get(completion.chore_id)
                amount = chore.allowance_amount if chore is not None else Decimal("0")
                pending_total += amount
                by_member_map[member_key]["pending_approval_amount"] += amount
            elif completion.status == ChoreCompletionStatus.APPROVED.value:
                approved_total += completion.earned_amount
                by_member_map[member_key]["approved_earned_amount"] += completion.earned_amount
            elif completion.status == ChoreCompletionStatus.REJECTED.value:
                chore = chores_by_id.get(completion.chore_id)
                amount = chore.allowance_amount if chore is not None else Decimal("0")
                rejected_total += amount
                by_member_map[member_key]["rejected_amount"] += amount

        return {
            "currency": family.currency,
            "pending_approval_amount": pending_total,
            "approved_earned_amount": approved_total,
            "rejected_amount": rejected_total,
            "by_member": list(by_member_map.values()),
        }

    # -----------------------------------------------------------------------
    # Dashboard-facing summary (follow-up: DB-1107A Allowance/Chore Dashboard Widget)
    # -----------------------------------------------------------------------

    async def get_family_chore_summary(self) -> dict:
        """Lightweight aggregate for a future dashboard widget (DB-1107A)."""
        chores = await self.list_visible_chores_for_user()
        today = date.today()

        due_soon = [
            c for c in chores
            if c.status == ChoreStatus.ACTIVE.value
            and c.due_date is not None
            and today <= c.due_date <= date.fromordinal(today.toordinal() + 7)
        ]
        overdue = [
            c for c in chores
            if c.status == ChoreStatus.ACTIVE.value
            and c.due_date is not None
            and c.due_date < today
        ]

        pending_approvals = 0
        if await self.can_user_approve_completion():
            chore_ids = [c.id for c in chores]
            if chore_ids:
                result = await self.db.execute(
                    select(FamilyChoreCompletion)
                    .where(FamilyChoreCompletion.tenant_id == self.tenant_id)
                    .where(FamilyChoreCompletion.chore_id.in_(chore_ids))
                    .where(FamilyChoreCompletion.status == ChoreCompletionStatus.SUBMITTED.value)
                )
                pending_approvals = len(list(result.scalars().all()))

        allowance_summary = await self.get_allowance_summary()

        return {
            "due_soon_count": len(due_soon),
            "overdue_count": len(overdue),
            "pending_approvals_count": pending_approvals,
            "approved_allowance_amount": allowance_summary["approved_earned_amount"],
            "currency": allowance_summary["currency"],
        }
