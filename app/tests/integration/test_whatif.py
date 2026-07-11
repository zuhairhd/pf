"""What-If simulator integration tests.

These tests use synthetic data only and verify that the simulator is read-only,
tenant-scoped, and produces deterministic projections.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.rls import set_tenant_context_async
from app.models import Account, Goal, GoalStatus, GoalVisibility, JournalEntry, Subscription
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


@pytest.mark.integration
@pytest.mark.anyio
async def test_scenarios_catalog_requires_auth(client):
    response = await client.get("/ai/what-if/scenarios")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_scenarios_catalog_returns_supported_scenarios(client, auth_headers):
    response = await client.get("/ai/what-if/scenarios", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    types = {s["scenario_type"] for s in data["scenarios"]}
    assert "increase_monthly_savings" in types
    assert "reduce_expense_category" in types
    assert "income_increase" in types
    assert "emergency_expense" in types
    assert "cancel_subscription" in types
    assert "goal_contribution_increase" in types
    assert "new_monthly_payment" in types


@pytest.mark.integration
@pytest.mark.anyio
async def test_increase_savings_scenario(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "2100", "Savings", "Asset")
    income = await _create_account(client, auth_headers, "4100", "Salary", "Income")
    # Average monthly income over last 90 days = 1000 / 3 = 333.33
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": income["id"], "credit": "1000.000"},
        ],
    )

    entries_before = await _count_journal_entries(db)

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 6,
            "monthly_extra_savings": "50.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "300.000"
    assert Decimal(data["scenario_monthly_net_flow"]) == Decimal(data["baseline_monthly_net_flow"]) + Decimal("50")
    assert Decimal(data["ending_balance_scenario"]) == Decimal(data["ending_balance_baseline"]) + Decimal("300")
    assert "educational" in response.json().get("disclaimer", "").lower()

    entries_after = await _count_journal_entries(db)
    assert entries_before == entries_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_reduce_expense_scenario(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "2110", "Bank", "Asset")
    expense = await _create_account(client, auth_headers, "5100", "Dining", "Expense")
    # Monthly expense average = 600 / 3 = 200
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "600.000"},
            {"account_id": asset["id"], "credit": "600.000"},
        ],
    )

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "reduce_expense_category",
            "months": 12,
            "monthly_reduction_amount": "30.000",
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "360.000"
    assert Decimal(data["scenario_monthly_net_flow"]) == Decimal(data["baseline_monthly_net_flow"]) + Decimal("30")


@pytest.mark.integration
@pytest.mark.anyio
async def test_income_increase_scenario(client, auth_headers):
    asset = await _create_account(client, auth_headers, "2120", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "4200", "Bonus", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "900.000"},
            {"account_id": income["id"], "credit": "900.000"},
        ],
    )

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "income_increase",
            "months": 6,
            "monthly_income_increase": "100.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "600.000"
    assert data["impact_metrics"]["monthly_income_increase"] == "100.000"


@pytest.mark.integration
@pytest.mark.anyio
async def test_emergency_expense_scenario_flags_risk(client, auth_headers):
    asset = await _create_account(client, auth_headers, "2130", "Checking", "Asset")
    income = await _create_account(client, auth_headers, "4300", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "500.000"},
            {"account_id": income["id"], "credit": "500.000"},
        ],
    )

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "emergency_expense",
            "months": 6,
            "amount": "750.000",
            "month_number": 1,
            "source_account_id": asset["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "-750.000"
    messages = {w["message"] for w in data["warnings"]}
    assert any("source account balance" in m.lower() or "negative balance" in m.lower() for m in messages)


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_subscription_scenario(client, auth_headers):
    response = await client.post(
        "/subscriptions",
        json={
            "name": "Streaming",
            "provider": "Netflix",
            "amount": "15.000",
            "frequency": "monthly",
            "next_billing_date": date.today().isoformat(),
            "category": "entertainment",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    subscription_id = response.json()["id"]

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "cancel_subscription",
            "months": 12,
            "subscription_id": subscription_id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "180.000"
    assert data["impact_metrics"]["subscription_monthly_amount"] == "15.000"


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_contribution_scenario(client, db, auth_headers, tenant_context, test_user_credentials):
    # Create a private goal directly for the same tenant as the authenticated user.
    # The test user is treated as head for its own tenant.
    user = test_user_credentials["user"]
    await tenant_context(user.organization_id)
    goal = Goal(
        tenant_id=user.organization_id,
        name="Vacation",
        target_amount=Decimal("1200.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("100.000"),
        visibility=GoalVisibility.PRIVATE.value,
        owner_user_id=user.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "goal_contribution_increase",
            "months": 6,
            "goal_id": goal.id,
            "monthly_extra_contribution": "50.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["impact_metrics"]["current_monthly_contribution"] == "100.000"
    assert data["impact_metrics"]["new_monthly_contribution"] == "150.000"
    assert data["impact_metrics"]["months_saved"] == "4.00"


@pytest.mark.integration
@pytest.mark.anyio
async def test_new_monthly_payment_affordability_warning(client, auth_headers):
    asset = await _create_account(client, auth_headers, "2140", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "4400", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "5400", "Utilities", "Expense")
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
        "/ai/what-if/simulate",
        json={
            "scenario_type": "new_monthly_payment",
            "months": 6,
            "down_payment": "200.000",
            "monthly_payment": "300.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["total_impact"] == "-2000.000"
    messages = {w["message"] for w in data["warnings"]}
    assert any("emergency reserve" in m.lower() or "negative balance" in m.lower() for m in messages)


@pytest.mark.integration
@pytest.mark.anyio
async def test_unsupported_scenario_rejected(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={"scenario_type": "win_the_lottery", "months": 12},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_invalid_months_rejected(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 0,
            "monthly_extra_savings": "50.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_negative_amount_rejected(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 6,
            "monthly_extra_savings": "-50.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_simulation_does_not_create_transactions(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "2150", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "4500", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "300.000"},
            {"account_id": income["id"], "credit": "300.000"},
        ],
    )

    entries_before = await _count_journal_entries(db)
    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 3,
            "monthly_extra_savings": "10.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    entries_after = await _count_journal_entries(db)
    assert entries_before == entries_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_llm_fallback_without_api_key(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 3,
            "monthly_extra_savings": "10.000",
            "include_narrative": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    narrative = response.json()["result"]["narrative"]
    assert "Scenario:" in narrative
    assert "educational" in narrative.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_disclaimer_present(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "increase_monthly_savings",
            "months": 3,
            "monthly_extra_savings": "10.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "educational" in response.json()["disclaimer"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_account(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    account_b = await _create_account(client, headers_b, "9001", "B Account", "Asset")

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "emergency_expense",
            "months": 6,
            "amount": "100.000",
            "source_account_id": account_b["id"],
        },
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_subscription(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    sub_b = await client.post(
        "/subscriptions",
        json={
            "name": "B Service",
            "provider": "Provider",
            "amount": "20.000",
            "frequency": "monthly",
            "next_billing_date": date.today().isoformat(),
        },
        headers=headers_b,
    )
    assert sub_b.status_code == 200, sub_b.text
    sub_id = sub_b.json()["id"]

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "cancel_subscription",
            "months": 6,
            "subscription_id": sub_id,
        },
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_private_goal_rejected(client, db, unique, tenant_context):
    org = await create_test_organization(db, name=unique("Private Goal Org"), slug=unique("private-goal-org"))
    user_a, password_a = await create_test_user(db, org, email=unique("a") + "@example.com", role="viewer")
    user_b, password_b = await create_test_user(db, org, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await tenant_context(org.id)
    goal = Goal(
        tenant_id=org.id,
        name="Private Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("50.000"),
        visibility=GoalVisibility.PRIVATE.value,
        owner_user_id=user_b.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/what-if/simulate",
        json={
            "scenario_type": "goal_contribution_increase",
            "months": 6,
            "goal_id": goal.id,
            "monthly_extra_contribution": "25.000",
        },
        headers=headers_a,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_compare_scenarios(client, auth_headers):
    asset = await _create_account(client, auth_headers, "2160", "Bank", "Asset")
    income = await _create_account(client, auth_headers, "4600", "Salary", "Income")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "600.000"},
            {"account_id": income["id"], "credit": "600.000"},
        ],
    )

    response = await client.post(
        "/ai/what-if/compare",
        json={
            "scenarios": [
                {
                    "scenario_type": "increase_monthly_savings",
                    "months": 3,
                    "monthly_extra_savings": "100.000",
                },
                {
                    "scenario_type": "income_increase",
                    "months": 3,
                    "monthly_income_increase": "50.000",
                },
            ]
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["results"]) == 2
    assert "best_ending_balance_scenario" in data["summary"]
    assert "worst_ending_balance_scenario" in data["summary"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_tenant_tables(db):
    await assert_rls_enabled(db, "accounts")
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "subscriptions")
