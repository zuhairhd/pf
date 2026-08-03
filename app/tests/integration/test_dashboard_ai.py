"""Dashboard v2 (AI-centric "Today" dashboard) tests (AI-1223).

Covers the /dashboard/api/today JSON API, the AI-centric dashboard page
sections, the HTMX "ai-today" partial, read-only/safety guarantees, and
tenant isolation. Uses synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Account, Bill, Goal, JournalEntry, Notification, Subscription
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
    unique,
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
        json={"date": date.today().isoformat(), "narration": narration, "lines": lines},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Dashboard API: /dashboard/api/today
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_requires_auth(client):
    response = await client.get("/dashboard/api/today")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_returns_expected_sections(client, auth_headers):
    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert "greeting" in data
    assert "today" in data
    assert "summary" in data
    assert "disclaimer" in data
    assert "alerts" in data
    assert "commitments" in data
    assert "goals" in data
    assert "insights" in data
    assert "suggested_actions" in data
    assert "suggested_questions" in data
    assert "quick_actions" in data
    assert len(data["suggested_questions"]) > 0
    assert len(data["quick_actions"]) >= 5


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_includes_confidence_fields(client, auth_headers):
    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["confidence_score"] is not None
    assert 0.0 <= data["confidence_score"] <= 1.0
    assert data["confidence_label"] in ("high", "medium", "low")
    assert isinstance(data["confidence_factors"], list)
    assert data["confidence_explanation"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_health_score_safe_when_no_data(client, auth_headers):
    """No accounts/transactions: health_score is present or null, never errors."""
    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    # Either a computed score dict or a safe null fallback.
    assert data["health_score"] is None or "overall_score" in data["health_score"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_empty_state(client, auth_headers):
    """With no bills, goals, or debts, the payload still renders safe empty sections."""
    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["alerts"], list)
    assert isinstance(data["insights"], list)
    assert data["goals"]["active_goals_count"] == 0
    assert data["commitments"]["overdue_bills_count"] == 0
    assert len(data["suggested_actions"]) > 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_shows_overdue_bill_alert(client, auth_headers):
    await client.post(
        "/bills",
        json={
            "name": "Old Bill",
            "provider": "Provider",
            "typical_amount": "10.000",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "frequency": "one-time",
        },
        headers=auth_headers,
    )

    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    overdue_alerts = [a for a in data["alerts"] if a["alert_type"] == "bill_overdue"]
    assert len(overdue_alerts) == 1
    assert overdue_alerts[0]["confidence_label"] == "high"
    assert data["commitments"]["overdue_bills_count"] == 1
    assert any("overdue" in action.lower() for action in data["suggested_actions"])


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_page_includes_ai_today_brief(client, auth_headers):
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "confidence" in response.text.lower()
    assert "Financial Health Snapshot" in response.text
    assert "Top Alerts" in response.text
    assert "AI Recommendations" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_page_includes_optimizer_quick_actions(client, auth_headers):
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "What-If Simulator" in response.text
    assert "Debt Optimizer" in response.text
    assert "Savings Optimizer" in response.text
    assert "Goal Planner" in response.text
    assert "Ask the AI Coach" in response.text or "AI Chat" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_page_still_includes_existing_widgets(client, auth_headers):
    """Regression: existing commitments and family goals widgets remain."""
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Bills & Subscriptions" in response.text
    assert "Upcoming Bills" in response.text
    assert "Family Goals" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_page_empty_state_renders(client, auth_headers):
    """A brand-new tenant with no goals/bills still renders the AI sections safely."""
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "No active family goals yet" in response.text
    assert "No upcoming bills for the next 7 days" in response.text


# ---------------------------------------------------------------------------
# HTMX partial: /dashboard/partials/ai-today
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_ai_today_partial_requires_auth(client):
    response = await client.get("/dashboard/partials/ai-today")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_ai_today_partial_renders(client, auth_headers):
    response = await client.get("/dashboard/partials/ai-today", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert 'id="ai-today-widget"' in response.text
    assert "Financial Health Snapshot" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_ai_today_partial_refresh_does_not_modify_records(client, auth_headers, db):
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)
    notifications_before = await count_rows(db, Notification)

    await client.get("/dashboard/partials/ai-today", headers=auth_headers)
    await client.get("/dashboard/partials/ai-today", headers=auth_headers)

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, JournalEntry) == journals_before
    assert await count_rows(db, Notification) == notifications_before


# ---------------------------------------------------------------------------
# Safety: read-only, LLM fallback, no raw account identifiers
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_view_creates_no_financial_records(client, auth_headers, db):
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)
    bills_before = await count_rows(db, Bill)
    subscriptions_before = await count_rows(db, Subscription)

    await client.get("/dashboard/", headers=auth_headers)
    await client.get("/dashboard/api/today", headers=auth_headers)

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, JournalEntry) == journals_before
    assert await count_rows(db, Bill) == bills_before
    assert await count_rows(db, Subscription) == subscriptions_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_view_creates_no_notifications(client, auth_headers, db):
    """Merely viewing the dashboard must not create notifications; that only
    happens via the explicit /ai/proactive-alerts/run endpoint."""
    notifications_before = await count_rows(db, Notification)

    await client.get("/dashboard/", headers=auth_headers)
    await client.get("/dashboard/api/today", headers=auth_headers)
    await client.get("/dashboard/partials/ai-today", headers=auth_headers)

    assert await count_rows(db, Notification) == notifications_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_works_without_openai_key(client, auth_headers):
    """Default test environment has no OPENAI_API_KEY; the endpoint must
    still succeed and fall back to a deterministic narrative."""
    response = await client.get(
        "/dashboard/api/today?include_narrative=true", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]
    factor_names = {f["name"] for f in data["confidence_factors"]}
    assert "llm_fallback" in factor_names


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_does_not_expose_account_codes(client, auth_headers):
    account = await _create_account(
        client, auth_headers, "9999888877776666", "Sensitive Account", "Asset"
    )

    response = await client.get("/dashboard/api/today", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "9999888877776666" not in response.text


# ---------------------------------------------------------------------------
# Tenant isolation / RLS
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_today_tenant_isolation(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await client.post(
        "/bills",
        json={
            "name": "Tenant A Overdue Bill",
            "provider": "Provider",
            "typical_amount": "10.000",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "frequency": "one-time",
        },
        headers=headers_a,
    )

    response_b = await client.get("/dashboard/api/today", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    data_b = response_b.json()
    assert data_b["commitments"]["overdue_bills_count"] == 0
    assert all(
        "Tenant A Overdue Bill" not in a["title"] and "Tenant A Overdue Bill" not in a["message"]
        for a in data_b["alerts"]
    )

    dashboard_b = await client.get("/dashboard/", headers=headers_b)
    assert "Tenant A Overdue Bill" not in dashboard_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_still_active_on_dashboard_dependencies(db):
    await assert_rls_enabled(db, "bills")
    await assert_rls_enabled(db, "subscriptions")
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "accounts")
