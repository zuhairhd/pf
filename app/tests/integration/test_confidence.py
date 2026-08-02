"""AI Confidence Scoring tests (AI-1222).

Covers the standalone confidence utility, and its integration into the
What-If simulator, Debt Optimizer, Savings Optimizer, Goal Planner,
Proactive Alerts, and AI Chat. All engine tests use synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ai_cfo.confidence import (
    ALL_FACTORS,
    ConfidenceLabel,
    ConfidenceScorer,
    calculate_confidence_score,
    confidence_rules,
    label_from_score,
)
from app.models import Account, Bill, Goal, GoalStatus, JournalEntry, Loan, LoanType
from app.tests.helpers import count_rows, unique


# ---------------------------------------------------------------------------
# Local fixtures/helpers
# ---------------------------------------------------------------------------


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
        json={"date": date.today().isoformat(), "narration": narration, "lines": lines},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Confidence utility (unit-level, no DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_label_thresholds():
    assert label_from_score(0.75) == ConfidenceLabel.HIGH
    assert label_from_score(0.90) == ConfidenceLabel.HIGH
    assert label_from_score(0.74) == ConfidenceLabel.MEDIUM
    assert label_from_score(0.45) == ConfidenceLabel.MEDIUM
    assert label_from_score(0.44) == ConfidenceLabel.LOW
    assert label_from_score(0.0) == ConfidenceLabel.LOW


@pytest.mark.unit
def test_score_stays_within_bounds_with_many_negative_factors():
    score = calculate_confidence_score(list(ALL_FACTORS.keys()) * 3)
    assert 0.0 <= score.score <= 1.0


@pytest.mark.unit
def test_score_stays_within_bounds_with_no_factors():
    score = calculate_confidence_score([])
    assert 0.0 <= score.score <= 1.0
    assert score.label == ConfidenceLabel.MEDIUM


@pytest.mark.unit
def test_factors_combine_additively():
    only_positive = calculate_confidence_score(["deterministic_calculation"])
    with_negative = calculate_confidence_score(["deterministic_calculation", "llm_fallback"])
    assert with_negative.score < only_positive.score


@pytest.mark.unit
def test_unknown_factor_names_are_ignored():
    score = calculate_confidence_score(["not_a_real_factor"])
    assert score.score == calculate_confidence_score([]).score


@pytest.mark.unit
def test_explanation_is_generated_and_mentions_label():
    score = calculate_confidence_score(["deterministic_calculation", "llm_fallback"])
    assert score.explanation
    assert score.label.value.capitalize() in score.explanation


@pytest.mark.unit
def test_confidence_scorer_builder():
    score = (
        ConfidenceScorer()
        .add("deterministic_calculation")
        .add_if(False, "llm_fallback")
        .add_if(True, "sufficient_history")
        .build()
    )
    names = {f.name for f in score.factors}
    assert names == {"deterministic_calculation", "sufficient_history"}


@pytest.mark.unit
def test_confidence_rules_shape():
    rules = confidence_rules()
    assert rules["thresholds"]["high"] == 0.75
    assert rules["thresholds"]["medium"] == 0.45
    assert set(rules["labels"]) == {"high", "medium", "low"}
    assert len(rules["positive_factors"]) > 0
    assert len(rules["negative_factors"]) > 0


# ---------------------------------------------------------------------------
# API: /ai/confidence/rules
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_confidence_rules_requires_auth(client):
    response = await client.get("/ai/confidence/rules")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_confidence_rules_returns_thresholds(client, auth_headers):
    response = await client.get("/ai/confidence/rules", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["thresholds"]["high"] == 0.75
    assert data["thresholds"]["medium"] == 0.45
    assert "high" in data["labels"]
    assert any(f["name"] == "deterministic_calculation" for f in data["positive_factors"])
    assert any(f["name"] == "llm_fallback" for f in data["negative_factors"])


# ---------------------------------------------------------------------------
# What-If Simulator
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_whatif_response_includes_confidence_fields(client, auth_headers, db):
    asset = await _create_account(client, auth_headers, "2900", "Savings", "Asset")
    income = await _create_account(client, auth_headers, "4900", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "5900", "Groceries", "Expense")
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
            {"account_id": expense["id"], "debit": "200.000"},
            {"account_id": asset["id"], "credit": "200.000"},
        ],
    )

    response = await client.post(
        "/ai/what-if/simulate",
        json={"scenario_type": "increase_monthly_savings", "monthly_extra_savings": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["confidence_score"] is not None
    assert 0.0 <= result["confidence_score"] <= 1.0
    assert result["confidence_label"] in ("high", "medium", "low")
    assert result["confidence_label"] == result["confidence"]
    assert len(result["confidence_factors"]) > 0
    assert result["confidence_explanation"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_whatif_no_history_is_low_confidence(client, auth_headers):
    response = await client.post(
        "/ai/what-if/simulate",
        json={"scenario_type": "increase_monthly_savings", "monthly_extra_savings": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["confidence_label"] == "low"
    factor_names = {f["name"] for f in result["confidence_factors"]}
    assert "low_transaction_history" in factor_names


# ---------------------------------------------------------------------------
# Debt Optimizer
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_debt_optimizer_missing_rate_and_minimum_lowers_confidence(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    asset = await _create_account(client, auth_headers, "2930", "Cash", "Asset")
    await tenant_context(user.organization_id)
    account = Account(
        tenant_id=user.organization_id,
        code="LIAB_CONF_01",
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
    result = response.json()["result"]
    assert result["confidence_label"] in ("low", "medium")
    factor_names = {f["name"] for f in result["confidence_factors"]}
    assert "missing_interest_rate" in factor_names
    assert "missing_minimum_payment" in factor_names


@pytest.mark.integration
@pytest.mark.anyio
async def test_debt_optimizer_full_data_is_higher_confidence(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await tenant_context(user.organization_id)
    loan = Loan(
        tenant_id=user.organization_id,
        name="Car Loan",
        lender="Test Lender",
        loan_type=LoanType.AUTO,
        original_principal=Decimal("5000.000"),
        current_balance=Decimal("5000.000"),
        interest_rate=Decimal("0.05"),
        minimum_payment=Decimal("150.000"),
        start_date=date.today(),
    )
    db.add(loan)
    await db.commit()
    await db.refresh(loan)

    response = await client.post(
        "/ai/debt-optimizer/simulate",
        json={"strategy": "avalanche", "loan_ids": [loan.id]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["confidence_label"] == "high"
    assert result["confidence_score"] >= 0.75


# ---------------------------------------------------------------------------
# Savings Optimizer
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_savings_optimizer_low_confidence_without_history(client, auth_headers):
    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={"mode": "savings_capacity"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["confidence_label"] == "low"


@pytest.mark.integration
@pytest.mark.anyio
async def test_savings_optimizer_high_confidence_with_full_history(client, auth_headers):
    asset = await _create_account(client, auth_headers, "2910", "Savings", "Asset")
    income = await _create_account(client, auth_headers, "4910", "Salary", "Income")
    expense = await _create_account(client, auth_headers, "5910", "Groceries", "Expense")
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": asset["id"], "debit": "2000.000"},
            {"account_id": income["id"], "credit": "2000.000"},
        ],
    )
    await _post_journal_entry(
        client,
        auth_headers,
        [
            {"account_id": expense["id"], "debit": "500.000"},
            {"account_id": asset["id"], "credit": "500.000"},
        ],
    )

    response = await client.post(
        "/ai/savings-optimizer/simulate",
        json={"mode": "savings_capacity"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["confidence_label"] == "high"


# ---------------------------------------------------------------------------
# Goal Planner
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_planner_missing_target_date_lowers_confidence(client, auth_headers):
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "hypothetical_goal",
            "target_amount": "1000.000",
            "goal_name": "No deadline goal",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    factor_names = {f["name"] for f in result["confidence_factors"]}
    assert "incomplete_goal_data" in factor_names


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_planner_single_goal_confidence_present(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    await tenant_context(user.organization_id)
    goal = Goal(
        tenant_id=user.organization_id,
        name=unique("Goal"),
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("0.000"),
        visibility="private",
        owner_user_id=user.id,
        status=GoalStatus.ACTIVE.value,
        target_date=None,
        priority=1,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/goal-planner/plan",
        json={"mode": "single_goal_feasibility", "goal_id": goal.id},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    goal_data = result["goal"]
    assert goal_data["confidence_label"] is not None
    factor_names = {f["name"] for f in goal_data["confidence_factors"]}
    assert "incomplete_goal_data" in factor_names


# ---------------------------------------------------------------------------
# Proactive Alerts
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_overdue_bill_alert_is_high_confidence(client, db, tenant, tenant_context):
    from app.tests.helpers import auth_headers_for, create_test_user

    await tenant_context(tenant.id)
    user, password = await create_test_user(db, tenant, role="owner")
    await db.commit()
    headers = await auth_headers_for(client, user.email, password)

    bill = Bill(
        tenant_id=tenant.id,
        name=unique("Bill"),
        provider=unique("Provider"),
        typical_amount=Decimal("50.000"),
        due_date=date.today() - timedelta(days=2),
        is_paid=False,
    )
    db.add(bill)
    await db.commit()

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]
    overdue = [c for c in candidates if c["alert_type"] == "bill_overdue"]
    assert len(overdue) == 1
    assert overdue[0]["confidence_label"] == "high"
    assert overdue[0]["confidence_score"] >= 0.75


@pytest.mark.integration
@pytest.mark.anyio
async def test_spending_anomaly_alert_is_medium_confidence(
    client, db, tenant, tenant_context
):
    from app.tests.helpers import auth_headers_for, create_test_user

    await tenant_context(tenant.id)
    user, password = await create_test_user(db, tenant, role="owner")
    await db.commit()
    headers = await auth_headers_for(client, user.email, password)

    asset = await _create_account(client, headers, "2920", "Cash", "Asset")
    expense = await _create_account(client, headers, "5920", "Shopping", "Expense")

    # Baseline (30-90 days ago): modest spending.
    old_entry_date = (date.today() - timedelta(days=60)).isoformat()
    await client.post(
        "/transactions/",
        json={
            "date": old_entry_date,
            "narration": "Baseline spending",
            "lines": [
                {"account_id": expense["id"], "debit": "50.000"},
                {"account_id": asset["id"], "credit": "50.000"},
            ],
        },
        headers=headers,
    )
    # Recent (last 30 days): much higher spending to trigger the anomaly.
    await _post_journal_entry(
        client,
        headers,
        [
            {"account_id": expense["id"], "debit": "500.000"},
            {"account_id": asset["id"], "credit": "500.000"},
        ],
        narration="Recent high spending",
    )

    response = await client.post("/ai/proactive-alerts/preview", headers=headers)
    assert response.status_code == 200, response.text
    candidates = response.json()["candidates"]
    anomaly = [c for c in candidates if c["alert_type"] == "high_spending_anomaly"]
    if anomaly:
        assert anomaly[0]["confidence_label"] == "medium"
        factor_names = {f["name"] for f in anomaly[0]["confidence_factors"]}
        assert "low_transaction_history" in factor_names


# ---------------------------------------------------------------------------
# AI Chat
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_remember_command_is_high_confidence(client, auth_headers):
    response = await client.post(
        "/ai/chat",
        json={"message": "Remember that I prefer conservative savings guidance"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["confidence_label"] == "high"
    factor_names = {f["name"] for f in data["confidence_factors"]}
    assert "no_llm_dependency" in factor_names


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_freeform_message_reflects_llm_fallback(client, auth_headers):
    """Without a configured OpenAI key, chat falls back to a deterministic
    rule-based response; the fallback factor must appear in confidence."""
    response = await client.post(
        "/ai/chat",
        json={"message": "Can you help me build a budget?"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["confidence_label"] in ("high", "medium", "low")
    factor_names = {f["name"] for f in data["confidence_factors"]}
    assert "llm_fallback" in factor_names


# ---------------------------------------------------------------------------
# Safety: no leakage, no financial record mutation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_confidence_factor_explanations_match_registry(client, auth_headers):
    """Confidence factor explanations must come from the static factor
    registry, never from dynamic/user/memory content."""
    response = await client.post(
        "/ai/what-if/simulate",
        json={"scenario_type": "increase_monthly_savings", "monthly_extra_savings": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    known_explanations = {f.explanation for f in ALL_FACTORS.values()}
    for factor in result["confidence_factors"]:
        assert factor["explanation"] in known_explanations


@pytest.mark.integration
@pytest.mark.anyio
async def test_confidence_endpoints_do_not_modify_financial_records(client, auth_headers, db):
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)

    await client.get("/ai/confidence/rules", headers=auth_headers)
    await client.post(
        "/ai/what-if/simulate",
        json={"scenario_type": "increase_monthly_savings", "monthly_extra_savings": "50.000"},
        headers=auth_headers,
    )
    await client.post("/ai/proactive-alerts/preview", headers=auth_headers)

    accounts_after = await count_rows(db, Account)
    goals_after = await count_rows(db, Goal)
    journals_after = await count_rows(db, JournalEntry)

    assert accounts_after == accounts_before
    assert goals_after == goals_before
    assert journals_after == journals_before
