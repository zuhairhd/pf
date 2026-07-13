"""Savings Optimizer integration tests.

These tests use synthetic data only and verify that the optimizer is read-only,
tenant-scoped, and produces deterministic savings projections.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.rls import set_tenant_context_async
from app.models import Account, Goal, GoalStatus, GoalVisibility, JournalEntry, User
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


async def _create_account(client, headers, code: str, name: str, account_type: str, **kwargs):
    response = await client.post(
        "/accounts/",
        json={"code": code, "name": name, "account_type": account_type, **kwargs},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _post_journal_entry(client, headers, lines: list[dict], narration: str = "Test entry"):
    response = await client.post(
        "/transactions/",
        json={
            "date": date.today().isoformat(),
            "narration": narration,
            "lines": lines,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _count_journal_entries(db):
    result = await db.execute(select(func.count(JournalEntry.id)))
    return result.scalar()


async def _create_goal(
    db,
    tenant_context,
    tenant_id: int,
    user_id: int,
    name: str,
    target: str,
    current: str = "0.000",
    monthly: str = "0.000",
    visibility: str = "private",
    target_date: date | None = None,
    priority: int = 1,
):
    await tenant_context(tenant_id)
    goal = Goal(
        tenant_id=tenant_id,
        name=name,
        target_amount=Decimal(target),
        current_amount=Decimal(current),
        monthly_contribution=Decimal(monthly),
        visibility=visibility,
        owner_user_id=user_id,
        status=GoalStatus.ACTIVE.value,
        target_date=target_date,
        priority=priority,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


@pytest.mark.integration
@pytest.mark.anyio
async def test_strategies_catalog_requires_auth(client):
    response = await client.get("/ai/savings-optimizer/strategies")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_strategies_catalog_returns_modes(client, auth_headers):
    response = await client.get("/ai/savings-optimizer/strategies", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    modes = {s["mode"] for s in data["strategies"]}
    assert "emergency_fund" in modes
    assert "savings_capacity" in modes
    assert "goal_allocation" in modes
    assert "reduce_spending" in modes
    assert "compare_strategies" in modes


@pytest.mark.integration
@pytest.mark.anyio
async def test_emergency_fund_calculates_target_gap_months(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6100", "Savings", "Asset")
    income = await _create_account(client, auth_headers, "7100", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "8100", "Rent", "Expense")

    # Asset balance = 1000, income = 1000, expenses = 600 (avg 200/month)
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "600.000"},
            {"account_id": asset["id"], "credit": "600.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "target_months_of_expenses": "3",
            "monthly_contribution": "100.000",
            "account_id": asset["id"],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["target_amount"] == "600.000"
    assert data["current_savings"] == "400.000"
    assert data["gap_amount"] == "200.000"
    assert data["months_to_target"] == 2
    assert data["risk_level"] == "medium"


@pytest.mark.integration
@pytest.mark.anyio
async def test_emergency_fund_warns_low_savings(client, auth_headers, db):
    expense = await _create_account(client, auth_headers, "8200", "Utilities", "Expense")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "900.000"},
            {"account_id": expense["id"], "credit": "900.000"},
        ],
        narration="Circular no-op to ensure account exists",
    )
    # Create an actual expense entry against an asset to generate expense average.
    asset = await _create_account(client, auth_headers, "6200", "Cash", "Asset")
    income = await _create_account(client, auth_headers, "7200", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "600.000"},
            {"account_id": asset["id"], "credit": "600.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "target_months_of_expenses": "3",
            "monthly_contribution": "50.000",
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["current_savings"] == "0.000"
    assert data["risk_level"] == "high"


@pytest.mark.integration
@pytest.mark.anyio
async def test_savings_capacity_calculates_rate_and_suggestions(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6300", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "7300", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "8300", "Bills", "Expense")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "3000.000"},
            {"account_id": income["id"], "credit": "3000.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "1800.000"},
            {"account_id": asset["id"], "credit": "1800.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "savings_capacity",
            "target_savings_rate": "50",
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["avg_monthly_income"] == "1000.000"
    assert data["avg_monthly_expenses"] == "600.000"
    assert data["avg_monthly_net_flow"] == "400.000"
    assert data["current_savings_rate_percent"] == "40.00"
    assert data["target_monthly_savings"] == "500.000"
    assert data["savings_gap"] == "100.000"
    assert Decimal(data["suggested_monthly_savings_min"]) >= Decimal("0")
    assert Decimal(data["suggested_monthly_savings_max"]) >= Decimal(data["suggested_monthly_savings_min"])


@pytest.mark.integration
@pytest.mark.anyio
async def test_savings_capacity_warns_negative_cash_flow(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6400", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "7400", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "8400", "Spending", "Expense")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "1800.000"},
            {"account_id": asset["id"], "credit": "1800.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={"mode": "savings_capacity", "months": 6},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert Decimal(data["avg_monthly_net_flow"]) < 0
    messages = {w["message"].lower() for w in data["warnings"]}
    assert any("expenses exceed income" in m for m in messages)


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_allocation_equal_split(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    g1 = await _create_goal(db, tenant_context, user.organization_id, user.id, "Vacation", "1000.000", "0.000", "0.000")
    g2 = await _create_goal(db, tenant_context, user.organization_id, user.id, "Car", "2000.000", "0.000", "0.000")

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "100.000",
            "strategy": "equal_split",
            "goal_ids": [g1.id, g2.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["strategy"] == "equal_split"
    assert data["total_allocated"] == "100.000"
    allocations = {a["goal_id"]: a["recommended_allocation"] for a in data["goals"]}
    assert Decimal(allocations[g1.id]) == Decimal("50.000")
    assert Decimal(allocations[g2.id]) == Decimal("50.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_allocation_priority_first(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    first = await _create_goal(db, tenant_context, user.organization_id, user.id, "First", "500.000", "0.000", "0.000", priority=1)
    second = await _create_goal(db, tenant_context, user.organization_id, user.id, "Second", "2000.000", "0.000", "0.000", priority=2)

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "100.000",
            "strategy": "priority_first",
            "goal_ids": [first.id, second.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    allocations = {a["goal_id"]: a["recommended_allocation"] for a in data["goals"]}
    assert Decimal(allocations[first.id]) == Decimal("100.000")
    assert Decimal(allocations[second.id]) == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_allocation_closest_deadline(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    soon = await _create_goal(
        db, tenant_context, user.organization_id, user.id, "Soon", "1000.000",
        target_date=date.today() + timedelta(days=30), priority=2
    )
    later = await _create_goal(
        db, tenant_context, user.organization_id, user.id, "Later", "1000.000",
        target_date=date.today() + timedelta(days=180), priority=1
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "100.000",
            "strategy": "closest_deadline",
            "goal_ids": [soon.id, later.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order = [a["goal_id"] for a in data["goals"]]
    assert order[0] == soon.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_allocation_unauthorized_private_goal_rejected(
    client, db, unique, tenant_context
):
    org = await create_test_organization(db, name=unique("Savings Org"), slug=unique("savings-org"))
    user_a, password_a = await create_test_user(db, org, email=unique("a") + "@example.com", role="viewer")
    user_b, password_b = await create_test_user(db, org, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await tenant_context(org.id)
    goal = Goal(
        tenant_id=org.id,
        name="Private Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("0.000"),
        visibility=GoalVisibility.PRIVATE.value,
        owner_user_id=user_b.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "50.000",
            "strategy": "equal_split",
            "goal_ids": [goal.id],
            "months": 6,
        },
        headers=headers_a,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_goal(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await set_tenant_context_async(db, org_b.id)
    goal_b = Goal(
        tenant_id=org_b.id,
        name="B Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("0.000"),
        visibility=GoalVisibility.SHARED.value,
        owner_user_id=user_b.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal_b)
    await db.commit()
    await db.refresh(goal_b)

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "50.000",
            "strategy": "equal_split",
            "goal_ids": [goal_b.id],
            "months": 6,
        },
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_account(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    account_b = await _create_account(client, headers_b, "9002", "B Savings", "Asset")

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "account_id": account_b["id"],
            "monthly_contribution": "50.000",
            "months": 6,
        },
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_private_account_rejected_for_emergency_fund(client, db, unique):
    org = await create_test_organization(db, name=unique("Private Acct Org"), slug=unique("private-acct-org"))
    user_a, password_a = await create_test_user(db, org, email=unique("a") + "@example.com", role="viewer")
    user_b, password_b = await create_test_user(db, org, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await set_tenant_context_async(db, org.id)
    account = Account(
        tenant_id=org.id,
        code="PRIV_SAV",
        name="Private Savings",
        account_type="Asset",
        visibility="private",
        owner_user_id=user_b.id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "account_id": account.id,
            "monthly_contribution": "50.000",
            "months": 6,
        },
        headers=headers_a,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_reduce_spending_calculates_required_reduction(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6500", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "7500", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "8500", "Dining", "Expense")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1500.000"},
            {"account_id": income["id"], "credit": "1500.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "900.000"},
            {"account_id": asset["id"], "credit": "900.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "reduce_spending",
            "target_monthly_savings": "300.000",
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["avg_monthly_income"] == "500.000"
    assert data["avg_monthly_expenses"] == "300.000"
    assert data["current_monthly_savings_capacity"] == "200.000"
    assert data["required_spending_reduction"] == "100.000"
    assert len(data["expense_reduction_candidates"]) >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_compare_strategies(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    g1 = await _create_goal(db, tenant_context, user.organization_id, user.id, "A", "500.000", priority=1)
    g2 = await _create_goal(db, tenant_context, user.organization_id, user.id, "B", "500.000", priority=2)

    response = await client.post(
        "/ai/savings-optimizer/compare",
        json={
            "mode": "compare_strategies",
            "monthly_available_savings": "100.000",
            "goal_ids": [g1.id, g2.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    strategies = {s["strategy"] for s in data["strategies"]}
    assert "equal_split" in strategies
    assert "priority_first" in strategies
    assert "closest_deadline" in strategies
    assert "lowest_gap_first" in strategies
    assert data["recommended_strategy"]
    assert data["recommendation"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_optimizer_does_not_create_transactions(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await _create_goal(db, tenant_context, user.organization_id, user.id, "ReadOnly", "800.000")

    entries_before = await _count_journal_entries(db)
    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "goal_allocation",
            "monthly_available_savings": "50.000",
            "strategy": "equal_split",
            "months": 3,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    entries_after = await _count_journal_entries(db)
    assert entries_before == entries_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_deterministic_narrative_without_api_key(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6600", "Cash", "Asset")
    income = await _create_account(client, auth_headers, "7600", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "target_months_of_expenses": "3",
            "monthly_contribution": "100.000",
            "account_id": asset["id"],
            "months": 6,
            "include_narrative": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    narrative = response.json()["result"]["narrative"]
    assert "Savings mode:" in narrative
    assert "educational" in narrative.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_disclaimer_present(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "6700", "Cash", "Asset")
    income = await _create_account(client, auth_headers, "7700", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={
            "mode": "emergency_fund",
            "target_months_of_expenses": "3",
            "monthly_contribution": "100.000",
            "account_id": asset["id"],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "educational" in response.json()["disclaimer"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_and_account_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "accounts")
