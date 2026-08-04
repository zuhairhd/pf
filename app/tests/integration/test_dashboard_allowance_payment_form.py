"""Allowance Payment Dashboard Action Form tests (DB-1107B).

Covers the inline dashboard payment form: GET
/dashboard/partials/family-chore-completions/{id}/payment-form (renders
the account-picker form for one approved unpaid completion) and POST
.../post-payment (submits the explicitly-chosen accounts and posts
through FamilyChoreService.post_payment(), unchanged from FAM-1305).
Also covers form rendering permissions, account-picker filtering, HTMX
success/error behavior, idempotency, read-only safety while browsing,
and tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import Account, Goal, JournalEntry
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


async def _approved_completion(client, db, unique, allowance_amount="10.000"):
    """Full setup: head/teen/family/chore/approved completion. Returns (head_headers, teen_headers, approved, org_id)."""
    head_headers, teen_headers, member, org_id = await _setup_head_and_teen(client, db, unique)
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount=allowance_amount)
    )
    approved = await _approve_via_api(client, head_headers, chore, teen_headers, allowance_amount)
    return head_headers, teen_headers, approved, org_id


# ---------------------------------------------------------------------------
# Form rendering
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_payment_form_requires_auth(client):
    response = await client.get("/dashboard/partials/family-chore-completions/1/payment-form")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_open_payment_form_for_approved_unpaid_completion(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "8.000")

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=head_headers
    )
    assert response.status_code == 200, response.text
    assert "Wash dishes" in response.text
    assert "8.000" in response.text
    assert 'name="payment_account_id"' in response.text
    assert 'name="expense_account_id"' in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_open_payment_form(client, db, unique):
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

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=parent_headers
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_cannot_open_payment_form(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "8.000")

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=teen_headers
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_cannot_open_payment_form(client, db, unique):
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

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=child_headers
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_open_payment_form(client, db, unique):
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

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=viewer_headers
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_form_includes_only_asset_accounts_in_payment_select(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("EXP"), "Household Expense", "Expense")

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=head_headers
    )
    assert response.status_code == 200, response.text
    # The Expense account must not be offered as a payment (Asset) option.
    payment_select_start = response.text.find('name="payment_account_id"')
    payment_select_end = response.text.find("</select>", payment_select_start)
    payment_select_html = response.text[payment_select_start:payment_select_end]
    assert expense["name"] not in payment_select_html


@pytest.mark.integration
@pytest.mark.anyio
async def test_form_includes_only_expense_accounts_in_expense_select(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    await _create_account(client, head_headers, unique("EXP"), "Household Expense", "Expense")

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=head_headers
    )
    assert response.status_code == 200, response.text
    expense_select_start = response.text.find('name="expense_account_id"')
    expense_select_html = response.text[expense_select_start:]
    assert cash["name"] not in expense_select_html


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_account_names_do_not_appear_in_form(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_user, other_password = await create_test_user(db, other_org)
    other_headers = await auth_headers_for(client, other_user.email, other_password)
    other_account = await _create_account(client, other_headers, unique("SECRET"), "Other Tenant Secret Cash", "Asset")

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=head_headers
    )
    assert response.status_code == 200, response.text
    assert other_account["name"] not in response.text


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_post_payment_from_dashboard_form(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "9.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("HX-Retarget") == "#family-chores-widget"
    assert "Paid" in response.text

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["paid_amount"]) == Decimal("9.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_payment_creates_balanced_journal_entry(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "7.500")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])
    assert completion["payment_status"] == "paid"
    assert completion["payment_journal_entry_id"] is not None

    await set_tenant_context_async(db, org_id)
    count = await count_rows(db, JournalEntry, JournalEntry.id == completion["payment_journal_entry_id"])
    assert count == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_dashboard_post_does_not_duplicate_journal_entry(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "6.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")
    payload = {"payment_account_id": cash["id"], "expense_account_id": expense["id"]}

    first = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data=payload, headers=head_headers,
    )
    second = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data=payload, headers=head_headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    completions = (
        await client.get(f"/family/chores/{approved['chore_id']}/completions", headers=head_headers)
    ).json()
    completion = next(c for c in completions if c["id"] == approved["id"])

    await set_tenant_context_async(db, org_id)
    count = await count_rows(db, JournalEntry, JournalEntry.id == completion["payment_journal_entry_id"])
    assert count == 1

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["paid_amount"]) == Decimal("6.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_already_paid_completion_returns_safe_response(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "4.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    # Pay through the plain API first (FAM-1305 path).
    await client.post(
        f"/family/chore-completions/{approved['id']}/post-payment",
        json={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_unapproved_completion_cannot_be_paid_from_dashboard(client, db, unique):
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
        f"/dashboard/partials/family-chore-completions/{completion['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text
    assert "HX-Retarget" not in response.headers


@pytest.mark.integration
@pytest.mark.anyio
async def test_missing_account_fields_rejected(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text
    assert "select both" in response.text.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_non_asset_payment_account_rejected(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    not_asset = await _create_account(client, head_headers, unique("EXP2"), "Not Asset", "Expense")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": not_asset["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_non_expense_expense_account_rejected(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    not_expense = await _create_account(client, head_headers, unique("CASH2"), "Not Expense", "Asset")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": not_expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_accounts_rejected_on_post(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_user, other_password = await create_test_user(db, other_org)
    other_headers = await auth_headers_for(client, other_user.email, other_password)
    other_cash = await _create_account(client, other_headers, unique("CASH"), "Cash", "Asset")
    other_expense = await _create_account(client, other_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": other_cash["id"], "expense_account_id": other_expense["id"]},
        headers=head_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_cannot_post_payment_from_dashboard_form(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=teen_headers,
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_ready_to_pay_button_appears_only_for_head_parent(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    head_widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert head_widget.status_code == 200, head_widget.text
    assert "Post Payment" in head_widget.text
    assert "Ready to Pay" in head_widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_ready_to_pay_button_does_not_appear_for_teen(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    teen_widget = await client.get("/dashboard/partials/family-chores", headers=teen_headers)
    assert teen_widget.status_code == 200, teen_widget.text
    assert "Post Payment" not in teen_widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_ready_to_pay_button_does_not_appear_for_viewer(client, db, unique):
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
    await _approve_via_api(client, head_headers, chore, teen_headers, "5.000")

    viewer_widget = await client.get("/dashboard/partials/family-chores", headers=viewer_headers)
    assert viewer_widget.status_code == 200, viewer_widget.text
    assert "Post Payment" not in viewer_widget.text
    assert "Ready to Pay" not in viewer_widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_widget_updates_after_payment(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    before = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert "Nothing ready to pay" not in before.text

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    after = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert after.status_code == 200, after.text
    assert "Nothing ready to pay" in after.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_paid_status_appears_after_payment(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    cash = await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    expense = await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": cash["id"], "expense_account_id": expense["id"]},
        headers=head_headers,
    )

    widget = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert "Paid" in widget.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewing_dashboard_and_opening_form_creates_no_journal_entries(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")
    await _create_account(client, head_headers, unique("CASH"), "Cash", "Asset")
    await _create_account(client, head_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    await set_tenant_context_async(db, org_id)
    journals_before = await count_rows(db, JournalEntry)
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)

    await client.get("/dashboard/", headers=head_headers)
    await client.get("/dashboard/api/family-chores", headers=head_headers)
    await client.get("/dashboard/partials/family-chores", headers=head_headers)
    await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=head_headers
    )

    await set_tenant_context_async(db, org_id)
    assert await count_rows(db, JournalEntry) == journals_before
    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_open_payment_form_for_tenant_b_completion(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)

    response = await client.get(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/payment-form", headers=other_headers
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_post_payment_for_tenant_b_completion(client, db, unique):
    head_headers, teen_headers, approved, org_id = await _approved_completion(client, db, unique, "5.000")

    other_org = await create_test_organization(db, name=unique("Other Org"), slug=unique("other-org"))
    other_head, other_password = await create_test_user(
        db, other_org, email=unique("other_head") + "@example.com", role="owner"
    )
    other_headers = await auth_headers_for(client, other_head.email, other_password)
    await _create_family(client, other_headers)
    other_cash = await _create_account(client, other_headers, unique("CASH"), "Cash", "Asset")
    other_expense = await _create_account(client, other_headers, unique("ALLOW"), "Allowance Expense", "Expense")

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{approved['id']}/post-payment",
        data={"payment_account_id": other_cash["id"], "expense_account_id": other_expense["id"]},
        headers=other_headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_payment_related_tables_via_dashboard_form(db):
    await assert_rls_enabled(db, "family_chore_completions")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
