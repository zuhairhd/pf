"""Proactive AI alerts integration tests.

Tests the read-only alert engine that detects financial conditions and creates
in-app notifications. No real personal financial data is used.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai_cfo.engines.proactive_alerts import (
    ProactiveAlertType,
    ProactiveAlertsEngine,
)
from app.core.rls import set_tenant_context_async, clear_tenant_context_async
from app.models import (
    Bill,
    Goal,
    GoalStatus,
    JournalEntry,
    JournalLine,
    Loan,
    LoanType,
    Notification,
    Subscription,
)
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
    create_test_user,
    unique,
)


async def _owner_headers(client, db, tenant):
    user, password = await create_test_user(db, tenant, role="owner")
    await db.commit()
    return await auth_headers_for(client, user.email, password), user


async def _viewer_headers(client, db, tenant):
    user, password = await create_test_user(db, tenant, role="viewer")
    await db.commit()
    return await auth_headers_for(client, user.email, password), user


async def _create_bill(db, tenant_id, *, due_date, name=None, paid=False):
    bill = Bill(
        tenant_id=tenant_id,
        name=name or unique("Bill"),
        provider=unique("Provider"),
        typical_amount=Decimal("50.000"),
        due_date=due_date,
        is_paid=paid,
    )
    db.add(bill)
    await db.flush()
    await db.refresh(bill)
    return bill


async def _create_subscription(db, tenant_id, *, next_billing_date, name=None):
    sub = Subscription(
        tenant_id=tenant_id,
        name=name or unique("Subscription"),
        provider=unique("Provider"),
        amount=Decimal("15.000"),
        frequency="monthly",
        next_billing_date=next_billing_date,
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)
    return sub


async def _create_goal(db, tenant_id, *, target_amount, current_amount, monthly_contribution, target_date, name=None):
    goal = Goal(
        tenant_id=tenant_id,
        name=name or unique("Goal"),
        target_amount=target_amount,
        current_amount=current_amount,
        monthly_contribution=monthly_contribution,
        target_date=target_date,
        status=GoalStatus.ACTIVE,
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


async def _create_loan(db, tenant_id, *, balance, rate, minimum_payment, name=None):
    loan = Loan(
        tenant_id=tenant_id,
        name=name or unique("Loan"),
        lender=unique("Lender"),
        loan_type=LoanType.PERSONAL,
        original_principal=balance,
        current_balance=balance,
        interest_rate=rate,
        start_date=date.today(),
        minimum_payment=minimum_payment,
    )
    db.add(loan)
    await db.flush()
    await db.refresh(loan)
    return loan


async def _post_income(db, tenant_id, amount, days_ago=0):
    asset = await create_test_account(db, tenant_id, account_type="Asset", name=unique("Bank"))
    income = await create_test_account(db, tenant_id, account_type="Income", name=unique("Salary"))
    entry = JournalEntry(
        tenant_id=tenant_id,
        date=date.today() - timedelta(days=days_ago),
        reference=unique("ref"),
        narration=unique("Income"),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    db.add_all([
        JournalLine(tenant_id=tenant_id, journal_entry_id=entry.id, account_id=asset.id, debit=amount),
        JournalLine(tenant_id=tenant_id, journal_entry_id=entry.id, account_id=income.id, credit=amount),
    ])
    await db.flush()
    return entry


async def _post_expense(db, tenant_id, amount, days_ago=0):
    asset = await create_test_account(db, tenant_id, account_type="Asset", name=unique("Bank"))
    expense = await create_test_account(db, tenant_id, account_type="Expense", name=unique("Expense"))
    entry = JournalEntry(
        tenant_id=tenant_id,
        date=date.today() - timedelta(days=days_ago),
        reference=unique("ref"),
        narration=unique("Expense"),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    db.add_all([
        JournalLine(tenant_id=tenant_id, journal_entry_id=entry.id, account_id=expense.id, debit=amount),
        JournalLine(tenant_id=tenant_id, journal_entry_id=entry.id, account_id=asset.id, credit=amount),
    ])
    await db.flush()
    return entry


async def _count_notifications(db, tenant_id, user_id):
    result = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == tenant_id)
        .where(Notification.user_id == user_id)
    )
    return len(result.scalars().all())


@pytest.mark.integration
@pytest.mark.anyio
async def test_alert_types_requires_auth(client):
    response = await client.get("/ai/proactive-alerts/types")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_alert_types_returns_supported_types(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, _ = await _owner_headers(client, db, tenant)
    response = await client.get("/ai/proactive-alerts/types", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    types = {a["alert_type"] for a in data["alert_types"]}
    assert ProactiveAlertType.BILL_DUE_SOON.value in types
    assert ProactiveAlertType.BILL_OVERDUE.value in types
    assert ProactiveAlertType.SUBSCRIPTION_RENEWAL_SOON.value in types
    assert ProactiveAlertType.HIGH_SPENDING_ANOMALY.value in types
    assert ProactiveAlertType.NEGATIVE_CASH_FLOW.value in types
    assert ProactiveAlertType.LOW_EMERGENCY_FUND.value in types
    assert ProactiveAlertType.GOAL_DEADLINE_RISK.value in types
    assert ProactiveAlertType.DEBT_PRESSURE.value in types
    assert "thresholds" in data


@pytest.mark.integration
@pytest.mark.anyio
async def test_preview_returns_candidates_without_notifications(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    await _create_subscription(db, tenant.id, next_billing_date=date.today() + timedelta(days=2))
    await db.commit()

    before = await _count_notifications(db, tenant.id, user.id)
    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["candidates"]) >= 2
    after = await _count_notifications(db, tenant.id, user.id)
    assert after == before


@pytest.mark.integration
@pytest.mark.anyio
async def test_run_requires_admin_or_owner(client, db, tenant):
    viewer_headers, _ = await _viewer_headers(client, db, tenant)
    response = await client.post("/ai/proactive-alerts/run", headers=viewer_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_run_creates_notifications(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    await _create_subscription(db, tenant.id, next_billing_date=date.today() + timedelta(days=2))
    await db.commit()

    response = await client.post("/ai/proactive-alerts/run", json={}, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["created"] >= 2
    assert data["candidates"] >= 2

    notifications = await _count_notifications(db, tenant.id, user.id)
    assert notifications >= 2


@pytest.mark.integration
@pytest.mark.anyio
async def test_duplicate_run_skips_notifications(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    bill = await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    await db.commit()

    first = await client.post("/ai/proactive-alerts/run", json={}, headers=headers)
    assert first.status_code == 200
    assert first.json()["created"] >= 1

    second = await client.post("/ai/proactive-alerts/run", json={}, headers=headers)
    assert second.status_code == 200
    assert second.json()["skipped"] >= 1

    bill_notifications = [
        n for n in
        (await db.execute(
            select(Notification)
            .where(Notification.tenant_id == tenant.id)
            .where(Notification.user_id == user.id)
            .where(Notification.related_entity_type == "bill")
            .where(Notification.related_entity_id == bill.id)
        )).scalars().all()
    ]
    assert len(bill_notifications) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_bill_due_soon_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    bill = await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    due_soon = [c for c in candidates if c["alert_type"] == ProactiveAlertType.BILL_DUE_SOON.value]
    assert len(due_soon) == 1
    assert bill.name in due_soon[0]["title"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_bill_overdue_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_bill(db, tenant.id, due_date=date.today() - timedelta(days=2))
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    overdue = [c for c in candidates if c["alert_type"] == ProactiveAlertType.BILL_OVERDUE.value]
    assert len(overdue) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_subscription_renewal_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_subscription(db, tenant.id, next_billing_date=date.today() + timedelta(days=2))
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    renewal = [c for c in candidates if c["alert_type"] == ProactiveAlertType.SUBSCRIPTION_RENEWAL_SOON.value]
    assert len(renewal) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_high_spending_anomaly_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    # Baseline 60 days: 100 OMR/month average.
    await _post_expense(db, tenant.id, Decimal("100.000"), days_ago=45)
    # Recent 30 days: 200 OMR -> 100% above baseline -> anomaly.
    await _post_expense(db, tenant.id, Decimal("200.000"), days_ago=5)
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    anomaly = [c for c in candidates if c["alert_type"] == ProactiveAlertType.HIGH_SPENDING_ANOMALY.value]
    assert len(anomaly) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_negative_cash_flow_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    # Income 100, expenses 200 -> negative net flow.
    await _post_income(db, tenant.id, Decimal("100.000"), days_ago=5)
    await _post_expense(db, tenant.id, Decimal("200.000"), days_ago=5)
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    cashflow = [c for c in candidates if c["alert_type"] == ProactiveAlertType.NEGATIVE_CASH_FLOW.value]
    assert len(cashflow) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_low_emergency_fund_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    # Expenses 1000/month, assets 500 -> 0.5 months -> alert.
    await _post_expense(db, tenant.id, Decimal("1000.000"), days_ago=5)
    await _post_income(db, tenant.id, Decimal("500.000"), days_ago=5)
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    emergency = [c for c in candidates if c["alert_type"] == ProactiveAlertType.LOW_EMERGENCY_FUND.value]
    assert len(emergency) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_deadline_risk_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_goal(
        db, tenant.id,
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("100.000"),
        monthly_contribution=Decimal("10.000"),
        target_date=date.today() + timedelta(days=60),
    )
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    goal_risk = [c for c in candidates if c["alert_type"] == ProactiveAlertType.GOAL_DEADLINE_RISK.value]
    assert len(goal_risk) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_debt_pressure_alert(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    # Loan balance 1000 at 24% with tiny minimum payment -> underwater.
    await _create_loan(
        db, tenant.id,
        balance=Decimal("1000.000"),
        rate=Decimal("0.2400"),
        minimum_payment=Decimal("10.000"),
    )
    # Income only 100/month -> high DTI.
    await _post_income(db, tenant.id, Decimal("100.000"), days_ago=5)
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    debt = [c for c in candidates if c["alert_type"] == ProactiveAlertType.DEBT_PRESSURE.value]
    assert len(debt) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_run_is_read_only(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    before_je = await db.scalar(select(JournalEntry.id).limit(1))
    count_before = len((await db.execute(select(Notification))).scalars().all())
    await db.commit()

    response = await client.post("/ai/proactive-alerts/run", json={}, headers=headers)
    assert response.status_code == 200
    await db.commit()

    # No new journal entries or transactions created.
    after_je = await db.scalar(select(JournalEntry.id).limit(1))
    assert after_je == before_je
    # Notifications were created.
    count_after = len((await db.execute(select(Notification))).scalars().all())
    assert count_after > count_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_llm_fallback_works_without_api_key(client, db, tenant, tenant_context):
    await tenant_context(tenant.id)
    headers, user = await _owner_headers(client, db, tenant)
    await _create_bill(db, tenant.id, due_date=date.today() + timedelta(days=1))
    await db.commit()

    response = await client.post(
        "/ai/proactive-alerts/run",
        json={"include_llm_wording": True},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_alerts_blocked(client, db, tenant_pair):
    tenant_a, tenant_b = tenant_pair
    headers_a, user_a = await _owner_headers(client, db, tenant_a)
    headers_b, user_b = await _owner_headers(client, db, tenant_b)

    # Create a bill in tenant B using tenant B context.
    await set_tenant_context_async(db, tenant_b.id)
    await _create_bill(db, tenant_b.id, due_date=date.today() + timedelta(days=1))
    await db.commit()

    # Tenant A preview should not see tenant B's bill.
    await clear_tenant_context_async(db)
    response_a = await client.post("/ai/proactive-alerts/preview", headers=headers_a)
    assert response_a.status_code == 200
    candidates_a = response_a.json()["candidates"]
    bill_ids_a = {
        c["related_entity_id"]
        for c in candidates_a
        if c["alert_type"] == ProactiveAlertType.BILL_DUE_SOON.value
    }

    await set_tenant_context_async(db, tenant_b.id)
    engine_b = ProactiveAlertsEngine(db, tenant_b.id, user=user_b)
    b_candidates = await engine_b.preview()
    await clear_tenant_context_async(db)

    b_bill_ids = {
        c.related_entity_id
        for c in b_candidates
        if c.alert_type == ProactiveAlertType.BILL_DUE_SOON
    }
    assert len(b_bill_ids) >= 1
    assert not b_bill_ids.intersection(bill_ids_a)


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_remains_active(db):
    await assert_rls_enabled(db, "notifications")
