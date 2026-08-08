"""Family finance service layer."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Family, FamilyInvitation, FamilyInvitationStatus, FamilyMember, FamilyRole, User
from app.notifications.channels.email import send_email
from app.utils.security import generate_secure_token


# How long a family invitation remains acceptable before it expires.
INVITATION_EXPIRY_DAYS = 7


class FamilyServiceError(Exception):
    """Raised when a family operation fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class FamilyService:
    """CRUD and permission helpers for family finance."""

    def __init__(self, db: AsyncSession, tenant_id: int, user: User):
        self.db = db
        self.tenant_id = tenant_id
        self.user = user

    async def get_family(self) -> Optional[Family]:
        """Return the family profile for the current tenant, if any."""
        result = await self.db.execute(
            select(Family).where(Family.tenant_id == self.tenant_id)
        )
        return result.scalar_one_or_none()

    async def create_family(self, data: dict) -> Family:
        """Create a new family profile for the current tenant."""
        existing = await self.get_family()
        if existing is not None:
            raise FamilyServiceError("A family profile already exists for this tenant")

        family = Family(
            tenant_id=self.tenant_id,
            name=data["name"],
            currency=data.get("currency", "OMR"),
        )
        self.db.add(family)
        await self.db.flush()
        await self.db.refresh(family)

        # The creator becomes the family head.
        await self._add_self_as_head(family)
        return family

    async def _add_self_as_head(self, family: Family) -> FamilyMember:
        """Add the current user as the head of the family."""
        member = FamilyMember(
            family_id=family.id,
            tenant_id=self.tenant_id,
            user_id=self.user.id,
            email=self.user.email,
            first_name=self.user.first_name,
            last_name=self.user.last_name,
            relationship_type="self",
            role=FamilyRole.HEAD.value,
            is_active=True,
            invitation_accepted_at=datetime.utcnow(),
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(family)
        return member

    async def update_family(self, family: Family, data: dict) -> Family:
        """Update the family profile."""
        if "name" in data and data["name"] is not None:
            family.name = data["name"]
        if "currency" in data and data["currency"] is not None:
            family.currency = data["currency"]
        await self.db.commit()
        await self.db.refresh(family)
        return family

    async def get_or_create_family(self) -> Family:
        """Return the tenant family, creating a default one if absent."""
        family = await self.get_family()
        if family is not None:
            return family
        return await self.create_family({"name": "My Family", "currency": self.user.currency or "OMR"})

    # -----------------------------------------------------------------------
    # Members
    # -----------------------------------------------------------------------

    async def list_members(self) -> list[FamilyMember]:
        """Return all members of the tenant family."""
        family = await self.get_family()
        if family is None:
            return []
        result = await self.db.execute(
            select(FamilyMember)
            .where(FamilyMember.family_id == family.id)
            .where(FamilyMember.tenant_id == self.tenant_id)
            .order_by(FamilyMember.created_at)
        )
        return list(result.scalars().all())

    async def get_member(self, member_id: int) -> Optional[FamilyMember]:
        """Return a single family member by ID."""
        family = await self.get_family()
        if family is None:
            return None
        result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.family_id == family.id,
                FamilyMember.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_member(self, data: dict) -> FamilyMember:
        """Add a member to the tenant family."""
        family = await self.get_or_create_family()
        role = data.get("role", FamilyRole.VIEWER.value)
        if role not in {r.value for r in FamilyRole}:
            raise FamilyServiceError(f"Invalid family role: {role}")

        member = FamilyMember(
            family_id=family.id,
            tenant_id=self.tenant_id,
            user_id=data.get("user_id"),
            email=data["email"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            relationship_type=data["relationship_type"],
            role=role,
            is_active=data.get("is_active", False),
        )
        self.db.add(member)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def update_member(self, member: FamilyMember, data: dict) -> FamilyMember:
        """Update a family member."""
        for field in ("first_name", "last_name", "relationship_type", "role", "is_active"):
            if field in data and data[field] is not None:
                value = data[field]
                if field == "role" and value not in {r.value for r in FamilyRole}:
                    raise FamilyServiceError(f"Invalid family role: {value}")
                setattr(member, field, value)
        await self.db.commit()
        await self.db.refresh(member)
        return member

    async def delete_member(self, member: FamilyMember) -> None:
        """Remove a family member."""
        await self.db.delete(member)
        await self.db.commit()

    # -----------------------------------------------------------------------
    # Invitations (AUTH-305)
    # -----------------------------------------------------------------------

    def _mark_expired_if_needed(self, invitation: FamilyInvitation) -> bool:
        """Flip a stale pending invitation to expired. Returns True if changed."""
        if (
            invitation.status == FamilyInvitationStatus.PENDING.value
            and invitation.expires_at < datetime.utcnow()
        ):
            invitation.status = FamilyInvitationStatus.EXPIRED.value
            return True
        return False

    async def list_invitations(self) -> list[FamilyInvitation]:
        """Return all invitations for the tenant family, newest first."""
        family = await self.get_family()
        if family is None:
            return []
        result = await self.db.execute(
            select(FamilyInvitation)
            .where(FamilyInvitation.tenant_id == self.tenant_id)
            .where(FamilyInvitation.family_id == family.id)
            .order_by(FamilyInvitation.created_at.desc())
        )
        invitations = list(result.scalars().all())
        changed = [self._mark_expired_if_needed(inv) for inv in invitations]
        if any(changed):
            await self.db.commit()
            for inv in invitations:
                await self.db.refresh(inv)
        return invitations

    async def get_invitation(self, invitation_id: int) -> Optional[FamilyInvitation]:
        """Return a single invitation by ID, scoped to the current tenant."""
        result = await self.db.execute(
            select(FamilyInvitation).where(
                FamilyInvitation.id == invitation_id,
                FamilyInvitation.tenant_id == self.tenant_id,
            )
        )
        invitation = result.scalar_one_or_none()
        if invitation is not None and self._mark_expired_if_needed(invitation):
            await self.db.commit()
            await self.db.refresh(invitation)
        return invitation

    async def create_invitation(self, data: dict) -> FamilyInvitation:
        """Create (or safely reuse) a pending invitation for an email.

        Idempotent: calling this again for an email with an existing pending,
        non-expired invitation returns that same invitation instead of
        creating a duplicate.
        """
        await self.require_permission("can_manage_members")

        role = data.get("role", FamilyRole.VIEWER.value)
        if hasattr(role, "value"):
            role = role.value
        if role not in {r.value for r in FamilyRole}:
            raise FamilyServiceError(f"Invalid family role: {role}")

        email = data["email"].strip().lower()
        family = await self.get_or_create_family()

        # This app is single-tenant-per-user: an email that already has an
        # account cannot be auto-invited into a different tenant, since that
        # would either sever their existing tenant access or require
        # cross-tenant account linking, neither of which is safe here.
        existing_user = await self.db.execute(select(User).where(User.email == email))
        if existing_user.scalar_one_or_none() is not None:
            raise FamilyServiceError(
                "This email is already registered with an existing account and cannot be auto-invited"
            )

        existing_member = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.tenant_id == self.tenant_id,
                FamilyMember.family_id == family.id,
                FamilyMember.email == email,
                FamilyMember.is_active.is_(True),
            )
        )
        if existing_member.scalar_one_or_none() is not None:
            raise FamilyServiceError("This email is already an active family member")

        result = await self.db.execute(
            select(FamilyInvitation).where(
                FamilyInvitation.tenant_id == self.tenant_id,
                FamilyInvitation.family_id == family.id,
                FamilyInvitation.email == email,
                FamilyInvitation.status == FamilyInvitationStatus.PENDING.value,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            expired_now = self._mark_expired_if_needed(existing)
            await self.db.commit()
            if not expired_now:
                await self.db.refresh(existing)
                return existing

        invitation = FamilyInvitation(
            tenant_id=self.tenant_id,
            family_id=family.id,
            email=email,
            first_name=data["first_name"],
            last_name=data["last_name"],
            relationship_type=data["relationship_type"],
            role=role,
            token=generate_secure_token(32),
            status=FamilyInvitationStatus.PENDING.value,
            expires_at=datetime.utcnow() + timedelta(days=INVITATION_EXPIRY_DAYS),
            invited_by_user_id=self.user.id,
        )
        self.db.add(invitation)
        await self.db.commit()
        await self.db.refresh(invitation)

        await self._send_invitation_email(invitation)
        return invitation

    async def cancel_invitation(self, invitation_id: int) -> FamilyInvitation:
        """Cancel a pending invitation. Cannot cancel an already-resolved one."""
        await self.require_permission("can_manage_members")

        invitation = await self.get_invitation(invitation_id)
        if invitation is None:
            raise FamilyServiceError("Invitation not found")
        if invitation.status != FamilyInvitationStatus.PENDING.value:
            raise FamilyServiceError(
                f"Cannot cancel an invitation that is already {invitation.status}"
            )

        invitation.status = FamilyInvitationStatus.CANCELLED.value
        invitation.cancelled_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation

    async def _send_invitation_email(self, invitation: FamilyInvitation) -> None:
        """Best-effort invitation email; delivery failure never raises.

        Uses the project's existing pluggable email backend (console-logged
        in dev/test by default, never sent externally unless EMAIL_BACKEND
        is explicitly configured for SMTP).
        """
        accept_url = f"/family/members/invitations/accept?token={invitation.token}"
        await send_email(
            to_email=invitation.email,
            subject="You're invited to join a family on PF AI",
            body_text=(
                f"Hi {invitation.first_name},\n\n"
                "You have been invited to join a family on PF AI Personal Finance.\n"
                f"Accept your invitation here: {accept_url}\n\n"
                f"This invitation expires on {invitation.expires_at.isoformat()}."
            ),
        )

    # -----------------------------------------------------------------------
    # Permissions
    # -----------------------------------------------------------------------

    async def _get_current_member(self) -> Optional[FamilyMember]:
        """Return the current user's active family member record, if any."""
        family = await self.get_family()
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

    async def get_role(self) -> FamilyRole:
        """Return the current user's family role."""
        member = await self._get_current_member()
        if member is not None:
            return FamilyRole(member.role)
        # Tenant owners/admins are treated as heads even without a member record.
        if self.user.role.value in ("owner", "admin") or self.user.is_superuser:
            return FamilyRole.HEAD
        return FamilyRole.VIEWER

    async def get_permissions(self) -> dict:
        """Return permission flags and role for the current user."""
        role = await self.get_role()
        return {"role": role.value, **_permissions_for_role(role)}

    async def require_permission(self, permission: str) -> None:
        """Raise if the current user lacks the requested permission."""
        perms = await self.get_permissions()
        if not perms.get(permission, False):
            raise FamilyServiceError(f"Permission denied: {permission}")


def _permissions_for_role(role: FamilyRole) -> dict:
    """Permission matrix for family roles."""
    base = {
        "can_view_family": False,
        "can_edit_family": False,
        "can_manage_members": False,
        "can_view_accounts": False,
        "can_edit_transactions": False,
        "can_view_reports": False,
        "can_approve_purchases": False,
    }

    if role == FamilyRole.HEAD:
        return {k: True for k in base}
    if role == FamilyRole.PARENT:
        return {**base, "can_view_family": True, "can_edit_family": True,
                "can_manage_members": True, "can_view_accounts": True,
                "can_edit_transactions": True, "can_view_reports": True,
                "can_approve_purchases": True}
    if role == FamilyRole.ADULT:
        return {**base, "can_view_family": True, "can_view_accounts": True,
                "can_edit_transactions": True, "can_view_reports": True}
    if role == FamilyRole.TEEN:
        return {**base, "can_view_family": True, "can_view_accounts": True}
    if role == FamilyRole.CHILD:
        return {**base, "can_view_family": True}
    # VIEWER
    return {**base, "can_view_family": True}
