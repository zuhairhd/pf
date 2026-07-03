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
    client, auth_headers, bill_payload
):
    """Marking a bill paid from the dashboard refreshes the widget."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
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
