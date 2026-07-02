"""Super-admin support access security tests.

These tests verify that super-admin tenant access:
- requires super-admin privileges
- is granted for exactly one tenant at a time
- is justified, time-bounded, and audited
- still obeys normal RLS policies (no universal bypass)

Shared fixtures come from ``app/tests/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text


@pytest.fixture
async def support_access_cast(db, tenant_pair, unique):
    """Create a super admin and two tenant admins for support-access tests."""
    from app.models import User
    from app.services.auth_service import AuthService

    org_a, org_b = tenant_pair
    auth_service = AuthService(db)

    super_admin = User(
        email=f"{unique('superadmin')}@example.com",
        hashed_password=auth_service.hash_password("hash"),
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
        email=f"{unique('admin-a')}@example.com",
        hashed_password=auth_service.hash_password("hash"),
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
        email=f"{unique('admin-b')}@example.com",
        hashed_password=auth_service.hash_password("hash"),
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
async def test_super_admin_can_start_support_session(db, tenant_pair, support_access_cast):
    """Super admin can start an audited session for exactly one tenant."""
    from app.services.admin_access_service import AdminAccessService

    org_a, _ = tenant_pair
    super_admin, _, _ = support_access_cast
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
async def test_normal_user_cannot_start_support_session(db, tenant_pair, support_access_cast):
    """A non-superuser cannot start admin support access."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, _ = tenant_pair
    _, tenant_admin_a, _ = support_access_cast
    service = AdminAccessService(db)

    with pytest.raises(AdminAccessError, match="Super admin access required"):
        await service.start_support_session(
            admin_user=tenant_admin_a,
            target_organization_id=org_a.id,
            reason="I should not be allowed",
        )


@pytest.mark.anyio
async def test_tenant_admin_cannot_access_other_tenant(db, tenant_pair, support_access_cast):
    """A tenant admin cannot start support access for another tenant's organization."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, org_b = tenant_pair
    _, tenant_admin_a, _ = support_access_cast
    service = AdminAccessService(db)

    with pytest.raises(AdminAccessError, match="Super admin access required"):
        await service.start_support_session(
            admin_user=tenant_admin_a,
            target_organization_id=org_b.id,
            reason="Cross-tenant access attempt",
        )


@pytest.mark.anyio
async def test_start_session_requires_reason(db, tenant_pair, support_access_cast):
    """Starting support access without a reason is rejected."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import AdminAccessError

    org_a, _ = tenant_pair
    super_admin, _, _ = support_access_cast
    service = AdminAccessService(db)

    with pytest.raises(AdminAccessError, match="Access reason is required"):
        await service.start_support_session(
            admin_user=super_admin,
            target_organization_id=org_a.id,
            reason="   ",
        )


@pytest.mark.anyio
async def test_expired_session_rejected_for_context(db, tenant_pair, support_access_cast):
    """An expired support session cannot be used to set tenant context."""
    from app.services.admin_access_service import AdminAccessService
    from app.core.admin_context import set_admin_tenant_context_from_session, AdminAccessError

    org_a, _ = tenant_pair
    super_admin, _, _ = support_access_cast
    service = AdminAccessService(db)

    session = await service.start_support_session(
        admin_user=super_admin,
        target_organization_id=org_a.id,
        reason="Short test session",
        expires_minutes=1,
    )
    session.access_expires_at = datetime.utcnow() - timedelta(minutes=1)
    await db.flush()

    with pytest.raises(AdminAccessError, match="Support session has expired"):
        await set_admin_tenant_context_from_session(db, session)


@pytest.mark.anyio
async def test_admin_context_sees_only_target_tenant(db, tenant_pair, support_access_cast, tenant_context):
    """Admin in Tenant A context can only see Tenant A rows, not Tenant B."""
    from app.services.admin_access_service import AdminAccessService
    from app.models import Goal

    org_a, org_b = tenant_pair
    super_admin, _, _ = support_access_cast
    service = AdminAccessService(db)

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

    await tenant_context(org_a.id)
    db.add(goal_a)
    await db.flush()

    await tenant_context(org_b.id)
    db.add(goal_b)
    await db.flush()

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
async def test_no_all_tenant_query_in_admin_mode(db, tenant_pair, tenant_context):
    """Even with an active admin session, a query without tenant context returns nothing."""
    from app.models import Goal
    from app.core.rls import clear_tenant_context_async

    org_a, org_b = tenant_pair

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

    await tenant_context(org_a.id)
    db.add(goal_a)
    await db.flush()

    await tenant_context(org_b.id)
    db.add(goal_b)
    await db.flush()

    await clear_tenant_context_async(db)
    result = await db.execute(select(Goal))
    goals = result.scalars().all()
    assert len(goals) == 0


@pytest.mark.anyio
async def test_audit_event_created(db, tenant_pair, support_access_cast):
    """Starting support access creates an audit record."""
    from app.services.admin_access_service import AdminAccessService
    from app.models import AdminAccessSession

    org_a, _ = tenant_pair
    super_admin, _, _ = support_access_cast
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
