"""Basic financial reports integration tests.

Covers income statement, balance sheet, cash flow, net worth, and expense
analysis. All reports are tenant-scoped, RLS-safe, and exclude reversed
original journal entries while keeping the offsetting reversal entries.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.rls import set_tenant_context_async
from app.models import Account, JournalEntry, JournalLine
from app.schemas.accounting import JournalEntryCreate, JournalLineCreate
from app.services.accounting_service import AccountingService
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
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
    """Create a tenant with a simple chart of accounts."""
    org = await create_test_organization(
        db, name=unique("ReportOrg"), slug=unique("report-org")
    )
    await set_tenant_context_async(db, org.id)

    bank = await _create_account(
        db, org.id, unique("bank"), unique("Bank Account"), "Asset", is_bank_account=True
    )
    cash = await _create_account(
        db, org.id, unique("cash"), unique("Cash Wallet"), "Asset", is_cash_account=True
    )
    salary = await _create_account(
        db, org.id, unique("salary"), unique("Salary Income"), "Income"
    )
    rent = await _create_account(
        db, org.id, unique("rent"), unique("Rent Expense"), "Expense"
    )
    groceries = await _create_account(
        db, org.id, unique("groceries"), unique("Groceries"), "Expense"
    )
    loan = await _create_account(
        db, org.id, unique("loan"), unique("Personal Loan"), "Liability"
    )
    equity = await _create_account(
        db, org.id, unique("equity"), unique("Owner Equity"), "Equity"
    )

    return org, {
        "bank": bank,
        "cash": cash,
        "salary": salary,
        "rent": rent,
        "groceries": groceries,
        "loan": loan,
        "equity": equity,
    }


@pytest.mark.integration
@pytest.mark.anyio
async def test_income_statement_calculations_and_date_filter(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=1)

    # Inside range: income 1000, expenses 300 + 200 = 500, net 500.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("1000.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("1000.000")},
        ],
    )
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("300.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("300.000")},
        ],
    )
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["groceries"].id, "debit": Decimal("200.000")},
            {"account_id": accounts["cash"].id, "credit": Decimal("200.000")},
        ],
    )

    # Outside range: should be ignored.
    await _post_entry(
        db,
        org.id,
        today - timedelta(days=60),
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("5000.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("5000.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/income-statement",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert Decimal(data["income_total"]) == Decimal("1000.000")
    assert Decimal(data["expense_total"]) == Decimal("500.000")
    assert Decimal(data["net_income"]) == Decimal("500.000")

    income_by_id = {a["account_id"]: a for a in data["income_accounts"]}
    expense_by_id = {a["account_id"]: a for a in data["expense_accounts"]}
    assert Decimal(income_by_id[accounts["salary"].id]["amount"]) == Decimal("1000.000")
    assert Decimal(expense_by_id[accounts["rent"].id]["amount"]) == Decimal("300.000")
    assert Decimal(expense_by_id[accounts["groceries"].id]["amount"]) == Decimal("200.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_balance_sheet_calculations_and_as_of_filter(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()

    # Equity injection: debit bank 2000, credit equity 2000.
    await _post_entry(
        db,
        org.id,
        today - timedelta(days=10),
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("2000.000")},
            {"account_id": accounts["equity"].id, "credit": Decimal("2000.000")},
        ],
    )
    # Take a loan after as_of date.
    await _post_entry(
        db,
        org.id,
        today + timedelta(days=1),
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("500.000")},
            {"account_id": accounts["loan"].id, "credit": Decimal("500.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/balance-sheet",
        params={"as_of_date": today.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert Decimal(data["assets_total"]) == Decimal("2000.000")
    assert Decimal(data["liabilities_total"]) == Decimal("0")
    assert Decimal(data["equity_total"]) == Decimal("2000.000")
    assert Decimal(data["net_worth"]) == Decimal("2000.000")
    assert data["balance_check"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_cash_flow_summary(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=1)

    # Inflow: debit bank 1000, credit income.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("1000.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("1000.000")},
        ],
    )
    # Outflow: debit rent, credit bank 300.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("300.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("300.000")},
        ],
    )
    # Outflow from cash wallet: debit groceries, credit cash 200.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["groceries"].id, "debit": Decimal("200.000")},
            {"account_id": accounts["cash"].id, "credit": Decimal("200.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/cash-flow",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert Decimal(data["cash_inflow"]) == Decimal("1000.000")
    assert Decimal(data["cash_outflow"]) == Decimal("500.000")
    assert Decimal(data["net_cash_flow"]) == Decimal("500.000")

    by_id = {a["account_id"]: a for a in data["by_account"]}
    assert Decimal(by_id[accounts["bank"].id]["inflow"]) == Decimal("1000.000")
    assert Decimal(by_id[accounts["bank"].id]["outflow"]) == Decimal("300.000")
    assert Decimal(by_id[accounts["bank"].id]["net"]) == Decimal("700.000")
    assert Decimal(by_id[accounts["cash"].id]["outflow"]) == Decimal("200.000")
    assert Decimal(by_id[accounts["cash"].id]["net"]) == Decimal("-200.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_net_worth_summary(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()

    # Assets 1500, liabilities 500 -> net worth 1000.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["bank"].id, "debit": Decimal("1500.000")},
            {"account_id": accounts["salary"].id, "credit": Decimal("1500.000")},
        ],
    )
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["cash"].id, "debit": Decimal("200.000")},
            {"account_id": accounts["loan"].id, "credit": Decimal("500.000")},
            {"account_id": accounts["equity"].id, "credit": Decimal("-300.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/net-worth",
        params={"as_of_date": today.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert Decimal(data["total_assets"]) == Decimal("1700.000")
    assert Decimal(data["total_liabilities"]) == Decimal("500.000")
    assert Decimal(data["net_worth"]) == Decimal("1200.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_expense_analysis(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=1)

    # Rent 400, groceries 100 -> total 500.
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("400.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("400.000")},
        ],
    )
    await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["groceries"].id, "debit": Decimal("100.000")},
            {"account_id": accounts["cash"].id, "credit": Decimal("100.000")},
        ],
    )
    await db.commit()

    response = await client.get(
        "/reports/expense-analysis",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()

    assert Decimal(data["total_expenses"]) == Decimal("500.000")
    by_id = {a["account_id"]: a for a in data["expenses_by_account"]}
    assert Decimal(by_id[accounts["rent"].id]["amount"]) == Decimal("400.000")
    assert Decimal(by_id[accounts["groceries"].id]["amount"]) == Decimal("100.000")
    assert Decimal(by_id[accounts["rent"].id]["percent_of_total"]) == Decimal("80.000")
    assert Decimal(by_id[accounts["groceries"].id]["percent_of_total"]) == Decimal("20.000")

    top = data["top_expense_accounts"]
    assert top[0]["account_id"] == accounts["rent"].id
    assert top[1]["account_id"] == accounts["groceries"].id


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversal_offsets_original_entry(client, db, unique):
    org, accounts = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=1)

    entry = await _post_entry(
        db,
        org.id,
        today,
        [
            {"account_id": accounts["rent"].id, "debit": Decimal("250.000")},
            {"account_id": accounts["bank"].id, "credit": Decimal("250.000")},
        ],
    )
    await db.commit()

    # Reverse the entry through the accounting service.
    service = AccountingService(db, org.id)
    await service.reverse_journal_entry(entry.id, reason="Mistake")
    await db.commit()

    response = await client.get(
        "/reports/expense-analysis",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert Decimal(data["total_expenses"]) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthenticated_requests_rejected(client):
    response = await client.get(
        "/reports/income-statement",
        params={
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
        },
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_invalid_date_range_rejected(client, db, unique):
    org, _ = await _setup_report_tenant(db, unique)
    user, password = await create_test_user(
        db, org, email=unique("owner") + "@example.com", role="owner"
    )
    headers = await auth_headers_for(client, user.email, password)

    today = date.today()
    response = await client.get(
        "/reports/income-statement",
        params={
            "start_date": (today + timedelta(days=5)).isoformat(),
            "end_date": today.isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_reports(client, db, unique):
    org_a, accounts_a = await _setup_report_tenant(db, unique)
    user_a, password_a = await create_test_user(
        db, org_a, email=unique("a") + "@example.com", role="owner"
    )

    org_b = await create_test_organization(
        db, name=unique("Org B"), slug=unique("org-b")
    )
    user_b, password_b = await create_test_user(
        db, org_b, email=unique("b") + "@example.com", role="owner"
    )

    today = date.today()
    await _post_entry(
        db,
        org_a.id,
        today,
        [
            {"account_id": accounts_a["rent"].id, "debit": Decimal("100.000")},
            {"account_id": accounts_a["bank"].id, "credit": Decimal("100.000")},
        ],
    )
    await db.commit()

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    response = await client.get(
        "/reports/expense-analysis",
        params={
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
        headers=headers_b,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert Decimal(data["total_expenses"]) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_journal_tables(db):
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
