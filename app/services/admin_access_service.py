"""Service layer for super-admin support access sessions.

This is a thin wrapper around app.core.admin_context so that business logic
remains testable and reusable from routes, background tasks, or CLI tools.
"""

from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, AdminAccessSession
from app.core.admin_context import (
    require_super_admin,
    start_admin_tenant_context,
    get_active_admin_access,
    set_admin_tenant_context_from_session,
    end_admin_tenant_context,
    expire_stale_admin_sessions,
    AdminAccessError,
)


class AdminAccessService:
    """Manage audited super-admin support access to a single tenant."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def require_super_admin(self, user: Optional[User]) -> None:
        """Raise if the user is not a super admin."""
        require_super_admin(user)

    async def start_support_session(
        self,
        admin_user: User,
        target_organization_id: int,
        reason: str,
        request: Optional[Request] = None,
        expires_minutes: int = 30,
    ) -> AdminAccessSession:
        """Start a support session and set RLS context to the target tenant."""
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.headers.get("x-forwarded-for") or request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        return await start_admin_tenant_context(
            self.db,
            admin_user,
            target_organization_id,
            reason,
            expires_minutes=expires_minutes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_active_session(self, admin_user_id: int) -> Optional[AdminAccessSession]:
        """Return the active support session for the admin, if any."""
        return await get_active_admin_access(self.db, admin_user_id)

    async def restore_tenant_context(self, access_session: AdminAccessSession) -> None:
        """Re-apply RLS tenant context for an existing active session."""
        await set_admin_tenant_context_from_session(self.db, access_session)

    async def end_support_session(
        self,
        access_session_id: int,
        admin_user_id: int,
    ) -> AdminAccessSession:
        """End a support session and clear RLS context."""
        return await end_admin_tenant_context(self.db, access_session_id, admin_user_id)

    async def expire_stale_sessions(self) -> int:
        """Mark expired active sessions as expired."""
        return await expire_stale_admin_sessions(self.db)

    async def list_recent_sessions(
        self,
        admin_user_id: int,
        limit: int = 50,
    ) -> list[AdminAccessSession]:
        """List recent support sessions for the admin."""
        from sqlalchemy import select
        from app.models import AdminAccessSession as AdminAccessSessionModel

        result = await self.db.execute(
            select(AdminAccessSessionModel)
            .where(AdminAccessSessionModel.admin_user_id == admin_user_id)
            .order_by(AdminAccessSessionModel.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
