"""Allowance and Chore Dashboard Widget tests (DB-1107A).

Covers /dashboard/api/family-chores, the /dashboard/partials/family-chores
HTMX widget, permission-aware visibility (HEAD/PARENT/TEEN/CHILD/VIEWER),
allowance summary calculation, empty states, HTMX quick actions
(submit-completion, approve-completion), read-only financial safety, and
tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

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


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_requires_auth(client):
    response = await client.get("/dashboard/api/family-chores")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_returns_expected_sections(client, auth_headers):
    response = await client.get("/dashboard/api/family-chores", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    for key in (
        "assigned_chores",
        "overdue_chores",
        "pending_approvals",
        "allowance_summary",
        "due_soon_count",
        "overdue_count",
        "pending_approvals_count",
        "currency",
        "permissions",
    ):
        assert key in data


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_returns_assigned_due_soon_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")

    due_soon = (date.today() + timedelta(days=2)).isoformat()
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], due_date=due_soon)
    )

    response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    ids = {c["id"] for c in data["assigned_chores"]}
    assert chore["id"] in ids
    assert data["due_soon_count"] >= 1
    item = next(c for c in data["assigned_chores"] if c["id"] == chore["id"])
    assert item["is_due_soon"] is True
    assert item["is_overdue"] is False
    assert item["assigned_to_name"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_returns_overdue_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)

    overdue_date = (date.today() - timedelta(days=1)).isoformat()
    chore = await _create_chore(client, head_headers, _chore_payload(due_date=overdue_date))

    response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    ids = {c["id"] for c in data["overdue_chores"]}
    assert chore["id"] in ids
    assert data["overdue_count"] >= 1
    item = next(c for c in data["overdue_chores"] if c["id"] == chore["id"])
    assert item["is_overdue"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_pending_approvals_for_head(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    ids = {c["id"] for c in data["pending_approvals"]}
    assert completion["id"] in ids
    assert data["pending_approvals_count"] >= 1
    item = next(c for c in data["pending_approvals"] if c["id"] == completion["id"])
    assert item["can_approve"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_api_allowance_summary_reflects_approval(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="8.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=head_headers
    )

    response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    summary = response.json()["allowance_summary"]
    assert Decimal(summary["approved_earned_amount"]) == Decimal("8.000")
    assert Decimal(summary["approved_this_month_amount"]) == Decimal("8.000")


# ---------------------------------------------------------------------------
# Dashboard partial (HTMX)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_partial_requires_auth(client):
    response = await client.get("/dashboard/partials/family-chores")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_widget_renders_on_page(client, auth_headers):
    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "Chores" in response.text
    # Existing sections must still render.
    assert "Bills & Subscriptions" in response.text
    assert "Family Goals" in response.text
    assert "Family Budgets" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_widget_empty_state(client, auth_headers):
    response = await client.get("/dashboard/partials/family-chores", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert "No chores due soon or overdue" in response.text
    assert "No completions awaiting approval" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_widget_shows_allowance_summary(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="12.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=head_headers
    )

    response = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    assert "Allowance Summary" in response.text
    assert "12.000" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_family_chores_widget_shows_pending_approvals(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)

    response = await client.get("/dashboard/partials/family-chores", headers=head_headers)
    assert response.status_code == 200, response.text
    assert "Approve" in response.text
    assert chore["title"] in response.text


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_and_parent_see_all_chores_and_approvals(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )
    teen_a, teen_a_password = await create_test_user(
        db, org, email=unique("teen_a") + "@example.com", role="viewer"
    )
    teen_b, teen_b_password = await create_test_user(
        db, org, email=unique("teen_b") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")
    member_a = await _add_member(client, head_headers, teen_a, "teen")
    member_b = await _add_member(client, head_headers, teen_b, "teen")

    overdue_date = (date.today() - timedelta(days=1)).isoformat()
    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], due_date=overdue_date)
    )
    chore_b = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"], due_date=overdue_date)
    )

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    completion_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    await client.post(f"/family/chores/{chore_a['id']}/completions", json={}, headers=teen_a_headers)
    await client.post(f"/family/chores/{chore_b['id']}/completions", json={}, headers=completion_b_headers)

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    response = await client.get("/dashboard/api/family-chores", headers=parent_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    overdue_ids = {c["id"] for c in data["overdue_chores"]}
    assert chore_a["id"] in overdue_ids
    assert chore_b["id"] in overdue_ids
    assert data["pending_approvals_count"] == 2


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_sees_only_own_assigned_chores(client, db, unique):
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

    due_soon = (date.today() + timedelta(days=1)).isoformat()
    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], due_date=due_soon)
    )
    chore_b = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"], due_date=due_soon)
    )

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    response = await client.get("/dashboard/api/family-chores", headers=teen_a_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    ids = {c["id"] for c in data["assigned_chores"]}
    assert chore_a["id"] in ids
    assert chore_b["id"] not in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_sees_only_own_assigned_chores(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(db, org, email=unique("child") + "@example.com", role="viewer")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member_child = await _add_member(client, head_headers, child, "child")
    member_teen = await _add_member(client, head_headers, teen, "teen")

    due_soon = (date.today() + timedelta(days=1)).isoformat()
    chore_child = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_child["id"], due_date=due_soon)
    )
    chore_teen = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_teen["id"], due_date=due_soon)
    )

    child_headers = await auth_headers_for(client, child.email, child_password)
    response = await client.get("/dashboard/api/family-chores", headers=child_headers)
    assert response.status_code == 200, response.text
    ids = {c["id"] for c in response.json()["assigned_chores"]}
    assert chore_child["id"] in ids
    assert chore_teen["id"] not in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_has_no_action_buttons(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    due_soon = (date.today() + timedelta(days=1)).isoformat()
    await _create_chore(client, head_headers, _chore_payload(due_date=due_soon))

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.get("/dashboard/partials/family-chores", headers=viewer_headers)
    assert response.status_code == 200, response.text
    assert "Mark Complete" not in response.text
    assert "/complete\"" not in response.text
    assert "/dashboard/partials/family-chore-completions" not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_submit_action_only_for_assigned_member(client, db, unique):
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
    await _add_member(client, head_headers, teen_b, "teen")

    due_soon = (date.today() + timedelta(days=1)).isoformat()
    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], due_date=due_soon)
    )

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)

    response_a = await client.get("/dashboard/api/family-chores", headers=teen_a_headers)
    item_a = next(c for c in response_a.json()["assigned_chores"] if c["id"] == chore_a["id"])
    assert item_a["can_submit"] is True

    response_b = await client.get("/dashboard/api/family-chores", headers=teen_b_headers)
    assert response_b.json()["assigned_chores"] == []


@pytest.mark.integration
@pytest.mark.anyio
async def test_approve_action_only_for_head_parent(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)

    teen_response = await client.get("/dashboard/api/family-chores", headers=teen_headers)
    for item in teen_response.json()["pending_approvals"]:
        assert item["can_approve"] is False

    head_response = await client.get("/dashboard/api/family-chores", headers=head_headers)
    for item in head_response.json()["pending_approvals"]:
        assert item["can_approve"] is True


# ---------------------------------------------------------------------------
# HTMX quick actions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_submit_completion_quick_action(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    before = await client.get(f"/family/chores/{chore['id']}/completions", headers=head_headers)
    completions_before = len(before.json())

    response = await client.post(
        f"/dashboard/partials/family-chores/{chore['id']}/complete", headers=teen_headers
    )
    assert response.status_code == 200, response.text

    after = await client.get(f"/family/chores/{chore['id']}/completions", headers=head_headers)
    assert len(after.json()) == completions_before + 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_approve_completion_quick_action(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="9.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{completion['id']}/approve", headers=head_headers
    )
    assert response.status_code == 200, response.text

    detail = await client.get("/family/allowance-summary", headers=head_headers)
    assert Decimal(detail.json()["approved_earned_amount"]) == Decimal("9.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_dashboard_refresh_creates_no_completions(client, db, auth_headers):
    await _create_family(client, auth_headers)
    chore = await _create_chore(client, auth_headers, _chore_payload())

    before = await client.get(f"/family/chores/{chore['id']}/completions", headers=auth_headers)
    completions_before = len(before.json())

    for _ in range(3):
        await client.get("/dashboard/partials/family-chores", headers=auth_headers)
        await client.get("/dashboard/api/family-chores", headers=auth_headers)

    after = await client.get(f"/family/chores/{chore['id']}/completions", headers=auth_headers)
    assert len(after.json()) == completions_before


# ---------------------------------------------------------------------------
# Safety: read-only, no unauthorized mutation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_widget_creates_no_financial_records(client, auth_headers, db):
    await _create_family(client, auth_headers)
    await _create_chore(client, auth_headers, _chore_payload(allowance_amount="15.000"))

    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)

    await client.get("/dashboard/", headers=auth_headers)
    await client.get("/dashboard/api/family-chores", headers=auth_headers)
    await client.get("/dashboard/partials/family-chores", headers=auth_headers)

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, JournalEntry) == journals_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_member_cannot_submit_another_members_chore_from_dashboard(client, db, unique):
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
    await _add_member(client, head_headers, teen_b, "teen")
    chore_a = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"]))

    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    before = await client.get(f"/family/chores/{chore_a['id']}/completions", headers=head_headers)
    completions_before = len(before.json())

    response = await client.post(
        f"/dashboard/partials/family-chores/{chore_a['id']}/complete", headers=teen_b_headers
    )
    assert response.status_code == 400, response.text

    after = await client.get(f"/family/chores/{chore_a['id']}/completions", headers=head_headers)
    assert len(after.json()) == completions_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_member_cannot_approve_from_dashboard(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    response = await client.post(
        f"/dashboard/partials/family-chore-completions/{completion['id']}/approve", headers=teen_headers
    )
    assert response.status_code == 400, response.text

    detail = await client.get("/family/allowance-summary", headers=head_headers)
    assert Decimal(detail.json()["pending_approval_amount"]) > Decimal("0")


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_chores_on_dashboard(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    due_soon = (date.today() + timedelta(days=1)).isoformat()
    chore_a = await _create_chore(client, headers_a, _chore_payload(due_date=due_soon))

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    response_b = await client.get("/dashboard/api/family-chores", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    ids_b = {c["id"] for c in response_b.json()["assigned_chores"]}
    assert chore_a["id"] not in ids_b

    dashboard_b = await client.get("/dashboard/", headers=headers_b)
    assert chore_a["title"] not in dashboard_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_chore_tables_via_dashboard(db):
    await assert_rls_enabled(db, "family_chores")
    await assert_rls_enabled(db, "family_chore_completions")
