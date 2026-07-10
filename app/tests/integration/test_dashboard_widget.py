"""Dashboard widget UI tests.

Covers the bills/subscriptions dashboard widget, HTMX partials, tenant
isolation, and RLS.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


async def _create_family(client, headers, name="Test Family"):
    response = await client.post("/family", json={"name": name, "currency": "OMR"}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _add_family_member(client, headers, user, role: str):
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


async def _create_family_goal(client, headers, payload):
    response = await client.post("/family/goals", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def shared_goal_payload():
    return {
        "name": "Family Vacation",
        "goal_type": "vacation",
        "target_amount": "1000.000",
        "target_date": (date.today() + timedelta(days=365)).isoformat(),
        "monthly_contribution": "100.000",
        "description": "Save for next summer vacation",
        "priority": 1,
        "visibility": "shared",
    }


@pytest.fixture
def private_goal_payload():
    return {
        "name": "Personal Gadget Fund",
        "goal_type": "custom",
        "target_amount": "500.000",
        "target_date": (date.today() + timedelta(days=180)).isoformat(),
        "monthly_contribution": "50.000",
        "description": "New laptop",
        "priority": 2,
        "visibility": "private",
    }


async def _create_account(client, headers, unique, *, account_type: str, name: str):
    payload = {
        "code": unique(name)[:20],
        "name": unique(name),
        "account_type": account_type,
        "is_bank_account": account_type == "Asset",
    }
    response = await client.post("/accounts/", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _bill_payload_with_accounts(client, headers, unique, bill_payload):
    payment = await _create_account(
        client, headers, unique, account_type="Asset", name="DashboardBank"
    )
    expense = await _create_account(
        client, headers, unique, account_type="Expense", name="DashboardExpense"
    )
    return {
        **bill_payload,
        "payment_account_id": payment["id"],
        "expense_account_id": expense["id"],
    }


@pytest.fixture
def bill_payload():
    return {
        "name": "Electricity",
        "provider": "Majan Electricity",
        "typical_amount": "45.000",
        "due_date": (date.today() + timedelta(days=2)).isoformat(),
        "frequency": "monthly",
    }


@pytest.fixture
def overdue_bill_payload():
    return {
        "name": "Old Bill",
        "provider": "Provider",
        "typical_amount": "10.000",
        "due_date": (date.today() - timedelta(days=1)).isoformat(),
        "frequency": "one-time",
    }


@pytest.fixture
def subscription_payload():
    return {
        "name": "Mobile Plan",
        "provider": "Ooredoo",
        "amount": "15.000",
        "frequency": "monthly",
        "next_billing_date": (date.today() + timedelta(days=5)).isoformat(),
        "category": "Utilities",
    }


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_requires_auth(client):
    """Anonymous users cannot access the dashboard."""
    response = await client.get("/dashboard/")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_renders_for_authenticated_user(client, auth_headers):
    """The dashboard page renders for an authenticated tenant user."""
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Bills & Subscriptions" in response.text
    assert "Upcoming Bills" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_renders_upcoming_bills(
    client, auth_headers, bill_payload
):
    """The dashboard widget shows upcoming bills."""
    await client.post("/bills", json=bill_payload, headers=auth_headers)

    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert bill_payload["name"] in response.text
    assert "Mark Paid" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_renders_overdue_bills(
    client, auth_headers, overdue_bill_payload
):
    """The dashboard widget shows overdue bills."""
    await client.post("/bills", json=overdue_bill_payload, headers=auth_headers)

    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert overdue_bill_payload["name"] in response.text
    assert "Was due" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_renders_upcoming_subscriptions(
    client, auth_headers, subscription_payload
):
    """The dashboard widget shows upcoming subscription renewals."""
    await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)

    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert subscription_payload["name"] in response.text
    assert "Upcoming Renewals" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_empty_state(client, auth_headers):
    """Empty states render when there are no bills or subscriptions."""
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "No upcoming bills for the next 7 days" in response.text
    assert "No overdue bills" in response.text
    assert "No subscription renewals in the next 30 days" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_commitments_api_requires_auth(client):
    """Anonymous users cannot call the commitments API."""
    response = await client.get("/dashboard/api/commitments")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_commitments_api_respects_tenant_context(
    client, db, unique, bill_payload
):
    """Tenant B cannot see Tenant A's bills in the commitments API."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await client.post("/bills", json=bill_payload, headers=headers_a)

    response_a = await client.get("/dashboard/api/commitments", headers=headers_a)
    assert response_a.status_code == 200, response_a.text
    assert response_a.json()["upcoming_bills_count"] >= 1

    response_b = await client.get("/dashboard/api/commitments", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert response_b.json()["upcoming_bills_count"] == 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_dashboard_data(
    client, db, unique, bill_payload, subscription_payload
):
    """Tenant B's dashboard HTML does not contain Tenant A's commitments."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await client.post("/bills", json=bill_payload, headers=headers_a)
    await client.post("/subscriptions", json=subscription_payload, headers=headers_a)

    response_b = await client.get("/dashboard/", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert bill_payload["name"] not in response_b.text
    assert subscription_payload["name"] not in response_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_mark_paid_quick_action(
    client, auth_headers, bill_payload, unique
):
    """Marking an account-configured bill paid refreshes the widget."""
    payload = await _bill_payload_with_accounts(client, auth_headers, unique, bill_payload)
    create_response = await client.post("/bills", json=payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.post(
        f"/dashboard/partials/bills/{bill_id}/mark-paid",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "Bills & Subscriptions" in response.text

    commitments_response = await client.get(
        "/dashboard/api/commitments", headers=auth_headers
    )
    data = commitments_response.json()
    assert data["upcoming_bills_count"] == 0

    repeat_response = await client.post(
        f"/dashboard/partials/bills/{bill_id}/mark-paid",
        headers=auth_headers,
    )
    assert repeat_response.status_code == 200, repeat_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_mark_paid_missing_accounts_returns_clear_error(
    client, auth_headers, bill_payload
):
    """Dashboard quick action does not post when payment accounts are missing."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.post(
        f"/dashboard/partials/bills/{bill_id}/mark-paid",
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text
    assert "Payment account is required" in response.text
    assert "choose payment and expense accounts" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_run_reminders_quick_action(
    client, auth_headers, bill_payload
):
    """Tenant admins can run reminders from the dashboard."""
    await client.post("/bills", json=bill_payload, headers=auth_headers)

    response = await client.post(
        "/dashboard/partials/run-reminders",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "Bills & Subscriptions" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_run_reminders_rejected_for_viewer(
    client, db, unique, bill_payload
):
    """Non-admin tenant users cannot run reminders from the dashboard."""
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    viewer, password = await create_test_user(db, org, role="viewer")
    headers = await auth_headers_for(client, viewer.email, password)

    response = await client.post("/dashboard/partials/run-reminders", headers=headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_commitment_tables(db):
    """Bills and subscriptions tables remain protected by RLS."""
    await assert_rls_enabled(db, "bills")
    await assert_rls_enabled(db, "subscriptions")


# ---------------------------------------------------------------------------
# Family Goals Dashboard Widget Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_api_requires_auth(client):
    response = await client.get("/dashboard/api/family-goals")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_partial_requires_auth(client):
    response = await client.get("/dashboard/partials/family-goals")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_widget_renders(
    client, auth_headers, shared_goal_payload
):
    await _create_family(client, auth_headers)
    goal = await _create_family_goal(client, auth_headers, shared_goal_payload)

    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Family Goals" in response.text
    assert goal["name"] in response.text
    assert "Family Vacation" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_head_sees_all_family_goals(
    client, auth_headers, shared_goal_payload, private_goal_payload
):
    await _create_family(client, auth_headers)
    shared = await _create_family_goal(client, auth_headers, shared_goal_payload)
    private = await _create_family_goal(client, auth_headers, private_goal_payload)

    response = await client.get("/dashboard/api/family-goals", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    goal_ids = {g["id"] for g in data["goals"]}
    assert shared["id"] in goal_ids
    assert private["id"] in goal_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_adult_sees_shared_and_own_private(
    client, db, unique, shared_goal_payload, private_goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_family_member(client, head_headers, adult, "adult")

    shared = await _create_family_goal(client, head_headers, shared_goal_payload)
    adult_private_payload = {**private_goal_payload, "name": "Adult Private Goal"}
    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    adult_private = await _create_family_goal(client, adult_headers, adult_private_payload)

    response = await client.get("/dashboard/api/family-goals", headers=adult_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    goal_ids = {g["id"] for g in data["goals"]}
    assert shared["id"] in goal_ids
    assert adult_private["id"] in goal_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_adult_does_not_see_other_adult_private(
    client, db, unique, shared_goal_payload, private_goal_payload
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
    await _add_family_member(client, head_headers, adult_a, "adult")
    await _add_family_member(client, head_headers, adult_b, "adult")

    await _create_family_goal(client, head_headers, shared_goal_payload)

    adult_a_headers = await auth_headers_for(client, adult_a.email, adult_a_password)
    adult_a_private = {**private_goal_payload, "name": "Adult A Private"}
    await _create_family_goal(client, adult_a_headers, adult_a_private)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    response = await client.get("/dashboard/", headers=adult_b_headers)
    assert response.status_code == 200, response.text
    assert "Adult A Private" not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_viewer_sees_read_only_shared_goals(
    client, db, unique, shared_goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_family_member(client, head_headers, viewer, "viewer")

    shared = await _create_family_goal(client, head_headers, shared_goal_payload)

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.get("/dashboard/api/family-goals", headers=viewer_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert shared["id"] in {g["id"] for g in data["goals"]}

    # Viewer goals should not have manage/contribute permissions.
    goal_item = next(g for g in data["goals"] if g["id"] == shared["id"])
    assert goal_item["can_view"] is True
    assert goal_item["can_manage"] is False
    assert goal_item["can_contribute"] is False


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_empty_state(client, auth_headers):
    await _create_family(client, auth_headers)
    response = await client.get("/dashboard/partials/family-goals", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "No active family goals yet" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_progress_percent(
    client, auth_headers, shared_goal_payload
):
    await _create_family(client, auth_headers)
    goal = await _create_family_goal(client, auth_headers, shared_goal_payload)

    await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "250.000", "date": date.today().isoformat()},
        headers=auth_headers,
    )

    response = await client.get("/dashboard/api/family-goals", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    item = next(g for g in data["goals"] if g["id"] == goal["id"])
    assert item["progress_percent"] == 25.0
    assert item["current_amount"] == 250.0
    assert item["remaining_amount"] == 750.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_quick_actions(
    client, auth_headers, shared_goal_payload
):
    await _create_family(client, auth_headers)
    goal = await _create_family_goal(client, auth_headers, shared_goal_payload)

    response = await client.post(
        f"/dashboard/partials/family-goals/{goal['id']}/contributions",
        data={"amount": "100.000", "date": date.today().isoformat()},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "Family Goals" in response.text

    complete_response = await client.post(
        f"/dashboard/partials/family-goals/{goal['id']}/complete",
        headers=auth_headers,
    )
    assert complete_response.status_code == 200, complete_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_goals_tenant_isolation(
    client, db, unique, shared_goal_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    goal_a = await _create_family_goal(client, headers_a, shared_goal_payload)

    await _create_family(client, headers_b, name="Family B")

    response_b = await client.get("/dashboard/api/family-goals", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert goal_a["id"] not in {g["id"] for g in response_b.json()["goals"]}

    dashboard_b = await client.get("/dashboard/", headers=headers_b)
    assert goal_a["name"] not in dashboard_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")
