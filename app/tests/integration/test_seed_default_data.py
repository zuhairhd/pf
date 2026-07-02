"""Tests for default platform and development seed data.

These tests verify that:
- the seed script runs successfully
- the seed script is idempotent
- tenant-scoped seeded data respects RLS
- no real personal data is seeded

Shared fixtures come from ``app/tests/conftest.py``.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select, func


@pytest.mark.anyio
async def test_seed_script_runs_successfully(db):
    """The seed function completes without errors and returns a summary."""
    from app.seeds import seed_all_default_data

    summary = await seed_all_default_data(db, print_temp_password=False)

    assert summary["organization"] is not None
    assert summary["organization"]["slug"] == "dev-family"
    assert summary["user"] is not None
    assert summary["user"]["email"] == os.getenv("DEV_SUPERUSER_EMAIL", "dev@example.local")
    assert summary["accounts_count"] == 31
    assert summary["budget"] is not None
    assert summary["notification_settings_count"] in (0, 8)


@pytest.mark.anyio
async def test_seed_is_idempotent(db, tenant_context):
    """Running the seed twice does not create duplicate tenant-scoped rows."""
    from app.seeds import seed_all_default_data
    from app.models import Account, Budget, BudgetCategory

    summary1 = await seed_all_default_data(db, print_temp_password=False)
    org_id = summary1["organization"]["id"]

    await tenant_context(org_id)
    accounts_count_1 = (
        await db.execute(select(func.count(Account.id)).where(Account.tenant_id == org_id))
    ).scalar()
    budgets_count_1 = (
        await db.execute(select(func.count(Budget.id)).where(Budget.tenant_id == org_id))
    ).scalar()
    budget_categories_count_1 = (
        await db.execute(
            select(func.count(BudgetCategory.id)).join(Budget).where(Budget.tenant_id == org_id)
        )
    ).scalar()

    summary2 = await seed_all_default_data(db, print_temp_password=False)

    await tenant_context(org_id)
    accounts_count_2 = (
        await db.execute(select(func.count(Account.id)).where(Account.tenant_id == org_id))
    ).scalar()
    budgets_count_2 = (
        await db.execute(select(func.count(Budget.id)).where(Budget.tenant_id == org_id))
    ).scalar()
    budget_categories_count_2 = (
        await db.execute(
            select(func.count(BudgetCategory.id)).join(Budget).where(Budget.tenant_id == org_id)
        )
    ).scalar()

    assert accounts_count_1 == accounts_count_2 == 31
    assert budgets_count_1 == budgets_count_2 == 1
    assert budget_categories_count_1 == budget_categories_count_2 == 14
    assert summary1["organization"]["id"] == summary2["organization"]["id"]
    assert summary1["user"]["id"] == summary2["user"]["id"]


@pytest.mark.anyio
async def test_development_tenant_exists_with_plan_limits(db):
    """The development tenant has expected plan limits applied."""
    from app.models import Organization

    result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = result.scalar_one()

    assert org.name == "Development Family"
    assert org.plan.value in ("free", "premium", "family", "professional")
    assert org.max_users > 0
    assert org.max_transactions > 0
    assert org.max_ai_requests_per_day >= 0
    assert org.max_storage_mb >= 0


@pytest.mark.anyio
async def test_development_user_is_super_admin(db):
    """The development user is a super admin linked to the dev tenant."""
    from app.models import User, Organization

    email = os.getenv("DEV_SUPERUSER_EMAIL", "dev@example.local")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    org_result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = org_result.scalar_one()

    assert user.is_superuser is True
    assert user.organization_id == org.id
    assert user.role.value == "owner"
    assert user.currency == "OMR"


@pytest.mark.anyio
async def test_chart_of_accounts_belongs_to_dev_tenant(db, tenant_context):
    """Seeded accounts belong only to the development tenant."""
    from app.models import Account, Organization

    org_result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = org_result.scalar_one()

    await tenant_context(org.id)
    result = await db.execute(
        select(Account).where(Account.tenant_id == org.id).order_by(Account.code)
    )
    accounts = result.scalars().all()

    assert len(accounts) == 31
    account_types = {acc.account_type for acc in accounts}
    assert account_types == {"Asset", "Liability", "Equity", "Income", "Expense"}

    names = {acc.name for acc in accounts}
    assert "Bank Muscat" in names
    assert "Cash" in names
    assert "Food & Groceries" in names
    assert "Salary" in names


@pytest.mark.anyio
async def test_tenant_scoped_rows_invisible_without_context(db):
    """Seeded tenant rows are not readable when tenant context is cleared."""
    from app.models import Account, Organization
    from app.core.rls import clear_tenant_context_async

    org_result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = org_result.scalar_one()

    await clear_tenant_context_async(db)
    result = await db.execute(select(Account).where(Account.tenant_id == org.id))
    accounts = result.scalars().all()

    assert len(accounts) == 0


@pytest.mark.anyio
async def test_budget_categories_linked_to_expense_accounts(db, tenant_context):
    """Default budget categories are linked to matching expense accounts."""
    from app.models import Budget, BudgetCategory, Organization, Account

    org_result = await db.execute(select(Organization).where(Organization.slug == "dev-family"))
    org = org_result.scalar_one()

    await tenant_context(org.id)
    budget_result = await db.execute(
        select(Budget).where(Budget.tenant_id == org.id, Budget.name == "Monthly Household Budget")
    )
    budget = budget_result.scalar_one()

    categories_result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.budget_id == budget.id)
    )
    categories = categories_result.scalars().all()

    assert len(categories) == 14
    for category in categories:
        assert category.budgeted_amount >= 0
        if category.account_id is not None:
            account_result = await db.execute(
                select(Account).where(Account.id == category.account_id, Account.tenant_id == org.id)
            )
            account = account_result.scalar_one()
            assert account.account_type == "Expense"


@pytest.mark.anyio
async def test_force_rls_remains_enabled(db):
    """FORCE ROW LEVEL SECURITY remains enabled on tenant-scoped tables."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            "SELECT relforcerowsecurity FROM pg_class "
            "WHERE relname = 'accounts' AND relnamespace = 'public'::regnamespace"
        )
    )
    forced = result.scalar()
    assert forced is True


@pytest.mark.anyio
async def test_env_files_are_ignored():
    """.env files are listed in .gitignore and not tracked."""
    from pathlib import Path

    gitignore = Path(".gitignore").read_text()
    assert ".env" in gitignore
    assert ".env.*" in gitignore or ".env.local" in gitignore
