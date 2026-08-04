"""Allowance payment posting through the accounting engine tests (FAM-1305).

Covers posting an approved chore completion's earned allowance as a
balanced journal entry through AccountingService, account validation,
role-based posting/reversal permissions, idempotency, safe reversal,
allowance summary payment-status breakdowns, dashboard "ready to pay"
safety, and tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import JournalEntry, JournalLine
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _create_chore(client, headers, payload):
    response = await client.post("/family/chores", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _chore_payload(assigned_to_member_id=None, allowance_amount="5.000", due_date=None):
    return {
        "title": "Wash dishes",
        "description": "Wash and dry all dishes after dinner",
        "assigned_to_member_id": assigned_to_member_id,
        "allowance_amount": allowance_amount,
        "currency": "OMR",
        "frequency": "daily",
        "due_date": due_date,
        "requires_approval": True,
    }


async def _create_account(client, headers, code, name, account_type="Asset"):
    response = await client.post(
        "/accounts/",
        json={"code": code, "name": name, "account_type": account_type},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _setup_head_and_teen(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    return head_headers, teen_headers, member, org.id


async def _approve_via_api(client, head_headers, chore, teen_headers, allowance_amount="10.000"):
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    approved = (
        await client.post(
            f"/family/chore-completions/{completion['id']}/approve", json={}, headers=head_headers
        )
    ).json()
    return approved


# ---------------------------------------------------------------------------
# Payment posting
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_pay_approved_completion(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="10.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers)

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["payment_status"] == "paid"
    assert data["payment_journal_entry_id"] is not None
    assert Decimal(data["amount"]) == Decimal("10.000")
    assert data["debit_account_id"] == expense["id"]
    assert data["credit_account_id"] == cash["id"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_payment_creates_balanced_journal_entry_debit_expense_credit_asset(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="12.500")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "12.500")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    entry_id = response.json()["payment_journal_entry_id"]

    await set_tenant_context_async(db, org_id)
    result = await db.execute(
        JournalLine.__table__.select().where(JournalLine.journal_entry_id == entry_id)
    )
    lines = result.fetchall()
    assert len(lines) == 2
    total_debit = sum(Decimal(str(l.debit)) for l in lines)
    total_credit = sum(Decimal(str(l.credit)) for l in lines)
    assert total_debit == total_credit == Decimal("12.500")

    expense_line = next(l for l in lines if l.account_id == expense["id"])
    cash_line = next(l for l in lines if l.account_id == cash["id"])
    assert expense_line.debit == Decimal("12.500")
    assert expense_line.credit == Decimal("0.000")
    assert cash_line.credit == Decimal("12.500")
    assert cash_line.debit == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_unapproved_completion_cannot_be_paid(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{completion['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_zero_earned_amount_cannot_be_paid(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    # Reject sets earned_amount to 0, but status is rejected (not approved) — use
    # approve with an explicit zero override instead, to isolate the zero-amount rule.
    approved = (
        await client.post(
            f"/family/chore-completions/{completion['id']}/approve",
            json={"earned_amount": "0"},
            headers=head_headers,
        )
    ).json()
    assert approved["status"] == "approved"
    assert Decimal(approved["earned_amount"]) == Decimal("0")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_payment_does_not_duplicate_journal_entry(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="8.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "8.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    payload = {"payment_account_id": cash["id"], "expense_account_id": expense["id"]}

    first = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment", json=payload, headers=head_headers
    )
    second = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment", json=payload, headers=head_headers
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["payment_journal_entry_id"] == second.json()["payment_journal_entry_id"]

    entry_id = first.json()["payment_journal_entry_id"]
    await set_tenant_context_async(db, org_id)
    count = await count_rows(db, JournalEntry, JournalEntry.id == entry_id)
    assert count == 1


# ---------------------------------------------------------------------------
# Account validation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_rejects_payment_account_from_another_tenant(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_user, other_password = await create_test_user(db, other_org)
    other_headers = await auth_headers_for(client, other_user.email, other_password)
    other_cash = await _create_account(client, other_headers, unique("CASH"), "Cash", "Asset")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": other_cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rejects_expense_account_from_another_tenant(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")
    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_user, other_password = await create_test_user(db, other_org)
    other_headers = await auth_headers_for(client, other_user.email, other_password)
    other_expense = await _create_account(client, other_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": other_expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rejects_non_asset_payment_account(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    not_asset = await _create_account(client, head_headers, unique("EXP2"), "Not Asset", "Expense")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": not_asset["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rejects_non_expense_expense_account(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    not_expense = await _create_account(client, head_headers, unique("CASH2"), "Not Expense", "Asset")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": not_expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_use_any_tenant_account_for_payment(client, db, unique):
    """HEAD/PARENT already have full account access (FAM-1301); a private
    account owned by another member does not block allowance payment
    posting, matching the same elevated-role rule used everywhere else
    (bills, subscriptions, budgets, goal contributions)."""
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    teen_headers_for_account = teen_headers
    private_cash = await _create_account(client, teen_headers_for_account, unique("PRIV"), "Teen Private Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": private_cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_cannot_post_payment(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=teen_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_cannot_post_payment(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(db, org, email=unique("child") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, child, "child")
    child_headers = await auth_headers_for(client, child.email, child_password)

    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, child_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=child_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_post_payment(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")
    member = await _add_member(client, head_headers, teen, "teen")
    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    teen_headers = await auth_headers_for(client, teen.email, teen_password)

    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=viewer_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_unrelated_adult_cannot_post_payment(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")
    member = await _add_member(client, head_headers, teen, "teen")
    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    teen_headers = await auth_headers_for(client, teen.email, teen_password)

    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=adult_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_post_payment(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")
    member = await _add_member(client, head_headers, teen, "teen")
    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    teen_headers = await auth_headers_for(client, teen.email, teen_password)

    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, parent_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, parent_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=parent_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["payment_status"] == "paid"


# ---------------------------------------------------------------------------
# Reversal
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reverse_payment_creates_balanced_reversal_journal_entry(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    paid = (
        await client.post(
            f"/family/chore-completions/{approved['id']}/post-payment",
            json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
            headers=head_headers,
        )
    ).json()

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["payment_status"] == "reversed"
    assert data["payment_reversal_journal_entry_id"] is not None
    assert data["payment_journal_entry_id"] == paid["payment_journal_entry_id"]

    await set_tenant_context_async(db, org_id)
    result = await db.execute(
        JournalLine.__table__.select().where(
            JournalLine.journal_entry_id == data["payment_reversal_journal_entry_id"]
        )
    )
    lines = result.fetchall()
    assert len(lines) == 2
    total_debit = sum(Decimal(str(l.debit)) for l in lines)
    total_credit = sum(Decimal(str(l.credit)) for l in lines)
    assert total_debit == total_credit == Decimal("6.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_original_payment_journal_entry_unchanged_after_reversal(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    paid = (
        await client.post(
            f"/family/chore-completions/{approved['id']}/post-payment",
            json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
            headers=head_headers,
        )
    ).json()
    original_id = paid["payment_journal_entry_id"]

    await client.post(f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers)

    await set_tenant_context_async(db, org_id)
    result = await db.execute(
        JournalLine.__table__.select().where(JournalLine.journal_entry_id == original_id)
    )
    lines = result.fetchall()
    assert len(lines) == 2
    expense_line = next(l for l in lines if l.account_id == expense["id"])
    cash_line = next(l for l in lines if l.account_id == cash["id"])
    assert expense_line.debit == Decimal("6.000")
    assert cash_line.credit == Decimal("6.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_reversal_does_not_duplicate(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    first = await client.post(
        f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    second = await client.post(
        f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["payment_reversal_journal_entry_id"] == second.json()["payment_reversal_journal_entry_id"]

    reversal_id = first.json()["payment_reversal_journal_entry_id"]
    await set_tenant_context_async(db, org_id)
    count = await count_rows(db, JournalEntry, JournalEntry.id == reversal_id)
    assert count == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_cannot_reverse_unpaid_completion(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_reverse_tenant_b_payment(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/reverse-payment", headers=other_headers
    )
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Allowance summary
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_allowance_summary_approved_unpaid_amount(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="7.000")
    )
    await _approve_via_api(client, head_headers, chore, teen_headers, "7.000")

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["approved_unpaid_amount"]) == Decimal("7.000")
    assert Decimal(summary["paid_amount"]) == Decimal("0")
    assert Decimal(summary["approved_earned_amount"]) == Decimal("7.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_allowance_summary_paid_amount(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="7.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "7.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["paid_amount"]) == Decimal("7.000")
    assert Decimal(summary["approved_unpaid_amount"]) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_allowance_summary_reversed_amount(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="7.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "7.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    await client.post(f"/family/chore-completions/{approved['id']}/reverse-payment", headers=head_headers)

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["reversed_amount"]) == Decimal("7.000")
    assert Decimal(summary["paid_amount"]) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_allowance_summary_per_member_scoping(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen_a, teen_a_password = await create_test_user(
        db, org, email=unique("teen_a") + "@example.com", role="viewer"
    )
    teen_b, teen_b_password = await create_test_user(
        db, org, email=unique("teen_b") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member_a = await _add_member(client, head_headers, teen_a, "teen")
    member_b = await _add_member(client, head_headers, teen_b, "teen")
    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)

    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], allowance_amount="4.000")
    )
    chore_b = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"], allowance_amount="9.000")
    )
    approved_a = await _approve_via_api(client, head_headers, chore_a, teen_a_headers, "4.000")
    await _approve_via_api(client, head_headers, chore_b, teen_b_headers, "9.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved_a['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    summary_a = (await client.get("/family/allowance-summary", headers=teen_a_headers)).json()
    assert Decimal(summary_a["paid_amount"]) == Decimal("4.000")
    assert Decimal(summary_a["approved_unpaid_amount"]) == Decimal("0")
    member_ids_a = {m["member_id"] for m in summary_a["by_member"]}
    assert member_ids_a == {member_a["id"]}

    summary_head = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    by_member = {m["member_id"]: m for m in summary_head["by_member"]}
    assert Decimal(by_member[member_a["id"]]["paid_amount"]) == Decimal("4.000")
    assert Decimal(by_member[member_b["id"]]["approved_unpaid_amount"]) == Decimal("9.000")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_remains_safe_after_approval_and_payment(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    response = await client.get("/dashboard/", headers=head_headers)
    assert response.status_code == 200, response.text
    assert "Chores" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_ready_to_pay_badge_shown_without_payment_form(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ready_to_pay_count"] == 1
    assert data["permissions"]["can_post_payment"] is True

    widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert widget.status_code == 200, widget.text
    assert "ready to pay" in widget.text
    # No account-selecting payment form/inputs on the dashboard — the
    # dashboard never silently chooses payment/expense accounts.
    assert "payment_account_id" not in widget.text
    assert "expense_account_id" not in widget.text
    assert "post-payment" not in widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_no_silent_account_guessing_for_teen(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    response = await client.get("/dashboard/api/family-chores", headers=teen_headers)
    assert response.status_code == 200, response.text
    # Teen cannot post payment; ready_to_pay_count reflects their own scope
    # but the permission flag must be false so no action is offered.
    assert response.json()["permissions"]["can_post_payment"] is False


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_pay_tenant_b_completion(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)
    other_cash = await _create_account(client, other_headers, unique("CASH"), "Cash", "Asset")
    other_expense = await _create_account(client, other_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": other_cash["id"], "expense_account_id": other_expense["id"]},
        headers=other_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_accounts(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_user, other_password = await create_test_user(db, other_org)
    other_headers = await auth_headers_for(client, other_user.email, other_password)
    other_cash = await _create_account(client, other_headers, unique("CASH"), "Cash", "Asset")
    other_expense = await _create_account(client, other_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": other_cash["id"], "expense_account_id": other_expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_payment_related_tables(db):
    await assert_rls_enabled(db, "family_chore_completions")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
