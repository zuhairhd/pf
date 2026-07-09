"""Family account visibility and access control service."""

from __future__ import annotations

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, FamilyMember, User, UserRole
from app.models.accounting import AccountVisibility
from app.models.family import FamilyRole


_UNSET = object()


class FamilyAccountAccessService:
    """Enforces shared/private/family account visibility rules inside a tenant."""

    def __init__(self, db: AsyncSession, tenant_id: int, user: User):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user
        self._family_member: FamilyMember | None = _UNSET  # type: ignore[assignment]
        self._role: FamilyRole | None = None

    async def _get_family_member(self) -> FamilyMember | None:
        if self._family_member is _UNSET:
            result = await self.db.execute(
                select(FamilyMember).where(
                    FamilyMember.tenant_id == self.tenant_id,
                    FamilyMember.user_id == self.user.id,
                    FamilyMember.is_active.is_(True),
                )
            )
            self._family_member = result.scalar_one_or_none()
        return self._family_member

    async def get_role(self) -> FamilyRole:
        """Return the user's family role, treating tenant admins as heads."""
        if self._role is None:
            member = await self._get_family_member()
            if member is not None and member.role in {r.value for r in FamilyRole}:
                self._role = FamilyRole(member.role)
            elif (
                self.user.role in (UserRole.OWNER, UserRole.ADMIN)
                or self.user.is_superuser
            ):
                self._role = FamilyRole.HEAD
            else:
                self._role = FamilyRole.VIEWER
        return self._role

    def _is_elevated(self, role: FamilyRole) -> bool:
        """Heads, parents, and tenant admins have full account access."""
        return role in (FamilyRole.HEAD, FamilyRole.PARENT)

    async def can_view_account(self, account: Account) -> bool:
        """Whether the user may view this account's details/balance."""
        role = await self.get_role()
        if self._is_elevated(role):
            return True

        if account.visibility in (
            AccountVisibility.SHARED.value,
            AccountVisibility.FAMILY.value,
        ):
            return True

        if account.visibility == AccountVisibility.PRIVATE.value:
            return account.owner_user_id is not None and account.owner_user_id == self.user.id

        return False

    async def can_manage_account(self, account: Account) -> bool:
        """Whether the user may update, share, or change ownership of this account."""
        role = await self.get_role()
        if self._is_elevated(role):
            return True

        if account.visibility in (
            AccountVisibility.SHARED.value,
            AccountVisibility.FAMILY.value,
        ):
            return role == FamilyRole.ADULT

        if account.visibility == AccountVisibility.PRIVATE.value:
            return (
                role == FamilyRole.ADULT
                and account.owner_user_id is not None
                and account.owner_user_id == self.user.id
            )

        return False

    async def can_use_account_for_posting(self, account: Account) -> bool:
        """Whether the user may post transactions/payments against this account."""
        # Same as management for now; teen/child own accounts could be relaxed later.
        return await self.can_manage_account(account)

    async def require_view(self, account: Account) -> None:
        if not await self.can_view_account(account):
            raise PermissionError("You do not have permission to view this account")

    async def require_manage(self, account: Account) -> None:
        if not await self.can_manage_account(account):
            raise PermissionError("You do not have permission to manage this account")

    async def list_visible_accounts(self) -> list[Account]:
        """Return accounts the user is allowed to see within the tenant."""
        role = await self.get_role()
        if self._is_elevated(role):
            query = select(Account).where(Account.tenant_id == self.tenant_id)
        else:
            query = select(Account).where(Account.tenant_id == self.tenant_id).where(
                or_(
                    Account.visibility.in_(
                        [AccountVisibility.SHARED.value, AccountVisibility.FAMILY.value]
                    ),
                    and_(
                        Account.visibility == AccountVisibility.PRIVATE.value,
                        Account.owner_user_id == self.user.id,
                    ),
                )
            )
        result = await self.db.execute(query.order_by(Account.code))
        return list(result.scalars().all())
