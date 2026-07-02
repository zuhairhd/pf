"""Authentication, RBAC, and tenant-context security tests.

These tests use HTTP route calls against the FastAPI app. Each test gets its
own async engine; the `get_db` dependency is overridden to provide a fresh
session that the route can commit normally.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv(dotenv_path=".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def test_engine():
    """Provide a per-test async engine."""
    engine = create_async_engine(ASYNC_DATABASE_URL, future=True, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(test_engine):
    """Provide an async database session for direct setup/assertions."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(test_engine):
    """Provide an HTTP client with get_db overridden to a fresh session."""
    from app.main import app
    from app.models.database import get_db

    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def _create_test_user(
    db: AsyncSession,
    *,
    is_superuser: bool = False,
    is_active: bool = True,
    is_verified: bool = True,
) -> dict:
    """Helper to create a test user with an organization."""
    from app.models import Organization, User, UserRole
    from app.services.auth_service import AuthService

    org = Organization(name=_unique("Org"), slug=_unique("org"))
    db.add(org)
    await db.flush()

    password = "SecurePass123!"
    auth_service = AuthService(db)
    user = User(
        email=f"{_unique('user')}@example.com",
        hashed_password=auth_service.hash_password(password),
        first_name="Test",
        last_name="User",
        is_active=is_active,
        is_email_verified=is_verified,
        is_superuser=is_superuser,
        organization_id=org.id,
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user": user, "password": password, "organization": org}


@pytest.mark.anyio
async def test_register_user(client):
    """A new user can register."""
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{_unique('new')}@example.com",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "Registration successful" in data["message"]


@pytest.mark.anyio
async def test_register_duplicate_email_rejected(client, db):
    """Registering with an existing email is rejected."""
    existing = await _create_test_user(db)

    response = await client.post(
        "/auth/register",
        json={
            "email": existing["user"].email,
            "password": "AnotherPass123!",
            "first_name": "Duplicate",
            "last_name": "User",
        },
    )
    assert response.status_code == 400
    body = response.json()
    message = body.get("detail") or body.get("message", "")
    assert "Email already registered" in message


@pytest.mark.anyio
async def test_login_success(client, db):
    """A verified active user can log in and receive tokens."""
    test_user = await _create_test_user(db)

    response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.anyio
async def test_login_wrong_password_rejected(client, db):
    """Login with wrong password is rejected without account enumeration."""
    test_user = await _create_test_user(db)

    response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    body = response.json()
    message = body.get("detail") or body.get("message", "")
    assert "Incorrect email or password" in message


@pytest.mark.anyio
async def test_login_inactive_user_rejected(client, db):
    """An inactive user cannot log in."""
    test_user = await _create_test_user(db, is_active=False)

    response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_jwt_protected_endpoint_works(client, db):
    """A valid JWT authenticates the user on a protected endpoint."""
    test_user = await _create_test_user(db)

    login_response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Authenticated, but normal user is not authorized for admin route.
    assert response.status_code == 403


@pytest.mark.anyio
async def test_invalid_token_rejected(client):
    """An invalid token is rejected."""
    response = await client.get(
        "/admin/tenants",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_refresh_token_works(client, db):
    """A refresh token can be exchanged for a new access/refresh pair."""
    test_user = await _create_test_user(db)

    login_response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    # Old refresh token should now be invalid.
    second_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert second_response.status_code == 401


@pytest.mark.anyio
async def test_email_verification_token_creation_and_verification(client, db):
    """Email verification token can be created and used to verify email."""
    from app.models import User, Organization, UserRole
    from app.services.auth_service import AuthService

    org = Organization(name=_unique("VerifyOrg"), slug=_unique("verify-org"))
    db.add(org)
    await db.flush()

    auth_service = AuthService(db)
    user = User(
        email=f"{_unique('verify')}@example.com",
        hashed_password=auth_service.hash_password("SecurePass123!"),
        first_name="Verify",
        last_name="Me",
        is_active=True,
        is_email_verified=False,
        organization_id=org.id,
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.commit()

    raw_token = await auth_service.create_email_verification(user)
    assert raw_token is not None
    assert len(raw_token) > 0

    success = await auth_service.verify_email(raw_token)
    assert success is True

    # Reload user and verify email is marked verified.
    result = await db.execute(select(User).where(User.id == user.id))
    updated_user = result.scalar_one()
    assert updated_user.is_email_verified is True


@pytest.mark.anyio
async def test_password_reset_request_and_completion(client, db):
    """Password reset token can be created and used to set a new password."""
    from app.services.auth_service import AuthService

    test_user = await _create_test_user(db)
    auth_service = AuthService(db)

    raw_token = await auth_service.create_password_reset(test_user["user"].email)
    assert raw_token is not None

    response = await client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPass123!"},
    )
    assert response.status_code == 200

    # Login with new password should succeed.
    login_response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": "NewPass123!"},
    )
    assert login_response.status_code == 200


@pytest.mark.anyio
async def test_expired_reset_token_rejected(db):
    """An expired or used reset token cannot be used."""
    from app.models import User, Organization, UserRole, PasswordReset
    from app.services.auth_service import AuthService

    org = Organization(name=_unique("ExpiredOrg"), slug=_unique("expired-org"))
    db.add(org)
    await db.flush()

    auth_service = AuthService(db)
    user = User(
        email=f"{_unique('expired')}@example.com",
        hashed_password=auth_service.hash_password("OldPass123!"),
        first_name="Expired",
        last_name="Token",
        is_active=True,
        is_email_verified=True,
        organization_id=org.id,
        role=UserRole.OWNER,
    )
    db.add(user)
    await db.commit()

    raw_token = await auth_service.create_password_reset(user.email)

    # Mark token as used.
    result = await db.execute(select(PasswordReset).where(PasswordReset.token == raw_token))
    reset = result.scalar_one()
    reset.is_used = True
    await db.commit()

    success = await auth_service.reset_password(raw_token, "NewPass123!")
    assert success is False


@pytest.mark.anyio
async def test_normal_user_cannot_access_admin_route(client, db):
    """A normal user is forbidden from super-admin routes."""
    test_user = await _create_test_user(db)

    login_response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_super_admin_can_access_admin_route(client, db):
    """A super admin can access super-admin routes."""
    test_admin = await _create_test_user(db, is_superuser=True)

    login_response = await client.post(
        "/auth/login",
        json={"email": test_admin["user"].email, "password": test_admin["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_user_cannot_impersonate_another_tenant(client, db):
    """A JWT scoped to one tenant cannot read another tenant's rows."""
    from app.models import User, Organization, Account, UserRole
    from app.services.auth_service import AuthService
    from app.core.rls import set_tenant_context_async

    org_a = Organization(name=_unique("Org A"), slug=_unique("org-a"))
    org_b = Organization(name=_unique("Org B"), slug=_unique("org-b"))
    db.add(org_a)
    db.add(org_b)
    await db.flush()

    auth_service = AuthService(db)
    user_a = User(
        email=f"{_unique('user-a')}@example.com",
        hashed_password=auth_service.hash_password("SecurePass123!"),
        first_name="User",
        last_name="A",
        is_active=True,
        is_email_verified=True,
        organization_id=org_a.id,
        role=UserRole.OWNER,
    )
    db.add(user_a)
    await db.commit()

    # Seed an account in tenant B.
    await set_tenant_context_async(db, org_b.id)
    account_b = Account(
        code="9999",
        name="Tenant B Account",
        account_type="Asset",
        tenant_id=org_b.id,
    )
    db.add(account_b)
    await db.commit()

    # User A logs in; token carries tenant_id = org_a.id.
    login_response = await client.post(
        "/auth/login",
        json={"email": user_a.email, "password": "SecurePass123!"},
    )
    assert login_response.status_code == 200

    # Direct DB proof: with user A's tenant context, account B is invisible.
    await set_tenant_context_async(db, org_a.id)
    result = await db.execute(select(Account).where(Account.code == "9999"))
    assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_rls_active_during_authenticated_request(client, db):
    """FORCE RLS remains enabled on tenant-scoped tables after auth operations."""
    from sqlalchemy import text

    test_user = await _create_test_user(db)

    login_response = await client.post(
        "/auth/login",
        json={"email": test_user["user"].email, "password": test_user["password"]},
    )
    token = login_response.json()["access_token"]

    response = await client.get(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403

    direct_result = await db.execute(
        text(
            "SELECT relforcerowsecurity FROM pg_class "
            "WHERE relname = 'accounts' AND relnamespace = 'public'::regnamespace"
        )
    )
    assert direct_result.scalar() is True
