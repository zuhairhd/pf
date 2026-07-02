"""Shared pytest fixtures for the PF test suite.

Test database strategy
----------------------
Tests prefer a dedicated database configured via `TEST_DATABASE_URL`. If that
variable is not set, they fall back to the database in `DATABASE_URL`.

When running against the shared development database, tests use unique
identifiers and avoid destructive operations (no `DROP`, no `TRUNCATE` of
non-test data). Individual tests clean up the synthetic rows they create.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Callable

import pytest
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", ASYNC_DATABASE_URL)


@pytest.fixture
def unique() -> Callable[[str], str]:
    """Provide the unique string helper as a fixture."""
    from app.tests.helpers import unique as _unique

    return _unique


@pytest.fixture
async def async_engine():
    """Provide a per-test async engine using the test database URL."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session.

    The session is not wrapped in an automatic transaction rollback because
    several routes and seed functions commit internally. Tests that need a
    rolled-back transaction should use ``async with session.begin():`` or the
    ``transactional_db`` fixture.
    """
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
async def transactional_db(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session that rolls back after the test.

    Useful for tests that do not commit and want a clean slate. Commits made
    by the code under test will release the savepoint and the outer rollback
    will still undo them at fixture teardown.
    """
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        trans = await session.begin_nested()
        yield session
        await trans.rollback()
        await session.close()


@pytest.fixture
async def client() -> AsyncClient:
    """Provide an HTTP client with ``get_db`` overridden to a fresh session."""
    from app.main import app
    from app.models.database import get_db

    engine = create_async_engine(TEST_DATABASE_URL, future=True, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def tenant(db, unique) -> "Organization":
    """Create a single test tenant."""
    from app.tests.helpers import create_test_organization

    return await create_test_organization(db, name=unique("Tenant"), slug=unique("tenant"))


@pytest.fixture
async def tenant_pair(db, unique) -> tuple["Organization", "Organization"]:
    """Create two test tenants."""
    from app.tests.helpers import create_test_organization

    org_a = await create_test_organization(
        db, name=unique("Tenant A"), slug=unique("tenant-a")
    )
    org_b = await create_test_organization(
        db, name=unique("Tenant B"), slug=unique("tenant-b")
    )
    return org_a, org_b


@pytest.fixture
async def test_user_credentials(db, tenant) -> dict:
    """Create a verified active tenant user and return {user, password}."""
    from app.tests.helpers import create_test_user

    user, password = await create_test_user(db, tenant)
    return {"user": user, "password": password}


@pytest.fixture
async def test_user(test_user_credentials) -> "User":
    """Return the user object from ``test_user_credentials``."""
    return test_user_credentials["user"]


@pytest.fixture
async def super_admin_credentials(db, tenant) -> dict:
    """Create a verified active super admin and return {user, password}."""
    from app.tests.helpers import create_test_user

    user, password = await create_test_user(
        db, tenant, is_superuser=True, password="AdminPass123!"
    )
    return {"user": user, "password": password}


@pytest.fixture
async def super_admin(super_admin_credentials) -> "User":
    """Return the super admin user object."""
    return super_admin_credentials["user"]


@pytest.fixture
async def auth_headers(client, test_user_credentials) -> dict[str, str]:
    """Provide Authorization headers for the default test user."""
    from app.tests.helpers import auth_headers_for

    return await auth_headers_for(
        client,
        test_user_credentials["user"].email,
        test_user_credentials["password"],
    )


@pytest.fixture
async def admin_auth_headers(client, super_admin_credentials) -> dict[str, str]:
    """Provide Authorization headers for the default super admin."""
    from app.tests.helpers import auth_headers_for

    return await auth_headers_for(
        client,
        super_admin_credentials["user"].email,
        super_admin_credentials["password"],
    )


@pytest.fixture
async def tenant_context(db):
    """Yield a helper that sets RLS tenant context on the current session.

    The context is cleared at fixture teardown.
    """
    from app.core.rls import set_tenant_context_async, clear_tenant_context_async

    async def _set_context(tenant_id):
        await set_tenant_context_async(db, tenant_id)

    yield _set_context
    await clear_tenant_context_async(db)
