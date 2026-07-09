"""Shared helpers for the PF test suite.

These functions create synthetic test data, build auth headers, and make
RLS assertions. They are used by `app/tests/conftest.py` fixtures and can be
called directly from tests that need fine-grained control.

All helpers assume an active async SQLAlchemy session. They intentionally do
not drop or truncate tables; tests should use unique identifiers and clean up
only the rows they create.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession


def unique(prefix: str) -> str:
    """Generate a unique string for test data to avoid collisions."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def create_test_organization(
    db: AsyncSession,
    name: Optional[str] = None,
    slug: Optional[str] = None,
) -> "Organization":
    """Create a tenant organization for tests."""
    from app.models import Organization

    org = Organization(
        name=name or unique("Tenant"),
        slug=slug or unique("tenant"),
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


async def create_test_user(
    db: AsyncSession,
    organization: Optional["Organization"] = None,
    *,
    email: Optional[str] = None,
    password: str = "SecurePass123!",
    is_superuser: bool = False,
    is_active: bool = True,
    is_verified: bool = True,
    role: str | "UserRole" = "owner",
    commit: bool = True,
) -> tuple["User", str]:
    """Create a test user and return the user object plus plaintext password.

    If no organization is provided, one is created automatically.
    """
    from app.models import User, UserRole
    from app.services.auth_service import AuthService

    if organization is None:
        organization = await create_test_organization(db)

    auth_service = AuthService(db)

    if isinstance(role, str):
        # Support both the enum value ('owner') and the member name ('OWNER').
        role = UserRole(role.lower())

    user = User(
        email=email or f"{unique('user')}@example.com",
        hashed_password=auth_service.hash_password(password),
        first_name="Test",
        last_name="User",
        is_active=is_active,
        is_email_verified=is_verified,
        is_superuser=is_superuser,
        organization_id=organization.id,
        role=role,
        timezone="UTC",
        language="en",
        currency="OMR",
        theme="light",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    if commit:
        await db.commit()
    return user, password


async def auth_headers_for(
    client,
    email: str,
    password: str,
) -> dict[str, str]:
    """Log in and return an Authorization header dict."""
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def rls_status(db: AsyncSession, table_name: str) -> dict[str, bool]:
    """Return RLS and FORCE RLS status for a table."""
    result = await db.execute(
        text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = :table AND relnamespace = 'public'::regnamespace"
        ),
        {"table": table_name},
    )
    row = result.fetchone()
    if row is None:
        return {"rls_enabled": False, "force_rls": False}
    return {"rls_enabled": bool(row[0]), "force_rls": bool(row[1])}


async def assert_rls_enabled(
    db: AsyncSession,
    table_name: str,
    *,
    force: bool = True,
) -> None:
    """Assert that a table has RLS enabled (and FORCE RLS by default)."""
    status = await rls_status(db, table_name)
    assert status["rls_enabled"], f"{table_name}: RLS is not enabled"
    if force:
        assert status["force_rls"], f"{table_name}: FORCE RLS is not enabled"


async def count_rows(
    db: AsyncSession,
    model,
    *filters,
) -> int:
    """Count rows for a model with optional filters."""
    stmt = select(func.count(model.id))
    if filters:
        stmt = stmt.where(*filters)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def create_test_account(
    db: AsyncSession,
    tenant_id: int,
    *,
    code: Optional[str] = None,
    name: Optional[str] = None,
    account_type: str = "Asset",
    visibility: str = "private",
    owner_user_id: Optional[int] = None,
) -> "Account":
    """Create a tenant-scoped account for tests."""
    from app.models import Account

    account = Account(
        tenant_id=tenant_id,
        code=code or unique("acct"),
        name=name or unique("Account"),
        account_type=account_type,
        visibility=visibility,
        owner_user_id=owner_user_id,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


async def create_test_family_member(
    db: AsyncSession,
    family_id: int,
    tenant_id: int,
    user: "User",
    role: str,
) -> "FamilyMember":
    """Create an active family member linking a user to a family."""
    from app.models import FamilyMember

    member = FamilyMember(
        family_id=family_id,
        tenant_id=tenant_id,
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        relationship_type="other",
        role=role,
        is_active=True,
        invitation_accepted_at=datetime.utcnow(),
    )
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member
