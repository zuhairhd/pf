"""Allowance Payment Reversal Dashboard Action tests (DB-1107C).

Covers the dashboard "Reverse Payment" action: POST
/dashboard/partials/family-chore-completions/{id}/reverse-payment,
which reuses FamilyChoreService.reverse_payment() (FAM-1305) unchanged —
itself delegating entirely to AccountingService.reverse_journal_entry()
(ACC-503A). Also covers the Recent Payments template's Reverse button
visibility, idempotency, permission gating, read-only browsing safety,
and tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import Account, Goal, JournalEntry, JournalLine
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


async def _paid_completion(client, db, unique, allowance_amount="10.000"):
    """Full setup: head/teen/family/chore/approved+paid completion.

    Returns (head_headers, teen_headers, paid_completion_dict, org_id, cash, expense).
    """
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount=allowance_amount)
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, allowance_amount)

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    paid_response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert paid_response.status_code == 200, paid_response.text

    return head_headers, teen_headers, approved, org_id, cash, expense


# ---------------------------------------------------------------------------
# Route / auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reverse_route_requires_auth(client):
    response = await client.post("/dashboard/partials/family-chore-completions/1/reverse-payment")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_reverse_payment_from_dashboard(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "6.000")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert response.status_code == 200, response.text
    assert "Reversed" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_reverse_payment(client, db, unique):
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
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "6.000")
    cash = await _create_account(client, parent_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, parent_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=parent_headers,
    )

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=parent_headers
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_cannot_reverse_payment(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=teen_headers
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_cannot_reverse_payment(client, db, unique):
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
    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=child_headers
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_reverse_payment(client, db, unique):
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
    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=viewer_headers
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_reverse_attempt_rejected_safely(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=other_headers
    )
    assert response.status_code in (400, 403, 404), response.text

    # No reversal actually happened — the original completion is still paid.
    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    assert completion["payment_status"] == "paid"
    assert completion["payment_reversal_journal_entry_id"] is None


# ---------------------------------------------------------------------------
# Template behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_paid_completion_shows_reverse_button_for_head(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert widget.status_code == 200, widget.text
    assert "Reverse" in widget.text
    assert f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment" in widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversed_completion_does_not_show_reverse_button(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )

    widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert widget.status_code == 200, widget.text
    assert f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment" not in widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_role_does_not_see_reverse_button(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    teen_widget = await client.get("/dashboard/partials/family-chores", headers=teen_headers)
    assert teen_widget.status_code == 200, teen_widget.text
    assert f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment" not in teen_widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversed_status_appears_after_reversal(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )

    widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert widget.status_code == 200, widget.text
    assert "Reversed" in widget.text

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["reversed_amount"]) == Decimal("5.000")
    assert Decimal(summary["paid_amount"]) == Decimal("0")


# ---------------------------------------------------------------------------
# Reversal behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_reverse_creates_balanced_reversal_journal_entry(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "7.000")

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )

    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    assert completion["payment_status"] == "reversed"
    reversal_id = completion["payment_reversal_journal_entry_id"]
    assert reversal_id is not None

    await set_tenant_context_async(db, org_id)
    result = await db.execute(
        JournalLine.__table__.select().where(JournalLine.journal_entry_id == reversal_id)
    )
    lines = result.fetchall()
    assert len(lines) == 2
    total_debit = sum(Decimal(str(l.debit)) for l in lines)
    total_credit = sum(Decimal(str(l.credit)) for l in lines)
    assert total_debit == total_credit == Decimal("7.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_original_payment_journal_entry_unchanged_after_dashboard_reversal(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "7.000")

    completions_before = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    original_id = next(c for c in completions_before if c["id"] == approved["id"])["payment_journal_entry_id"]

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )

    await set_tenant_context_async(db, org_id)
    result = await db.execute(
        JournalLine.__table__.select().where(JournalLine.journal_entry_id == original_id)
    )
    lines = result.fetchall()
    assert len(lines) == 2
    expense_line = next(l for l in lines if l.account_id == expense["id"])
    cash_line = next(l for l in lines if l.account_id == cash["id"])
    assert expense_line.debit == Decimal("7.000")
    assert cash_line.credit == Decimal("7.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_dashboard_reverse_does_not_duplicate(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "6.000")

    first = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    second = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    reversal_id = completion["payment_reversal_journal_entry_id"]

    await set_tenant_context_async(db, org_id)
    count = await count_rows(db, JournalEntry, JournalEntry.id == reversal_id)
    assert count == 1

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["reversed_amount"]) == Decimal("6.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_cannot_reverse_unpaid_completion_from_dashboard(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="5.000")
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )
    assert response.status_code == 400, response.text

    completions = (
        await client.get(f"/family/chores/{chore['id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    assert completion["payment_status"] == "unpaid"
    assert completion["payment_reversal_journal_entry_id"] is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_cannot_reverse_completion_without_payment_journal_entry(client, db, unique):
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="0.000")
    )
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    # Rejecting leaves earned_amount at 0 and status "rejected" — never paid,
    # so payment_journal_entry_id is never set.
    await client.post(
        f"/family/chore-completions/{completion['id']}/reject",
        json={"rejection_reason": "Not done properly"},
        headers=head_headers,
    )

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{completion['id']}/reverse-payment", headers=head_headers
    )
    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_view_creates_no_reversal(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    for _ in range(3):
        await client.get("/dashboard/", headers=head_headers)
        await client.get("/dashboard/api/family-chores", headers=head_headers)
        await client.get("/dashboard/partials/family-chores", headers=head_headers)

    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    assert completion["payment_status"] == "paid"
    assert completion["payment_reversal_journal_entry_id"] is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_reverse_does_not_modify_accounts_or_goals(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    await set_tenant_context_async(db, org_id)
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=head_headers
    )

    await set_tenant_context_async(db, org_id)
    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_reverse_tenant_b_completion_from_dashboard(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment", headers=other_headers
    )
    assert response.status_code != 200, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_reverse_control(client, db, unique):
    head_headers, teen_headers, approved, org_id, cash, expense = await _paid_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)

    widget = await client.get("/dashboard/partials/family-chores", headers=other_headers)
    assert widget.status_code == 200, widget.text
    assert f"/dashboard/partials/family-chore-completions/{approved['id']}/reverse-payment" not in widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_reversal_related_tables(db):
    await assert_rls_enabled(db, "family_chore_completions")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
