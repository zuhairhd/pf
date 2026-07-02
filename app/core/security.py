"""Authentication, RBAC, and tenant-context dependencies for FastAPI.

This module provides reusable security dependencies that can be injected into
route handlers. It also includes helpers for setting PostgreSQL RLS tenant
context on the database session used by a request.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.core.rls import set_tenant_context_async, clear_tenant_context_async
from app.models import User, UserRole
from app.models.database import get_db


settings = get_settings()
security_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Raised when authorization fails."""

    def __init__(self, detail: str = "Access denied") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _extract_token_from_request(request: Request) -> Optional[str]:
    """Extract a Bearer token from the Authorization header or request state."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    return None


def _decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Raises:
        AuthenticationError: if the token is missing, expired, or invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    return payload


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> User:
    """Dependency that loads and returns the currently authenticated user.

    The token is read from the `Authorization` header or, for HTML routes, from
    the request state populated by middleware.
    """
    token = credentials.credentials if credentials else _extract_token_from_request(request)
    if not token:
        raise AuthenticationError()

    payload = _decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User not found")

    return user


def require_active_user(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires the user to be active."""
    if not user.is_active:
        raise AuthorizationError("Account is inactive")
    return user


def require_verified_user(user: User = Depends(require_active_user)) -> User:
    """Dependency that requires the user's email to be verified."""
    if not user.is_email_verified:
        raise AuthorizationError("Email not verified")
    return user


def require_tenant_member(user: User = Depends(require_active_user)) -> User:
    """Dependency that requires the user to belong to a tenant organization."""
    if not user.organization_id:
        raise AuthorizationError("User is not associated with a tenant")
    return user


def require_tenant_role(
    allowed_roles: set[UserRole],
) -> callable:
    """Factory that returns a dependency requiring one of the given tenant roles."""

    def _require_role(user: User = Depends(require_tenant_member)) -> User:
        if user.role not in allowed_roles:
            raise AuthorizationError("Insufficient tenant permissions")
        return user

    return _require_role


require_tenant_admin = require_tenant_role({UserRole.OWNER, UserRole.ADMIN})
require_tenant_owner = require_tenant_role({UserRole.OWNER})


def require_super_admin(user: User = Depends(require_active_user)) -> User:
    """Dependency that requires a super administrator."""
    if not user.is_superuser:
        raise AuthorizationError("Super admin access required")
    return user


async def get_db_with_tenant_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Dependency that yields a DB session with RLS tenant context set.

    Tenant context is taken from the JWT token. If no tenant context can be
    established, the context is cleared so RLS returns no rows rather than
    leaking data.
    """
    token = _extract_token_from_request(request)
    tenant_id: Optional[int] = None

    if token:
        try:
            payload = _decode_access_token(token)
            tenant_id = payload.get("tenant_id")
        except AuthenticationError:
            tenant_id = None

    if tenant_id:
        await set_tenant_context_async(db, tenant_id)
    else:
        await clear_tenant_context_async(db)

    return db
