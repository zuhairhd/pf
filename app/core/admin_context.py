"""Safe super-admin tenant context management.

This module implements the preferred safe approach for support staff to access
tenant data: the admin selects one tenant at a time, provides a reason, and the
normal RLS policies remain active. There is no universal bypass, no GUC flag,
and no special role for the application database user.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Organization, AdminAccessSession, AdminAccessStatus
from app.core.rls import set_tenant_context_async, clear_tenant_context_async


DEFAULT_SUPPORT_ACCESS_MINUTES = 30


class AdminAccessError(Exception):
    """Raised when admin support access cannot be granted or is invalid."""
    pass


def require_super_admin(user: Optional[User]) -> None:
    """Raise HTTPException if the user is not a super admin."""
    if user is None or not getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )


def _sanitize_reason(reason: Optional[str]) -> str:
    """Validate and strip an access reason."""
    if not reason or not reason.strip():
        raise AdminAccessError("Access reason is required")
    reason = reason.strip()
    if len(reason) > 2000:
        raise AdminAccessError("Reason must be 2000 characters or less")
    return reason


async def start_admin_tenant_context(
    db: AsyncSession,
    admin_user: User,
    target_organization_id: int,
    reason: str,
    expires_minutes: int = DEFAULT_SUPPORT_ACCESS_MINUTES,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AdminAccessSession:
    """Start an audited support session for exactly one tenant.

    The session is recorded in the global `admin_access_sessions` table and the
    database connection is placed into that tenant's RLS context. Normal RLS
    policies continue to apply.

    Raises:
        AdminAccessError: if the request is invalid (not super admin, missing
            reason, unknown tenant, etc.).
    """
    if not getattr(admin_user, "is_superuser", False):
        raise AdminAccessError("Super admin access required")

    reason = _sanitize_reason(reason)

    if target_organization_id <= 0:
        raise AdminAccessError("Valid target organization is required")

    # Verify the target organization exists.
    org_result = await db.execute(
        select(Organization).where(Organization.id == target_organization_id)
    )
    if org_result.scalar_one_or_none() is None:
        raise AdminAccessError("Target organization not found")

    # Enforce a single active session per admin (defense in depth).
    active_result = await db.execute(
        select(AdminAccessSession).where(
            AdminAccessSession.admin_user_id == admin_user.id,
            AdminAccessSession.status == AdminAccessStatus.ACTIVE.value,
            AdminAccessSession.access_expires_at > datetime.utcnow(),
        )
    )
    if active_result.scalar_one_or_none() is not None:
        raise AdminAccessError("An active support session already exists; end it first")

    now = datetime.utcnow()
    session = AdminAccessSession(
        admin_user_id=admin_user.id,
        target_organization_id=target_organization_id,
        reason=reason,
        access_started_at=now,
        access_expires_at=now + timedelta(minutes=expires_minutes),
        ip_address=(ip_address[:45] if ip_address else None),
        user_agent=(user_agent[:500] if user_agent else None),
        status=AdminAccessStatus.ACTIVE.value,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # Set RLS tenant context for the selected organization.
    await set_tenant_context_async(db, target_organization_id)

    return session


async def get_active_admin_access(
    db: AsyncSession,
    admin_user_id: int,
) -> Optional[AdminAccessSession]:
    """Return the active, non-expired support session for an admin, if any."""
    result = await db.execute(
        select(AdminAccessSession).where(
            AdminAccessSession.admin_user_id == admin_user_id,
            AdminAccessSession.status == AdminAccessStatus.ACTIVE.value,
            AdminAccessSession.access_expires_at > datetime.utcnow(),
        )
    )
    return result.scalar_one_or_none()


async def set_admin_tenant_context_from_session(
    db: AsyncSession,
    access_session: AdminAccessSession,
) -> None:
    """Re-apply the tenant context for an existing support session.

    Raises:
        AdminAccessError: if the session has expired or is not active.
    """
    if access_session.status != AdminAccessStatus.ACTIVE.value:
        raise AdminAccessError("Support session is not active")
    if access_session.access_expires_at <= datetime.utcnow():
        raise AdminAccessError("Support session has expired")

    await set_tenant_context_async(db, access_session.target_organization_id)


async def end_admin_tenant_context(
    db: AsyncSession,
    access_session_id: int,
    admin_user_id: int,
) -> AdminAccessSession:
    """End (revoke) a support session and clear its RLS context.

    Only the admin who started the session or another super admin can end it.
    """
    result = await db.execute(
        select(AdminAccessSession).where(AdminAccessSession.id == access_session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise AdminAccessError("Support session not found")

    if session.admin_user_id != admin_user_id:
        # In a real system you might allow another super admin to revoke.
        # For safety, restrict to the originating admin in this implementation.
        raise AdminAccessError("You can only end your own support session")

    session.status = AdminAccessStatus.REVOKED.value
    session.access_ended_at = datetime.utcnow()
    await db.flush()
    await db.refresh(session)

    await clear_tenant_context_async(db)
    return session


async def expire_stale_admin_sessions(db: AsyncSession) -> int:
    """Mark all expired ACTIVE sessions as EXPIRED. Returns count changed."""
    result = await db.execute(
        select(AdminAccessSession).where(
            AdminAccessSession.status == AdminAccessStatus.ACTIVE.value,
            AdminAccessSession.access_expires_at <= datetime.utcnow(),
        )
    )
    count = 0
    for session in result.scalars().all():
        session.status = AdminAccessStatus.EXPIRED.value
        count += 1
    await db.flush()
    return count
