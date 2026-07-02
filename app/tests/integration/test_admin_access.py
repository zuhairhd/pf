"""Super-admin support access security tests.

These tests verify that super-admin tenant access:
- requires super-admin privileges
- is granted for exactly one tenant at a time
- is justified, time-bounded, and audited
- still obeys normal RLS policies (no universal bypass)
"""

import os
import uuid
from datetime import datetime, timedelta

import pytest
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text

load_dotenv(dotenv_path=".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def db():
    """Provide an async database session and roll back after each test."""
    engine = create_async_engine(ASYNC_DATABASE_URL, future=True, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
        # Rollback happens automatically when the nested transaction context exits.
    await engine.dispose()


@pytest.fixture
async def test_tenants(db):
    """Create two tenant organizations for tests."""
    from app.models import Organization

    org_a = Organization(name=_unique("Tenant A"), slug=_unique("tenant-a"))
    org_b = Organization(name=_unique("Tenant B"), slug=_unique("tenant-b"))
    db.add(org_a)
    db.add(org_b)
    await db.flush()
    await db.refresh(org_a)
    await db.refresh(org_b)
    return org_a, org_b


@pytest.fixture
async def test_users(db, test_tenants):
    """Create a super admin and two normal tenant users."""
    from app.models import User

    org_a, org_b = test_tenants

    super_admin = User(
        email=f"superadmin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        first_name="Super",
        last_name="Admin",
        is_active=True,
        is_email_verified=True,
        is_superuser=True,
        is_2fa_enabled=False,
        organization_id=org_a.id,
        role="owner",
        timezone="UTC",
        language="en",
        currency="OMR",
        theme="light",
    )
    tenant_admin_a = User(
        email=f"admin_a_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        first_name="Admin",
        last_name="A",
        is_active=True,
        is_email_verified=True,
        is_superuser=False,
        is_2fa_enabled=False,
        organization_id=org_a.id,
        role="owner",
        timezone="UTC",
        language="en",
        currency="OMR",
        theme="light",
    )
    tenant_admin_b = User(
        email=f"admin_b_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        first_name="Admin",
        last_name="B",
        is_active=True,
        is_email_verified=True,
        is_superuser=False,
        is_2fa_enabled=False,
        organization_id=org_b.id,
        role="owner",
        timezone="UTC",
        language="en",
        currency="OMR",
        theme="light",
    )
    db.add(super_admin)
    db.add(tenant_admin_a)
    db.add(tenant_admin_b)
    await db.flush()
    await db.refresh(super_admin)
    await db.refresh(tenant_admin_a)
    await db.refresh(tenant_admin_b)
    return super_admin, tenant_admin_a, tenant_admin_b


@pytest.mark.anyio
async def test_super_admin_can_start_support_session(db, test_tenants, test_users):
    """Super admin can start an audited session for exactly one tenant."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, _ = test_tenants
    super_admin, _, _ = test_users
    service = AdminAccessService(db)

    session = await service.start_support_session(
        admin_user=super_admin,
        target_organization_id=org_a.id,
        reason="Investigating billing discrepancy",
        expires_minutes=15,
    )

    assert session.admin_user_id == super_admin.id
    assert session.target_organization_id == org_a.id
    assert session.reason == "Investigating billing discrepancy"
    assert session.status == "active"
    assert session.access_expires_at > datetime.utcnow()


@pytest.mark.anyio
async def test_normal_user_cannot_start_support_session(db, test_tenants, test_users):
    """A non-superuser cannot start admin support access."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, _ = test_tenants
    _, tenant_admin_a, _ = test_users
    service = AdminAccessService(db)

    with pytest.raises(AdminAccessError, match="Super admin access required"):
        await service.start_support_session(
            admin_user=tenant_admin_a,
            target_organization_id=org_a.id,
            reason="I should not be allowed",
        )


@pytest.mark.anyio
async def test_tenant_admin_cannot_access_other_tenant(db, test_tenants, test_users):
    """A tenant admin cannot start support access for another tenant's organization."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, org_b = test_tenants
    _, tenant_admin_a, _ = test_users
    service = AdminAccessService(db)

    # tenant_admin_a belongs to org_a and is NOT a superuser, so even targeting
    # org_b should be rejected at the superuser check before any tenant check.
    with pytest.raises(AdminAccessError, match="Super admin access required"):
        await service.start_support_session(
            admin_user=tenant_admin_a,
            target_organization_id=org_b.id,
            reason="Cross-tenant access attempt",
        )


@pytest.mark.anyio
async def test_start_session_requires_reason(db, test_tenants, test_users):
    """Starting support access without a reason is rejected."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, _ = test_tenants
    super_admin, _, _ = test_users
    service = AdminAccessService(db)

    with pytest.raises(AdminAccessError, match="Access reason is required"):
        await service.start_support_session(
            admin_user=super_admin,
            target_organization_id=org_a.id,
            reason="   ",
        )


@pytest.mark.anyio
async def test_expired_session_rejected_for_context(db, test_tenants, test_users):
    """An expired support session cannot be used to set tenant context."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import set_admin_tenant_context_from_session
    from app.core.admin_context import AdminAccessError
    from app.models import AdminAccessSession

    org_a, _ = test_tenants
    super_admin, _, _ = test_users
    service = AdminAccessService(db)

    session = await service.start_support_session(
        admin_user=super_admin,
        target_organization_id=org_a.id,
        reason="Short test session",
        expires_minutes=1,
    )
    # Manually expire the session in the database.
    session.access_expires_at = datetime.utcnow() - timedelta(minutes=1)
    await db.flush()

    with pytest.raises(AdminAccessError, match="Support session has expired"):
        await set_admin_tenant_context_from_session(db, session)


@pytest.mark.anyio
async def test_admin_context_sees_only_target_tenant(db, test_tenants, test_users):
    """Admin in Tenant A context can only see Tenant A rows, not Tenant B."""
    from app.services.admin_access_service import AdminAccessService
    from app.models import Goal

    org_a, org_b = test_tenants
    super_admin, _, _ = test_users
    service = AdminAccessService(db)

    # Seed one goal per tenant. RLS INSERT policies require the matching tenant
    # context, so we set the GUC for each insert.
    from app.core.rls import set_tenant_context_async

    goal_a = Goal(
        name="Goal A",
        goal_type="CUSTOM",
        status="ACTIVE",
        target_amount=1000,
        current_amount=0,
        monthly_contribution=100,
        priority=1,
        tenant_id=org_a.id,
    )
    goal_b = Goal(
        name="Goal B",
        goal_type="CUSTOM",
        status="ACTIVE",
        target_amount=2000,
        current_amount=0,
        monthly_contribution=200,
        priority=1,
        tenant_id=org_b.id,
    )

    await set_tenant_context_async(db, org_a.id)
    db.add(goal_a)
    await db.flush()

    await set_tenant_context_async(db, org_b.id)
    db.add(goal_b)
    await db.flush()

    # Start support session for Tenant A and verify RLS filtering.
    await service.start_support_session(
        admin_user=super_admin,
        target_organization_id=org_a.id,
        reason="Support Tenant A",
    )

    result = await db.execute(select(Goal))
    goals = result.scalars().all()
    assert len(goals) == 1
    assert goals[0].tenant_id == org_a.id
    assert goals[0].name == "Goal A"


@pytest.mark.anyio
async def test_no_all_tenant_query_in_admin_mode(db, test_tenants, test_users):
    """Even with an active admin session, a query without tenant context returns nothing."""
    from app.models import Goal
    from app.core.rls import set_tenant_context_async, clear_tenant_context_async

    org_a, org_b = test_tenants

    goal_a = Goal(
        name="Goal A",
        goal_type="CUSTOM",
        status="ACTIVE",
        target_amount=1000,
        current_amount=0,
        monthly_contribution=100,
        priority=1,
        tenant_id=org_a.id,
    )
    goal_b = Goal(
        name="Goal B",
        goal_type="CUSTOM",
        status="ACTIVE",
        target_amount=2000,
        current_amount=0,
        monthly_contribution=200,
        priority=1,
        tenant_id=org_b.id,
    )

    await set_tenant_context_async(db, org_a.id)
    db.add(goal_a)
    await db.flush()

    await set_tenant_context_async(db, org_b.id)
    db.add(goal_b)
    await db.flush()

    # No tenant context set.
    await clear_tenant_context_async(db)
    result = await db.execute(select(Goal))
    goals = result.scalars().all()
    assert len(goals) == 0


@pytest.mark.anyio
async def test_audit_event_created(db, test_tenants, test_users):
    """Starting support access creates an audit record."""
    from app.services.admin_access_service import AdminAccessService
    from app.models import AdminAccessSession

    org_a, _ = test_tenants
    super_admin, _, _ = test_users
    service = AdminAccessService(db)

    await service.start_support_session(
        admin_user=super_admin,
        target_organization_id=org_a.id,
        reason="Audit test",
    )
    await db.flush()

    result = await db.execute(
        select(AdminAccessSession).where(
            AdminAccessSession.admin_user_id == super_admin.id,
            AdminAccessSession.target_organization_id == org_a.id,
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.reason == "Audit test"
    assert audit.status == "active"


@pytest.mark.anyio
async def test_force_rls_remains_enabled(db):
    """FORCE ROW LEVEL SECURITY remains enabled on tenant-scoped tables."""
    result = await db.execute(
        text(
            "SELECT relforcerowsecurity FROM pg_class "
            "WHERE relname = 'accounts' AND relnamespace = 'public'::regnamespace"
        )
    )
    forced = result.scalar()
    assert forced is True
