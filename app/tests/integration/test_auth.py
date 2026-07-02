"""Authentication, RBAC, and tenant-context security tests.

These tests use HTTP route calls against the FastAPI app. Shared fixtures
(tenant, test_user, client, auth_headers, etc.) come from ``app/tests/conftest.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select


@pytest.mark.anyio
async def test_register_user(client, unique):
    """A new user can register."""
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{unique('new')}@example.com",
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
async def test_register_duplicate_email_rejected(client, db, unique):
    """Registering with an existing email is rejected."""
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, _ = await create_test_user(db, org, email=f"{unique('existing')}@example.com")

    response = await client.post(
        "/auth/register",
        json={
            "email": user.email,
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
async def test_login_success(client, db, unique):
    """A verified active user can log in and receive tokens."""
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org)

    response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.anyio
async def test_login_wrong_password_rejected(client, db, unique):
    """Login with wrong password is rejected without account enumeration."""
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, _ = await create_test_user(db, org)

    response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "WrongPassword123!"},
    )
    assert response.status_code == 401
    body = response.json()
    message = body.get("detail") or body.get("message", "")
    assert "Incorrect email or password" in message


@pytest.mark.anyio
async def test_login_inactive_user_rejected(client, db, unique):
    """An inactive user cannot log in."""
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org, is_active=False)

    response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_jwt_protected_endpoint_works(client, db, unique):
    """A valid JWT authenticates the user on a protected endpoint."""
    from app.tests.helpers import auth_headers_for, create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org)
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/admin/tenants", headers=headers)
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
async def test_refresh_token_works(client, db, unique):
    """A refresh token can be exchanged for a new access/refresh pair."""
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org)

    login_response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": password},
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
async def test_email_verification_token_creation_and_verification(client, db, unique):
    """Email verification token can be created and used to verify email."""
    from app.models import User
    from app.services.auth_service import AuthService
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("VerifyOrg"), slug=unique("verify-org"))
    user, _ = await create_test_user(db, org, is_verified=False)

    auth_service = AuthService(db)
    raw_token = await auth_service.create_email_verification(user)
    assert raw_token is not None
    assert len(raw_token) > 0

    success = await auth_service.verify_email(raw_token)
    assert success is True

    result = await db.execute(select(User).where(User.id == user.id))
    updated_user = result.scalar_one()
    assert updated_user.is_email_verified is True


@pytest.mark.anyio
async def test_password_reset_request_and_completion(client, db, unique):
    """Password reset token can be created and used to set a new password."""
    from app.services.auth_service import AuthService
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, _ = await create_test_user(db, org)
    auth_service = AuthService(db)

    raw_token = await auth_service.create_password_reset(user.email)
    assert raw_token is not None

    response = await client.post(
        "/auth/reset-password",
        json={"token": raw_token, "new_password": "NewPass123!"},
    )
    assert response.status_code == 200

    login_response = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "NewPass123!"},
    )
    assert login_response.status_code == 200


@pytest.mark.anyio
async def test_expired_reset_token_rejected(db, unique):
    """An expired or used reset token cannot be used."""
    from app.models import PasswordReset
    from app.services.auth_service import AuthService
    from app.tests.helpers import create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("ExpiredOrg"), slug=unique("expired-org"))
    user, _ = await create_test_user(db, org)
    auth_service = AuthService(db)

    raw_token = await auth_service.create_password_reset(user.email)

    result = await db.execute(select(PasswordReset).where(PasswordReset.token == raw_token))
    reset = result.scalar_one()
    reset.is_used = True
    await db.commit()

    success = await auth_service.reset_password(raw_token, "NewPass123!")
    assert success is False


@pytest.mark.anyio
async def test_normal_user_cannot_access_admin_route(client, db, unique):
    """A normal user is forbidden from super-admin routes."""
    from app.tests.helpers import auth_headers_for, create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org)
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/admin/tenants", headers=headers)
    assert response.status_code == 403


@pytest.mark.anyio
async def test_super_admin_can_access_admin_route(client, db, unique):
    """A super admin can access super-admin routes."""
    from app.tests.helpers import auth_headers_for, create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    admin, password = await create_test_user(db, org, is_superuser=True)
    headers = await auth_headers_for(client, admin.email, password)

    response = await client.get("/admin/tenants", headers=headers)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_user_cannot_impersonate_another_tenant(client, db, unique):
    """A JWT scoped to one tenant cannot read another tenant's rows."""
    from app.models import Account
    from app.core.rls import set_tenant_context_async
    from app.tests.helpers import create_test_organization, create_test_user

    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))

    user_a, password_a = await create_test_user(db, org_a)

    await set_tenant_context_async(db, org_b.id)
    account_b = Account(
        code="9999",
        name="Tenant B Account",
        account_type="Asset",
        tenant_id=org_b.id,
    )
    db.add(account_b)
    await db.commit()

    login_response = await client.post(
        "/auth/login",
        json={"email": user_a.email, "password": password_a},
    )
    assert login_response.status_code == 200

    await set_tenant_context_async(db, org_a.id)
    result = await db.execute(select(Account).where(Account.code == "9999"))
    assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_rls_active_during_authenticated_request(client, db, unique):
    """FORCE RLS remains enabled on tenant-scoped tables after auth operations."""
    from sqlalchemy import text
    from app.tests.helpers import auth_headers_for, create_test_organization, create_test_user

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    user, password = await create_test_user(db, org)
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/admin/tenants", headers=headers)
    assert response.status_code == 403

    direct_result = await db.execute(
        text(
            "SELECT relforcerowsecurity FROM pg_class "
            "WHERE relname = 'accounts' AND relnamespace = 'public'::regnamespace"
        )
    )
    assert direct_result.scalar() is True
