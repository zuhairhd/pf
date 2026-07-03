"""Bills and Subscriptions router tests.

Covers CRUD, status transitions, dashboard commitments, tenant isolation, and
RLS for the bills and subscriptions tables.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Bill, Subscription, SubscriptionStatus
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
        "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "frequency": "monthly",
    }


@pytest.fixture
def subscription_payload():
    return {
        "name": "Mobile Plan",
        "provider": "Ooredoo",
        "amount": "15.000",
        "frequency": "monthly",
        "next_billing_date": (date.today() + timedelta(days=10)).isoformat(),
        "category": "Utilities",
    }


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_create_bill(client, auth_headers, bill_payload):
    """An authenticated tenant user can create a bill."""
    response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == bill_payload["name"]
    assert data["provider"] == bill_payload["provider"]
    assert Decimal(data["typical_amount"]) == Decimal(bill_payload["typical_amount"])
    assert data["status"] == "upcoming"
    assert data["is_paid"] is False


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_bills(client, auth_headers, bill_payload):
    """Bills are listed for the current tenant only."""
    await client.post("/bills", json=bill_payload, headers=auth_headers)
    response = await client.get("/bills", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) >= 1
    assert all(b["status"] in ("upcoming", "paid", "overdue", "cancelled") for b in data)


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_bill(client, auth_headers, bill_payload):
    """A single bill can be retrieved."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.get(f"/bills/{bill_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == bill_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_bill(client, auth_headers, bill_payload):
    """A bill can be updated."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.patch(
        f"/bills/{bill_id}",
        json={"typical_amount": "55.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["typical_amount"]) == Decimal("55.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_delete_bill(client, auth_headers, bill_payload):
    """A bill can be deleted."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.delete(f"/bills/{bill_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True

    get_response = await client.get(f"/bills/{bill_id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_paid(client, auth_headers, bill_payload):
    """Mark-paid updates the bill status and timestamp."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["is_paid"] is True
    assert data["status"] == "paid"
    assert data["paid_at"] is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_unpaid(client, auth_headers, bill_payload):
    """Mark-unpaid reverts a paid bill."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    response = await client.post(f"/bills/{bill_id}/mark-unpaid", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["is_paid"] is False
    assert data["paid_at"] is None
    assert data["status"] == "upcoming"


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_bill(client, auth_headers, bill_payload):
    """A bill can be cancelled."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.post(f"/bills/{bill_id}/cancel", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


@pytest.mark.integration
@pytest.mark.anyio
async def test_overdue_bills(client, auth_headers):
    """Overdue bills are returned based on due date."""
    overdue_payload = {
        "name": "Old Bill",
        "provider": "Provider",
        "typical_amount": "10.000",
        "due_date": (date.today() - timedelta(days=1)).isoformat(),
        "frequency": "one-time",
    }
    await client.post("/bills", json=overdue_payload, headers=auth_headers)

    response = await client.get("/bills/overdue", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) >= 1


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_create_subscription(client, auth_headers, subscription_payload):
    """An authenticated tenant user can create a subscription."""
    response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == subscription_payload["name"]
    assert data["provider"] == subscription_payload["provider"]
    assert data["status"] == "active"
    assert data["monthly_equivalent_amount"] is not None
    assert data["yearly_equivalent_amount"] is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_subscriptions(client, auth_headers, subscription_payload):
    """Subscriptions are listed for the current tenant only."""
    await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    response = await client.get("/subscriptions", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_subscription(client, auth_headers, subscription_payload):
    """A single subscription can be retrieved."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]

    response = await client.get(f"/subscriptions/{subscription_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == subscription_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_subscription(client, auth_headers, subscription_payload):
    """A subscription can be updated."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]

    response = await client.patch(
        f"/subscriptions/{subscription_id}",
        json={"amount": "20.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["amount"]) == Decimal("20.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_delete_subscription(client, auth_headers, subscription_payload):
    """A subscription can be deleted."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]

    response = await client.delete(f"/subscriptions/{subscription_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_subscription_paid(client, auth_headers, subscription_payload):
    """Mark-paid advances the next billing date."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]
    original_date = create_response.json()["next_billing_date"]

    response = await client.post(f"/subscriptions/{subscription_id}/mark-paid", headers=auth_headers)
    assert response.status_code == 200, response.text
    new_date = response.json()["next_billing_date"]
    assert new_date != original_date


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_subscription(client, auth_headers, subscription_payload):
    """A subscription can be cancelled."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]

    response = await client.post(f"/subscriptions/{subscription_id}/cancel", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


@pytest.mark.integration
@pytest.mark.anyio
async def test_pause_and_activate_subscription(client, auth_headers, subscription_payload):
    """A subscription can be paused and resumed."""
    create_response = await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)
    subscription_id = create_response.json()["id"]

    pause_response = await client.post(f"/subscriptions/{subscription_id}/pause", headers=auth_headers)
    assert pause_response.status_code == 200, response.text
    assert pause_response.json()["status"] == "paused"

    activate_response = await client.post(f"/subscriptions/{subscription_id}/activate", headers=auth_headers)
    assert activate_response.status_code == 200, response.text
    assert activate_response.json()["status"] == "active"


@pytest.mark.integration
@pytest.mark.anyio
async def test_subscription_equivalent_amounts(client, auth_headers):
    """Monthly and yearly equivalents are calculated correctly."""
    payload = {
        "name": "Yearly Software",
        "provider": "Vendor",
        "amount": "120.000",
        "frequency": "yearly",
        "next_billing_date": (date.today() + timedelta(days=20)).isoformat(),
    }
    response = await client.post("/subscriptions", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert Decimal(data["monthly_equivalent_amount"]) == Decimal("10.000")
    assert Decimal(data["yearly_equivalent_amount"]) == Decimal("120.000")


# ---------------------------------------------------------------------------
# Tenant isolation and RLS
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_bills(client, db, unique, bill_payload):
    """Tenant B cannot read bills created by Tenant A."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    create_response = await client.post("/bills", json=bill_payload, headers=headers_a)
    assert create_response.status_code == 200
    bill_id = create_response.json()["id"]

    response_b = await client.get(f"/bills/{bill_id}", headers=headers_b)
    assert response_b.status_code == 404

    list_b = await client.get("/bills", headers=headers_b)
    assert list_b.status_code == 200
    assert not any(b["id"] == bill_id for b in list_b.json())


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_subscriptions(client, db, unique, subscription_payload):
    """Tenant B cannot read subscriptions created by Tenant A."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    create_response = await client.post("/subscriptions", json=subscription_payload, headers=headers_a)
    assert create_response.status_code == 200
    subscription_id = create_response.json()["id"]

    response_b = await client.get(f"/subscriptions/{subscription_id}", headers=headers_b)
    assert response_b.status_code == 404

    list_b = await client.get("/subscriptions", headers=headers_b)
    assert list_b.status_code == 200
    assert not any(s["id"] == subscription_id for s in list_b.json())


@pytest.mark.integration
@pytest.mark.anyio
async def test_bills_require_auth(client, bill_payload):
    """Anonymous users cannot create or list bills."""
    create_response = await client.post("/bills", json=bill_payload)
    assert create_response.status_code in (401, 403)

    list_response = await client.get("/bills")
    assert list_response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_subscriptions_require_auth(client, subscription_payload):
    """Anonymous users cannot create or list subscriptions."""
    create_response = await client.post("/subscriptions", json=subscription_payload)
    assert create_response.status_code in (401, 403)

    list_response = await client.get("/subscriptions")
    assert list_response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_bills_and_subscriptions(db):
    """Both tables must have RLS and FORCE RLS enabled."""
    await assert_rls_enabled(db, "bills")
    await assert_rls_enabled(db, "subscriptions")


# ---------------------------------------------------------------------------
# Dashboard commitments
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_commitments(client, auth_headers, bill_payload, subscription_payload):
    """Dashboard commitments summarize upcoming bills and subscriptions."""
    await client.post("/bills", json=bill_payload, headers=auth_headers)
    await client.post("/subscriptions", json=subscription_payload, headers=auth_headers)

    response = await client.get("/dashboard/api/commitments", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["upcoming_bills_count"] >= 1
    assert Decimal(data["upcoming_bills_total"]) >= Decimal(bill_payload["typical_amount"])
    assert data["upcoming_renewals_count"] >= 1
    assert Decimal(data["upcoming_renewals_total"]) >= Decimal(subscription_payload["amount"])
    assert Decimal(data["monthly_subscription_total"]) >= Decimal(subscription_payload["amount"])
    assert Decimal(data["total_fixed_commitments_this_month"]) > Decimal("0")
