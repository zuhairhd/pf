"""Family Budget Dashboard Widget tests (DB-1106A).

Covers /dashboard/api/family-budgets, the /dashboard/partials/family-budgets
HTMX widget, permission-aware visibility, budget-vs-actual display, empty
states, read-only safety, and tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Account, Budget, Goal, JournalEntry, Notification
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
)


@pytest.fixture
def private_budget_payload():
    today = date.today()
    return {
        "name": "Personal Spending",
        "period": "monthly",
        "start_date": today.replace(day=1).isoformat(),
        "end_date": (today.replace(day=1) + timedelta(days=29)).isoformat(),
        "visibility": "private",
        "categories": [],
    }


@pytest.fixture
def shared_budget_payload():
    today = date.today()
    return {
        "name": "Household Budget",
        "period": "monthly",
        "start_date": today.replace(day=1).isoformat(),
        "end_date": (today.replace(day=1) + timedelta(days=29)).isoformat(),
        "visibility": "shared",
        "categories": [],
    }


async def _create_family(client, headers, name="Test Family"):
    response = await client.post("/family", json={"name": name, "currency": "OMR"}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _add_member(client, headers, user, role: str):
    payload = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "relationship_type": "other",
        "role": role,
        "user_id": user.id,
    }
    response = await client.post("/family/members", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    member = response.json()
    patch_response = await client.patch(
        f"/family/members/{member['id']}",
        json={"is_active": True},
        headers=headers,
    )
    assert patch_response.status_code == 200, patch_response.text
    return patch_response.json()


async def _create_budget(client, headers, payload):
    response = await client.post("/family/budgets", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _create_expense_account(client, headers, code: str, name: str):
    response = await client.post(
        "/accounts/",
        json={"code": code, "name": name, "account_type": "Expense"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _post_expense_journal_entry(client, headers, asset_id, expense_id, amount, entry_date):
    response = await client.post(
        "/transactions/",
        json={
            "date": entry_date.isoformat(),
            "narration": "Test expense",
            "lines": [
                {"account_id": expense_id, "debit": str(amount)},
                {"account_id": asset_id, "credit": str(amount)},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_api_requires_auth(client):
    response = await client.get("/dashboard/api/family-budgets")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_api_returns_expected_sections(client, auth_headers):
    response = await client.get("/dashboard/api/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    for key in (
        "budgets",
        "active_budgets_count",
        "total_planned",
        "total_actual",
        "total_remaining",
        "average_percent_used",
        "over_budget_count",
        "near_limit_count",
        "currency",
        "permissions",
    ):
        assert key in data


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_api_empty_state(client, auth_headers):
    response = await client.get("/dashboard/api/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["budgets"] == []
    assert data["active_budgets_count"] == 0
    assert data["over_budget_count"] == 0
    assert data["near_limit_count"] == 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_api_planned_actual_remaining_percent(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1200", "name": "Cash", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5200", "Dining")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Dining", "account_id": expense["id"], "budgeted_amount": "100.000"},
        headers=auth_headers,
    )
    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=5)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "40.000", mid_period)

    response = await client.get("/dashboard/api/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    item = next(b for b in data["budgets"] if b["id"] == budget["id"])
    assert Decimal(item["total_planned"]) == Decimal("100.000")
    assert Decimal(item["total_actual"]) == Decimal("40.000")
    assert Decimal(item["total_remaining"]) == Decimal("60.000")
    assert Decimal(item["percent_used"]) == Decimal("40.00")
    assert item["categories"][0]["planned_amount"] == "100.000"
    assert data["active_budgets_count"] == 1


# ---------------------------------------------------------------------------
# Dashboard partial (HTMX)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_partial_requires_auth(client):
    response = await client.get("/dashboard/partials/family-budgets")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_widget_renders_on_page(client, auth_headers):
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Family Budgets" in response.text
    # Existing sections must still render.
    assert "Bills & Subscriptions" in response.text
    assert "Family Goals" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_widget_empty_state(client, auth_headers):
    response = await client.get("/dashboard/partials/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "No budgets" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_widget_shows_progress_and_badges(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1300", "name": "Cash2", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5300", "Overspent")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Overspent", "account_id": expense["id"], "budgeted_amount": "50.000"},
        headers=auth_headers,
    )
    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=3)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "75.000", mid_period)

    response = await client.get("/dashboard/partials/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "progress-bar" in response.text
    assert "Over budget" in response.text
    assert budget["name"] in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budgets_widget_shows_near_limit(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1400", "name": "Cash3", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5400", "NearLimit")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "NearLimit", "account_id": expense["id"], "budgeted_amount": "100.000", "alert_threshold": "80"},
        headers=auth_headers,
    )
    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=3)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "85.000", mid_period)

    response = await client.get("/dashboard/partials/family-budgets", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Near limit" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_budget_categories_partial(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)
    expense = await _create_expense_account(client, auth_headers, "5450", "Groceries")
    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Groceries", "account_id": expense["id"], "budgeted_amount": "150.000"},
        headers=auth_headers,
    )

    response = await client.get(
        f"/dashboard/partials/family-budgets/{budget['id']}/categories", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert "Groceries" in response.text


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_sees_all_family_budgets(client, db, unique, private_budget_payload, shared_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    shared = await _create_budget(client, head_headers, shared_budget_payload)
    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    private = await _create_budget(client, adult_headers, private_budget_payload)

    response = await client.get("/dashboard/api/family-budgets", headers=head_headers)
    assert response.status_code == 200, response.text
    ids = {b["id"] for b in response.json()["budgets"]}
    assert shared["id"] in ids
    assert private["id"] in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_sees_shared_family_and_own_private_only(
    client, db, unique, private_budget_payload, shared_budget_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult_a, adult_a_password = await create_test_user(
        db, org, email=unique("adult_a") + "@example.com", role="viewer"
    )
    adult_b, adult_b_password = await create_test_user(
        db, org, email=unique("adult_b") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult_a, "adult")
    await _add_member(client, head_headers, adult_b, "adult")

    shared = await _create_budget(client, head_headers, shared_budget_payload)

    adult_a_headers = await auth_headers_for(client, adult_a.email, adult_a_password)
    private_a = await _create_budget(client, adult_a_headers, private_budget_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    response = await client.get("/dashboard/api/family-budgets", headers=adult_b_headers)
    assert response.status_code == 200, response.text
    ids = {b["id"] for b in response.json()["budgets"]}
    assert shared["id"] in ids
    assert private_a["id"] not in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_sees_read_only_budget_no_manage_action(
    client, db, unique, shared_budget_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    shared = await _create_budget(client, head_headers, shared_budget_payload)

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.get("/dashboard/api/family-budgets", headers=viewer_headers)
    assert response.status_code == 200, response.text
    item = next(b for b in response.json()["budgets"] if b["id"] == shared["id"])
    assert item["can_view"] is True
    assert item["can_manage"] is False

    # No archive quick action rendered for a viewer.
    widget_response = await client.get("/dashboard/partials/family-budgets", headers=viewer_headers)
    assert "bi-archive" not in widget_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_manage_action_appears_only_when_can_manage(
    client, db, unique, private_budget_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _create_budget(client, head_headers, private_budget_payload)

    response = await client.get("/dashboard/partials/family-budgets", headers=head_headers)
    assert response.status_code == 200, response.text
    assert "bi-archive" in response.text


# ---------------------------------------------------------------------------
# Safety: read-only, no leaks
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_creates_no_financial_records(client, auth_headers, db, private_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)
    expense = await _create_expense_account(client, auth_headers, "5500", "SafetyCheck")
    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "SafetyCheck", "account_id": expense["id"], "budgeted_amount": "50.000"},
        headers=auth_headers,
    )

    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)
    budgets_before = await count_rows(db, Budget)
    notifications_before = await count_rows(db, Notification)

    await client.get("/dashboard/", headers=auth_headers)
    await client.get("/dashboard/api/family-budgets", headers=auth_headers)
    await client.get("/dashboard/partials/family-budgets", headers=auth_headers)
    await client.get(f"/dashboard/partials/family-budgets/{budget['id']}/categories", headers=auth_headers)

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, JournalEntry) == journals_before
    assert await count_rows(db, Budget) == budgets_before
    assert await count_rows(db, Notification) == notifications_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_does_not_mutate_budget_actual_field(
    client, auth_headers, db, private_budget_payload
):
    """Rendering the widget must not persist a stale total_actual onto the Budget row."""
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1600", "name": "Cash4", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5600", "Mutation")
    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Mutation", "account_id": expense["id"], "budgeted_amount": "50.000"},
        headers=auth_headers,
    )
    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=2)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "30.000", mid_period)

    # Render the dashboard widget (computes actual=30 in-memory).
    await client.get("/dashboard/partials/family-budgets", headers=auth_headers)

    # The stored Budget.total_actual must remain untouched by the dashboard render.
    detail = await client.get(f"/family/budgets/{budget['id']}", headers=auth_headers)
    assert Decimal(detail.json()["total_actual"]) == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_inaccessible_account_name_not_leaked_in_dashboard(
    client, db, unique, tenant_context, private_budget_payload
):
    from app.tests.helpers import create_test_account

    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult_a, adult_a_password = await create_test_user(
        db, org, email=unique("adult_a") + "@example.com", role="viewer"
    )
    adult_b, adult_b_password = await create_test_user(
        db, org, email=unique("adult_b") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult_a, "adult")
    await _add_member(client, head_headers, adult_b, "adult")

    # adult_b has a private expense account; a shared budget references it
    # by ID directly at the DB layer to simulate a stale/edge-case link.
    await tenant_context(org.id)
    private_expense = await create_test_account(
        db, org.id, code=unique("EXP"), name="Adult B Secret Expense",
        account_type="Expense", visibility="private", owner_user_id=adult_b.id,
    )
    await db.commit()

    head_shared = await _create_budget(client, head_headers, {**private_budget_payload, "visibility": "shared"})
    # Head can manage shared budgets and add the category (head bypasses
    # per-account visibility checks as an elevated role).
    await client.post(
        f"/family/budgets/{head_shared['id']}/categories",
        json={"name": "Hidden", "account_id": private_expense.id, "budgeted_amount": "20.000"},
        headers=head_headers,
    )

    adult_a_headers = await auth_headers_for(client, adult_a.email, adult_a_password)
    response = await client.get("/dashboard/partials/family-budgets", headers=adult_a_headers)
    assert response.status_code == 200, response.text
    assert "Adult B Secret Expense" not in response.text


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_budgets_on_dashboard(
    client, db, unique, shared_budget_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    budget_a = await _create_budget(client, headers_a, shared_budget_payload)

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    response_b = await client.get("/dashboard/api/family-budgets", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert budget_a["id"] not in {b["id"] for b in response_b.json()["budgets"]}

    dashboard_b = await client.get("/dashboard/", headers=headers_b)
    assert budget_a["name"] not in dashboard_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_budget_tables_via_dashboard(db):
    await assert_rls_enabled(db, "budgets")
    await assert_rls_enabled(db, "budget_categories")
