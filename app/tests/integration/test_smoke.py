"""Smoke tests for application health, database, migrations, RLS, and seed data.

These tests are intentionally fast and do not require complex setup. They give
confidence that the environment is wired correctly before longer integration
suites run.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text


@pytest.mark.smoke
@pytest.mark.anyio
async def test_app_imports():
    """The FastAPI app imports without errors."""
    from app.main import app

    assert app is not None
    assert app.title is not None


@pytest.mark.smoke
@pytest.mark.anyio
async def test_database_connection(db):
    """The configured database is reachable."""
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.smoke
@pytest.mark.anyio
async def test_alembic_head_is_current(db):
    """The database revision matches the latest Alembic migration."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    result = await db.execute(text("SELECT version_num FROM alembic_version"))
    db_revision = result.scalar()

    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    assert db_revision == head_revision, f"DB is at {db_revision}, expected head {head_revision}"


@pytest.mark.smoke
@pytest.mark.anyio
async def test_rls_enabled_on_accounts(db):
    """RLS and FORCE RLS are enabled on a representative tenant-scoped table."""
    from app.tests.helpers import assert_rls_enabled

    await assert_rls_enabled(db, "accounts", force=True)


@pytest.mark.smoke
@pytest.mark.anyio
async def test_rls_enabled_on_child_table(db):
    """RLS and FORCE RLS are enabled on a representative child table."""
    from app.tests.helpers import assert_rls_enabled

    await assert_rls_enabled(db, "ai_chat_messages", force=True)


@pytest.mark.smoke
@pytest.mark.anyio
async def test_seed_script_is_idempotent(db, tenant_context):
    """Running the seed script twice leaves the dev tenant rows unchanged."""
    from sqlalchemy import func, select
    from app.models import Account, Budget, Organization
    from app.seeds import seed_all_default_data

    await seed_all_default_data(db, print_temp_password=False)

    org_result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = org_result.scalar_one()

    await tenant_context(org.id)
    accounts_before = (
        await db.execute(select(func.count(Account.id)).where(Account.tenant_id == org.id))
    ).scalar()
    budgets_before = (
        await db.execute(select(func.count(Budget.id)).where(Budget.tenant_id == org.id))
    ).scalar()

    await seed_all_default_data(db, print_temp_password=False)

    await tenant_context(org.id)
    accounts_after = (
        await db.execute(select(func.count(Account.id)).where(Account.tenant_id == org.id))
    ).scalar()
    budgets_after = (
        await db.execute(select(func.count(Budget.id)).where(Budget.tenant_id == org.id))
    ).scalar()

    assert accounts_before == accounts_after == 31
    assert budgets_before == budgets_after == 1


@pytest.mark.smoke
@pytest.mark.anyio
async def test_protected_route_rejects_anonymous(client):
    """A protected endpoint rejects a request with no token."""
    response = await client.get("/admin/tenants")
    assert response.status_code == 401


@pytest.mark.smoke
@pytest.mark.anyio
async def test_auth_login_for_seeded_dev_user(client):
    """The seeded development super-admin can log in when credentials are available."""
    email = os.getenv("DEV_SUPERUSER_EMAIL", "dev@example.local")
    password = os.getenv("DEV_SUPERUSER_PASSWORD")
    if not password:
        pytest.skip("DEV_SUPERUSER_PASSWORD not set")

    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
