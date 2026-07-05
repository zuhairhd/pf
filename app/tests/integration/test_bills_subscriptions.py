"""Bills and Subscriptions router tests.

Covers CRUD, status transitions, dashboard commitments, tenant isolation, and
RLS for the bills and subscriptions tables.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Account, Bill, JournalEntry, JournalLine, Subscription, SubscriptionStatus
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


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


async def _create_payment_accounts(client, headers, unique):
    payment = await _create_account(
        client, headers, unique, account_type="Asset", name="Bank"
    )
    expense = await _create_account(
        client, headers, unique, account_type="Expense", name="Utilities"
    )
    return payment, expense


async def _journal_lines(db, tenant_context, tenant_id, journal_entry_id):
    await tenant_context(tenant_id)
    result = await db.execute(
        select(JournalLine)
        .where(JournalLine.tenant_id == tenant_id)
        .where(JournalLine.journal_entry_id == journal_entry_id)
        .order_by(JournalLine.id)
    )
    return list(result.scalars().all())


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
async def test_mark_bill_paid_creates_balanced_journal_entry(
    client, auth_headers, bill_payload, unique, db, tenant_context, test_user
):
    """Mark-paid posts a balanced journal entry through the accounting engine."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/bills",
        json={
            **bill_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    bill_id = create_response.json()["id"]

    response = await client.post(
        f"/bills/{bill_id}/mark-paid",
        json={"payment_date": date.today().isoformat(), "notes": "Paid from bank"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["is_paid"] is True
    assert data["status"] == "paid"
    assert data["paid_at"] is not None
    assert data["journal_entry_id"] is not None
    assert data["debit_account_id"] == expense["id"]
    assert data["credit_account_id"] == payment["id"]
    assert Decimal(data["payment_amount"]) == Decimal(bill_payload["typical_amount"])
    assert data["currency"] == "OMR"

    lines = await _journal_lines(
        db, tenant_context, test_user.organization_id, data["journal_entry_id"]
    )
    assert len(lines) == 2
    debit_line = next(line for line in lines if line.debit > 0)
    credit_line = next(line for line in lines if line.credit > 0)
    assert debit_line.account_id == expense["id"]
    assert credit_line.account_id == payment["id"]
    assert debit_line.debit == Decimal("45.000")
    assert credit_line.credit == Decimal("45.000")
    assert sum((line.debit for line in lines), Decimal("0")) == sum(
        (line.credit for line in lines), Decimal("0")
    )

    await tenant_context(test_user.organization_id)
    entry = await db.get(JournalEntry, data["journal_entry_id"])
    assert entry.reference == f"BILL-{test_user.organization_id}-{bill_id}"
    assert entry.narration == "Bill payment: Electricity"
    assert entry.source == "bill_payment"


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_paid_twice_does_not_duplicate_journal_entry(
    client, auth_headers, bill_payload, unique, db, tenant_context, test_user
):
    """Repeated mark-paid calls return the same payment journal entry."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/bills",
        json={
            **bill_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    bill_id = create_response.json()["id"]

    first = await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    second = await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["journal_entry_id"] == first.json()["journal_entry_id"]

    await tenant_context(test_user.organization_id)
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.tenant_id == test_user.organization_id,
            JournalEntry.reference == f"BILL-{test_user.organization_id}-{bill_id}",
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_paid_requires_accounts(client, auth_headers, bill_payload):
    """Mark-paid fails clearly when no payment accounts are supplied."""
    create_response = await client.post("/bills", json=bill_payload, headers=auth_headers)
    bill_id = create_response.json()["id"]

    response = await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    assert response.status_code == 400
    assert "Payment account is required" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_unpaid_blocks_posted_journal_entry(
    client, auth_headers, bill_payload, unique
):
    """Mark-unpaid does not delete or undo a posted journal entry."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/bills",
        json={
            **bill_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    bill_id = create_response.json()["id"]
    paid_response = await client.post(f"/bills/{bill_id}/mark-paid", headers=auth_headers)
    journal_entry_id = paid_response.json()["journal_entry_id"]

    response = await client.post(f"/bills/{bill_id}/mark-unpaid", headers=auth_headers)
    assert response.status_code == 400
    assert "payment journal entry" in response.text

    get_response = await client.get(f"/bills/{bill_id}", headers=auth_headers)
    assert get_response.json()["is_paid"] is True
    assert get_response.json()["journal_entry_id"] == journal_entry_id


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
async def test_mark_subscription_paid_creates_balanced_journal_entry(
    client, auth_headers, subscription_payload, unique, db, tenant_context, test_user
):
    """Subscription mark-paid posts debit expense and credit bank/cash."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/subscriptions",
        json={
            **subscription_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    subscription_id = create_response.json()["id"]
    original_date = create_response.json()["next_billing_date"]

    response = await client.post(f"/subscriptions/{subscription_id}/mark-paid", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    new_date = data["next_billing_date"]
    assert new_date != original_date
    assert data["journal_entry_id"] is not None
    assert data["debit_account_id"] == expense["id"]
    assert data["credit_account_id"] == payment["id"]
    assert Decimal(data["payment_amount"]) == Decimal(subscription_payload["amount"])

    lines = await _journal_lines(
        db, tenant_context, test_user.organization_id, data["journal_entry_id"]
    )
    assert len(lines) == 2
    assert sum((line.debit for line in lines), Decimal("0")) == Decimal("15.000")
    assert sum((line.credit for line in lines), Decimal("0")) == Decimal("15.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_subscription_paid_twice_is_idempotent(
    client, auth_headers, subscription_payload, unique
):
    """Repeated subscription mark-paid calls do not duplicate posting or date advance."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/subscriptions",
        json={
            **subscription_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    subscription_id = create_response.json()["id"]

    first = await client.post(f"/subscriptions/{subscription_id}/mark-paid", headers=auth_headers)
    second = await client.post(f"/subscriptions/{subscription_id}/mark-paid", headers=auth_headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["journal_entry_id"] == first.json()["journal_entry_id"]
    assert second.json()["next_billing_date"] == first.json()["next_billing_date"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_subscription_unpaid_blocks_posted_journal_entry(
    client, auth_headers, subscription_payload, unique
):
    """Subscription mark-unpaid is blocked after a payment journal entry exists."""
    payment, expense = await _create_payment_accounts(client, auth_headers, unique)
    create_response = await client.post(
        "/subscriptions",
        json={
            **subscription_payload,
            "payment_account_id": payment["id"],
            "expense_account_id": expense["id"],
        },
        headers=auth_headers,
    )
    subscription_id = create_response.json()["id"]
    paid_response = await client.post(
        f"/subscriptions/{subscription_id}/mark-paid", headers=auth_headers
    )
    assert paid_response.status_code == 200, paid_response.text

    response = await client.post(
        f"/subscriptions/{subscription_id}/mark-unpaid", headers=auth_headers
    )
    assert response.status_code == 400
    assert "payment journal entry" in response.text


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
async def test_mark_bill_paid_rejects_cross_tenant_payment_account(
    client, db, unique, bill_payload
):
    """Tenant A cannot post a bill using Tenant B's payment account."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)
    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    tenant_b_payment = await _create_account(
        client, headers_b, unique, account_type="Asset", name="TenantBBank"
    )
    tenant_a_expense = await _create_account(
        client, headers_a, unique, account_type="Expense", name="TenantAExpense"
    )
    bill = await client.post("/bills", json=bill_payload, headers=headers_a)

    response = await client.post(
        f"/bills/{bill.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_b_payment["id"],
            "expense_account_id": tenant_a_expense["id"],
        },
        headers=headers_a,
    )
    assert response.status_code == 400
    assert "Payment account not found" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_paid_rejects_cross_tenant_expense_account(
    client, db, unique, bill_payload
):
    """Tenant A cannot post a bill using Tenant B's expense account."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)
    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    tenant_a_payment = await _create_account(
        client, headers_a, unique, account_type="Asset", name="TenantABank"
    )
    tenant_b_expense = await _create_account(
        client, headers_b, unique, account_type="Expense", name="TenantBExpense"
    )
    bill = await client.post("/bills", json=bill_payload, headers=headers_a)

    response = await client.post(
        f"/bills/{bill.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_a_payment["id"],
            "expense_account_id": tenant_b_expense["id"],
        },
        headers=headers_a,
    )
    assert response.status_code == 400
    assert "Expense account not found" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_bill_paid_rejects_wrong_account_types(
    client, auth_headers, unique, bill_payload
):
    """Payment must be Asset and debit account must be Expense."""
    income = await _create_account(client, auth_headers, unique, account_type="Income", name="Income")
    asset = await _create_account(client, auth_headers, unique, account_type="Asset", name="Asset")
    liability = await _create_account(
        client, auth_headers, unique, account_type="Liability", name="Liability"
    )
    bill = await client.post("/bills", json=bill_payload, headers=auth_headers)

    payment_response = await client.post(
        f"/bills/{bill.json()['id']}/mark-paid",
        json={"payment_account_id": income["id"], "expense_account_id": liability["id"]},
        headers=auth_headers,
    )
    assert payment_response.status_code == 400
    assert "Payment account must be an Asset account" in payment_response.text

    expense_response = await client.post(
        f"/bills/{bill.json()['id']}/mark-paid",
        json={"payment_account_id": asset["id"], "expense_account_id": liability["id"]},
        headers=auth_headers,
    )
    assert expense_response.status_code == 400
    assert "Expense account must be an Expense account" in expense_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_mark_subscription_paid_rejects_cross_tenant_and_wrong_type_accounts(
    client, db, unique, subscription_payload
):
    """Subscription posting validates tenant ownership and account types."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)
    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    tenant_a_payment = await _create_account(
        client, headers_a, unique, account_type="Asset", name="TenantABank"
    )
    tenant_b_payment = await _create_account(
        client, headers_b, unique, account_type="Asset", name="TenantBBank"
    )
    tenant_a_expense = await _create_account(
        client, headers_a, unique, account_type="Expense", name="TenantAExpense"
    )
    tenant_b_expense = await _create_account(
        client, headers_b, unique, account_type="Expense", name="TenantBExpense"
    )
    tenant_a_liability = await _create_account(
        client, headers_a, unique, account_type="Liability", name="TenantALiability"
    )
    sub = await client.post("/subscriptions", json=subscription_payload, headers=headers_a)

    cross_tenant_payment_response = await client.post(
        f"/subscriptions/{sub.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_b_payment["id"],
            "expense_account_id": tenant_a_expense["id"],
        },
        headers=headers_a,
    )
    assert cross_tenant_payment_response.status_code == 400
    assert "Payment account not found" in cross_tenant_payment_response.text

    cross_tenant_expense_response = await client.post(
        f"/subscriptions/{sub.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_a_payment["id"],
            "expense_account_id": tenant_b_expense["id"],
        },
        headers=headers_a,
    )
    assert cross_tenant_expense_response.status_code == 400
    assert "Expense account not found" in cross_tenant_expense_response.text

    wrong_payment_type_response = await client.post(
        f"/subscriptions/{sub.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_a_liability["id"],
            "expense_account_id": tenant_a_expense["id"],
        },
        headers=headers_a,
    )
    assert wrong_payment_type_response.status_code == 400
    assert "Payment account must be an Asset account" in wrong_payment_type_response.text

    wrong_expense_type_response = await client.post(
        f"/subscriptions/{sub.json()['id']}/mark-paid",
        json={
            "payment_account_id": tenant_a_payment["id"],
            "expense_account_id": tenant_a_liability["id"],
        },
        headers=headers_a,
    )
    assert wrong_expense_type_response.status_code == 400
    assert "Expense account must be an Expense account" in wrong_expense_type_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_pay_tenant_b_bill_or_subscription(
    client, db, unique, bill_payload, subscription_payload
):
    """Payment routes do not expose or post another tenant's commitments."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)
    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)
    payment_b, expense_b = await _create_payment_accounts(client, headers_b, unique)

    bill_b = await client.post(
        "/bills",
        json={
            **bill_payload,
            "payment_account_id": payment_b["id"],
            "expense_account_id": expense_b["id"],
        },
        headers=headers_b,
    )
    sub_b = await client.post(
        "/subscriptions",
        json={
            **subscription_payload,
            "payment_account_id": payment_b["id"],
            "expense_account_id": expense_b["id"],
        },
        headers=headers_b,
    )

    bill_response = await client.post(
        f"/bills/{bill_b.json()['id']}/mark-paid", headers=headers_a
    )
    sub_response = await client.post(
        f"/subscriptions/{sub_b.json()['id']}/mark-paid", headers=headers_a
    )
    assert bill_response.status_code == 404
    assert sub_response.status_code == 404


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
