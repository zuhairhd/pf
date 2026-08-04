"""Financial Reports UI / Report Center tests (REP-2001).

Covers the server-rendered Report Center (GET /reports) and its HTMX
partials (GET /reports/partials/*) built on top of the unchanged
REP-2000 ReportService/generators. No report calculation logic is
duplicated here — these tests verify rendering, date-filter defaults
and validation, empty states, read-only safety, and tenant/RLS
isolation of the UI layer only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import (
    Account,
    AIInsight,
    Budget,
    Goal,
    JournalEntry,
    Notification,
)
from app.schemas.accounting import JournalEntryCreate, JournalLineCreate
from app.services.accounting_service import AccountingService
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
)


async def _create_account(
    db,
    tenant_id: int,
    code: str,
    name: str,
    account_type: str,
    *,
    is_bank_account: bool = False,
    is_cash_account: bool = False,
):
    account = Account(
        tenant_id=tenant_id,
        code=code,
        name=name,
        account_type=account_type,
        is_bank_account=is_bank_account,
        is_cash_account=is_cash_account,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


async def _post_entry(db, tenant_id: int, entry_date: date, lines: list):
    service = AccountingService(db, tenant_id)
    return await service.create_journal_entry(
        JournalEntryCreate(
            date=entry_date,
            narration="Test entry",
            lines=[
                JournalLineCreate(
                    account_id=line["account_id"],
                    debit=line.get("debit", Decimal("0")),
                    credit=line.get("credit", Decimal("0")),
                )
                for line in lines
            ],
        )
    )


async def _setup_report_tenant(db, unique):
    """Create a tenant with a simple chart of accounts (mirrors test_reports.py)."""
    org = await create_test_organization(db, name=unique("ReportOrg"), slug=unique("report-org"))
    await set_tenant_context_async(db, org.id)

    bank = await _create_account(db, org.id, unique("bank"), unique("Bank Account"), "Asset", is_bank_account=True)
    cash = await _create_account(db, org.id, unique("cash"), unique("Cash Wallet"), "Asset", is_cash_account=True)
    salary = await _create_account(db, org.id, unique("salary"), unique("Salary Income"), "Income")
    rent = await _create_account(db, org.id, unique("rent"), unique("Rent Expense"), "Expense")
    groceries = await _create_account(db, org.id, unique("groceries"), unique("Groceries"), "Expense")
    loan = await _create_account(db, org.id, unique("loan"), unique("Personal Loan"), "Liability")
    equity = await _create_account(db, org.id, unique("equity"), unique("Owner Equity"), "Equity")

    return org, {
        "bank": bank, "cash": cash, "salary": salary, "rent": rent,
        "groceries": groceries, "loan": loan, "equity": equity,
    }


async def _setup_user(db, org, unique):
    user, password = await create_test_user(db, org, email=unique("owner") + "@example.com", role="owner")
    return user, password


async def _post_sample_activity(db, org, accounts, today):
    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("1000.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("1000.000")},
        ],
    )
    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("300.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("300.000")},
        ],
    )
    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["groceries"].id, "debit": Decimal("200.000")},
            {"account_id": accounts["cash"].id, "credit": Decimal("200.000")},
        ],
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Routes / auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reports_center_requires_auth(client):
    response = await client.get("/reports")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/reports/partials/income-statement",
        "/reports/partials/balance-sheet",
        "/reports/partials/cash-flow",
        "/reports/partials/net-worth",
        "/reports/partials/expense-analysis",
    ],
)
async def test_report_partial_requires_auth(client, path):
    response = await client.get(path)
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_authenticated_tenant_user_can_view_reports_center(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/reports", headers=headers)
    assert response.status_code == 200, response.text
    assert "Report Center" in response.text


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_report_center_renders_report_cards(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/reports", headers=headers)
    assert response.status_code == 200, response.text
    for label in ("Income Statement", "Balance Sheet", "Cash Flow", "Net Worth", "Expense Analysis"):
        assert label in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_income_statement_partial_renders_totals(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()
    await _post_sample_activity(db, org, accounts, today)

    response = await client.get(
        "/reports/partials/income-statement",
        params={
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "1000.000" in response.text
    assert "500.000" in response.text
    assert accounts["salary"].name in response.text
    assert accounts["rent"].name in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_balance_sheet_partial_renders_totals(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()

    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("2000.000")},
            {"account_id": accounts["equity"].id, "credit": Decimal("2000.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/partials/balance-sheet",
        params={"as_of_date": today.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "2000.000" in response.text
    assert "Balanced" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_cash_flow_partial_renders_totals(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()
    await _post_sample_activity(db, org, accounts, today)

    response = await client.get(
        "/reports/partials/cash-flow",
        params={
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "1000.000" in response.text
    assert "500.000" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_net_worth_partial_renders_totals(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()

    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("1500.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("1500.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/partials/net-worth",
        params={"as_of_date": today.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "1500.000" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_expense_analysis_partial_renders_totals_and_top_expenses(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()

    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("400.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("400.000")},
        ],
    )
    await _post_entry(
        db, org.id, today,
        [
            {"account_id": accounts["groceries"].id, "debit": Decimal("100.000")},
            {"account_id": accounts["cash"].id, "credit": Decimal("100.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/partials/expense-analysis",
        params={
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "500.000" in response.text
    assert "Top Expense Accounts" in response.text
    assert accounts["rent"].name in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_empty_state_renders_when_no_accounts(client, db, unique):
    org = await create_test_organization(db, name=unique("Empty Org"), slug=unique("empty-org"))
    user, password = await create_test_user(db, org, email=unique("owner") + "@example.com", role="owner")
    headers = await auth_headers_for(client, user.email, password)

    response = await client.get("/reports/partials/income-statement", headers=headers)
    assert response.status_code == 200, response.text
    assert "No income or expense accounts" in response.text


# ---------------------------------------------------------------------------
# Date filters
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_valid_date_range_works(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()
    await _post_sample_activity(db, org, accounts, today)

    response = await client.get(
        "/reports/partials/income-statement",
        params={
            "start_date": (today - timedelta(days=1)).isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert "1000.000" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_invalid_date_range_shows_safe_error(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()

    response = await client.get(
        "/reports/partials/income-statement",
        params={
            "start_date": (today + timedelta(days=5)).isoformat(),
            "end_date": today.isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert "on or before" in response.text.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_missing_date_defaults_work(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()
    await _post_sample_activity(db, org, accounts, today)

    response = await client.get("/reports/partials/income-statement", headers=headers)
    assert response.status_code == 200, response.text
    assert "1000.000" in response.text

    response = await client.get("/reports/partials/balance-sheet", headers=headers)
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Read-only safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewing_reports_creates_no_financial_or_ai_records(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await _setup_user(db, org, unique)
    headers = await auth_headers_for(client, user.email, password)
    today = date.today()
    await _post_sample_activity(db, org, accounts, today)

    await set_tenant_context_async(db, org.id)
    journals_before = await count_rows(db, JournalEntry)
    accounts_before = await count_rows(db, Account)
    budgets_before = await count_rows(db, Budget)
    goals_before = await count_rows(db, Goal)
    notifications_before = await count_rows(db, Notification)
    insights_before = await count_rows(db, AIInsight)

    await client.get("/reports", headers=headers)
    await client.get("/reports/partials/income-statement", headers=headers)
    await client.get("/reports/partials/balance-sheet", headers=headers)
    await client.get("/reports/partials/cash-flow", headers=headers)
    await client.get("/reports/partials/net-worth", headers=headers)
    await client.get("/reports/partials/expense-analysis", headers=headers)

    await set_tenant_context_async(db, org.id)
    assert await count_rows(db, JournalEntry) == journals_before
    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Budget) == budgets_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, Notification) == notifications_before
    assert await count_rows(db, AIInsight) == insights_before


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_report_data_in_ui(client, db, unique):
    org_a, accounts_a = await _setup_report_tenant(db, unique)
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")

    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    today = date.today()
    await _post_entry(
        db, org_a.id, today,
        [
            {"account_id": accounts_a["rent"].id, "debit": Decimal("777.000")},
            {"account_id": accounts_a["bank"].id, "credit": Decimal("777.000")},
        ],
    )
    await db.commit()

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    response = await client.get(
        "/reports/partials/expense-analysis",
        params={
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
        headers=headers_b,
    )
    assert response.status_code == 200, response.text
    assert "777.000" not in response.text
    assert accounts_a["rent"].name not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_journal_tables_via_reports_ui(db):
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
