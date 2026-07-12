"""Debt Optimizer integration tests.

These tests use synthetic loan data only and verify that the optimizer is
read-only, tenant-scoped, and produces deterministic projections.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.rls import set_tenant_context_async
from app.models import Account, JournalEntry, Loan, LoanType, RepaymentStrategy, User
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


async def _create_loan(
    db,
    tenant_context,
    tenant_id: int,
    name: str,
    balance: str,
    rate: str,
    minimum_payment: str | None = None,
    **kwargs,
):
    await tenant_context(tenant_id)
    loan = Loan(
        tenant_id=tenant_id,
        name=name,
        lender="Test Lender",
        loan_type=LoanType.PERSONAL,
        original_principal=Decimal(balance),
        current_balance=Decimal(balance),
        interest_rate=Decimal(rate),
        start_date=date.today(),
        minimum_payment=Decimal(minimum_payment) if minimum_payment else None,
        repayment_strategy=RepaymentStrategy.AVALANCHE,
        **kwargs,
    )
    db.add(loan)
    await db.commit()
    await db.refresh(loan)
    return loan


async def _count_journal_entries(db):
    result = await db.execute(select(func.count(JournalEntry.id)))
    return result.scalar()


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


@pytest.mark.integration
@pytest.mark.anyio
async def test_strategies_catalog_requires_auth(client):
    response = await client.get("/ai/debt-optimizer/strategies")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_strategies_catalog_returns_strategies(client, auth_headers):
    response = await client.get("/ai/debt-optimizer/strategies", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    types = {s["strategy_type"] for s in data["strategies"]}
    assert "avalanche" in types
    assert "snowball" in types
    assert "custom_order" in types


@pytest.mark.integration
@pytest.mark.anyio
async def test_avalanche_prioritizes_highest_interest(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    high = await _create_loan(db, tenant_context, user.organization_id, "High Rate", "1000.000", "0.2000", "100.000")
    low = await _create_loan(db, tenant_context, user.organization_id, "Low Rate", "1000.000", "0.0500", "100.000")

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "0.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order = data["payoff_order"]
    assert order[0]["id"] == high.id
    assert order[1]["id"] == low.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_snowball_prioritizes_smallest_balance(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    small = await _create_loan(db, tenant_context, user.organization_id, "Small", "500.000", "0.2000", "50.000")
    large = await _create_loan(db, tenant_context, user.organization_id, "Large", "2000.000", "0.0500", "50.000")

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "snowball", "extra_monthly_payment": "0.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order = data["payoff_order"]
    assert order[0]["id"] == small.id
    assert order[1]["id"] == large.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_extra_payment_reduces_payoff_time(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await _create_loan(db, tenant_context, user.organization_id, "Card", "1200.000", "0.1800", "100.000")

    baseline = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "0.000"},
        headers=auth_headers,
    )
    assert baseline.status_code == 200, baseline.text
    scenario = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "100.000"},
        headers=auth_headers,
    )
    assert scenario.status_code == 200, scenario.text

    base_data = baseline.json()["result"]
    scen_data = scenario.json()["result"]
    assert scen_data["payoff_months"] < base_data["payoff_months"]
    assert scen_data["months_saved"] > 0
    assert Decimal(scen_data["interest_saved"]) > Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_negative_extra_payment_rejected(client, auth_headers):
    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "-50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_payment_too_small_warning(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await _create_loan(db, tenant_context, user.organization_id, "Underwater", "1000.000", "0.2400", "10.000")

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "0.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    messages = {w["message"].lower() for w in data["warnings"]}
    assert any("minimum payment" in m and "interest" in m for m in messages)


@pytest.mark.integration
@pytest.mark.anyio
async def test_missing_interest_low_confidence(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    asset = await _create_account(client, auth_headers, "2200", "Cash", "Asset")
    await tenant_context(user.organization_id)
    account = Account(
        tenant_id=user.organization_id,
        code="LOAN_LIAB_01",
        name="Mystery Liability",
        account_type="Liability",
        visibility="private",
        owner_user_id=user.id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "1000.000"},
            {"account_id": account.id, "credit": "1000.000"},
        ],
        narration="Loan proceeds",
    )

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "account_ids": [account.id]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["confidence"] in ("low", "medium")
    descriptions = {a["description"].lower() for a in data["assumptions"]}
    assert any("interest rate" in d for d in descriptions)


@pytest.mark.integration
@pytest.mark.anyio
async def test_custom_order_strategy(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    first = await _create_loan(db, tenant_context, user.organization_id, "First", "2000.000", "0.0500", "50.000")
    second = await _create_loan(db, tenant_context, user.organization_id, "Second", "500.000", "0.2000", "50.000")

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={
            "strategy": "custom_order",
            "custom_order": [second.id, first.id],
            "extra_monthly_payment": "0.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order_ids = [d["id"] for d in data["payoff_order"]]
    assert order_ids == [second.id, first.id]


@pytest.mark.integration
@pytest.mark.anyio
async def test_deterministic_narrative_when_llm_disabled(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await _create_loan(db, tenant_context, user.organization_id, "Card", "1000.000", "0.1200", "100.000")

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={
            "strategy": "avalanche",
            "extra_monthly_payment": "0.000",
            "include_narrative": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    narrative = response.json()["result"]["narrative"]
    assert "Strategy:" in narrative
    assert "educational" in narrative.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_optimizer_does_not_create_transactions(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await _create_loan(db, tenant_context, user.organization_id, "ReadOnly", "800.000", "0.1000", "80.000")

    entries_before = await _count_journal_entries(db)
    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "extra_monthly_payment": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    entries_after = await _count_journal_entries(db)
    assert entries_before == entries_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_loan(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await set_tenant_context_async(db, org_b.id)
    loan_b = Loan(
        tenant_id=org_b.id,
        name="B Loan",
        lender="B Lender",
        loan_type=LoanType.PERSONAL,
        original_principal=Decimal("1000.000"),
        current_balance=Decimal("1000.000"),
        interest_rate=Decimal("0.1000"),
        start_date=date.today(),
        minimum_payment=Decimal("100.000"),
        repayment_strategy=RepaymentStrategy.AVALANCHE,
    )
    db.add(loan_b)
    await db.commit()
    await db.refresh(loan_b)

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "loan_ids": [loan_b.id]},
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_private_liability_account_rejected(client, db, unique, tenant_context):
    org = await create_test_organization(db, name=unique("Debt Org"), slug=unique("debt-org"))
    user_a, password_a = await create_test_user(db, org, email=unique("a") + "@example.com", role="viewer")
    user_b, password_b = await create_test_user(db, org, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await tenant_context(org.id)
    account = Account(
        tenant_id=org.id,
        code="PRIV_LIAB",
        name="Private Loan",
        account_type="Liability",
        visibility="private",
        owner_user_id=user_b.id,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "account_ids": [account.id]},
        headers=headers_a,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_compare_returns_strategies(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    await _create_loan(db, tenant_context, user.organization_id, "A", "1000.000", "0.1500", "100.000")
    await _create_loan(db, tenant_context, user.organization_id, "B", "600.000", "0.0800", "100.000")

    response = await client.post(
        "/ai/debt-optimizer/compare",
        json={"strategy": "avalanche", "extra_monthly_payment": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["results"]) == 2
    strategies = {r["strategy"] for r in data["results"]}
    assert "avalanche" in strategies
    assert "snowball" in strategies
    assert data["recommendation"]
    assert "guarantee" not in data["recommendation"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_debt_tables(db):
    await assert_rls_enabled(db, "loans")
    await assert_rls_enabled(db, "accounts")
