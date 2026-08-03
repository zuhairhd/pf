"""Family chores and allowance tracking tests (FAM-1304).

Covers chore CRUD, completion submission/approval/rejection, allowance
summary calculation, role-based permissions, tenant/RLS isolation, and
read-only financial safety. Uses synthetic data only.
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
# Chores: CRUD + permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_chore_requires_auth(client):
    response = await client.post("/family/chores", json=_chore_payload())
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_create_chore(client, auth_headers):
    await _create_family(client, auth_headers)
    chore = await _create_chore(client, auth_headers, _chore_payload())
    assert chore["title"] == "Wash dishes"
    assert chore["status"] == "active"
    assert chore["can_manage"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_create_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    chore = await _create_chore(client, parent_headers, _chore_payload())
    assert chore["created_by_user_id"] == parent.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_cannot_create_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, teen, "teen")

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    response = await client.post("/family/chores", json=_chore_payload(), headers=teen_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_cannot_create_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(db, org, email=unique("child") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, child, "child")

    child_headers = await auth_headers_for(client, child.email, child_password)
    response = await client.post("/family/chores", json=_chore_payload(), headers=child_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_create_chore(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post("/family/chores", json=_chore_payload(), headers=viewer_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_cannot_create_chore(client, db, unique):
    """No elevated permission flag exists yet for chores; adult defaults to no."""
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post("/family/chores", json=_chore_payload(), headers=adult_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_chores_filters_by_assigned_member(client, db, unique):
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

    chore_a = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"]))
    chore_b = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"]))

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    response = await client.get("/family/chores", headers=teen_a_headers)
    assert response.status_code == 200, response.text
    ids = {c["id"] for c in response.json()}
    assert chore_a["id"] in ids
    assert chore_b["id"] not in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_list_sees_all_chores(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")

    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))
    unassigned = await _create_chore(client, head_headers, _chore_payload())

    response = await client.get("/family/chores", headers=head_headers)
    ids = {c["id"] for c in response.json()}
    assert chore["id"] in ids
    assert unassigned["id"] in ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_chore_rejects_unauthorized_teen(client, db, unique):
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

    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"]))

    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    response = await client.get(f"/family/chores/{chore['id']}", headers=teen_b_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_chore_requires_permission(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    forbidden = await client.patch(
        f"/family/chores/{chore['id']}", json={"title": "Hijacked"}, headers=teen_headers
    )
    assert forbidden.status_code == 403

    allowed = await client.patch(
        f"/family/chores/{chore['id']}", json={"title": "Wash and dry dishes"}, headers=head_headers
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["title"] == "Wash and dry dishes"


@pytest.mark.integration
@pytest.mark.anyio
async def test_archive_chore_requires_permission(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    forbidden = await client.post(f"/family/chores/{chore['id']}/archive", headers=teen_headers)
    assert forbidden.status_code == 403

    allowed = await client.post(f"/family/chores/{chore['id']}/archive", headers=head_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "archived"


# ---------------------------------------------------------------------------
# Completions: submit / approve / reject
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_assigned_teen_can_submit_completion(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    response = await client.post(
        f"/family/chores/{chore['id']}/completions",
        json={"submitted_notes": "Done!"},
        headers=teen_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "submitted"
    assert data["completed_by_member_id"] == member["id"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_assigned_child_can_submit_completion(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(db, org, email=unique("child") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, child, "child")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    child_headers = await auth_headers_for(client, child.email, child_password)
    response = await client.post(
        f"/family/chores/{chore['id']}/completions", json={}, headers=child_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submitted"


@pytest.mark.integration
@pytest.mark.anyio
async def test_unassigned_member_cannot_submit_completion(client, db, unique):
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
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"]))

    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    response = await client.post(
        f"/family/chores/{chore['id']}/completions", json={}, headers=teen_b_headers
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_submit_completion(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, viewer, "viewer")
    chore = await _create_chore(client, head_headers, _chore_payload(assigned_to_member_id=member["id"]))

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post(
        f"/family/chores/{chore['id']}/completions", json={}, headers=viewer_headers
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_and_parent_can_approve_completion(client, db, unique):
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
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="7.500")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    response = await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=parent_headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "approved"
    assert Decimal(data["earned_amount"]) == Decimal("7.500")
    assert data["approved_by_user_id"] == parent.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_child_viewer_cannot_approve(client, db, unique):
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

    # Teen tries to approve their own completion.
    response = await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=teen_headers
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_reject_stores_reason(client, db, unique):
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
        f"/family/chore-completions/{completion['id']}/reject",
        json={"rejection_reason": "Dishes still dirty"},
        headers=head_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "Dishes still dirty"
    assert Decimal(data["earned_amount"]) == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_reject_without_reason_fails(client, db, unique):
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
        f"/family/chore-completions/{completion['id']}/reject", json={}, headers=head_headers
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Allowance summary
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_approved_amount_calculated_correctly(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="10.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()
    await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=head_headers
    )

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["approved_earned_amount"]) == Decimal("10.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_pending_approval_amount_calculated_correctly(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="6.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    assert Decimal(summary["pending_approval_amount"]) == Decimal("6.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_teen_sees_own_summary_only(client, db, unique):
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

    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], allowance_amount="4.000")
    )
    chore_b = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"], allowance_amount="9.000")
    )

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    completion_a = (
        await client.post(f"/family/chores/{chore_a['id']}/completions", json={}, headers=teen_a_headers)
    ).json()
    await client.post(f"/family/chores/{chore_b['id']}/completions", json={}, headers=teen_b_headers)

    await client.post(
        f"/family/chore-completions/{completion_a['id']}/approve", json={}, headers=head_headers
    )

    summary_a = (await client.get("/family/allowance-summary", headers=teen_a_headers)).json()
    assert Decimal(summary_a["approved_earned_amount"]) == Decimal("4.000")
    assert Decimal(summary_a["pending_approval_amount"]) == Decimal("0")
    member_ids_a = {m["member_id"] for m in summary_a["by_member"]}
    assert member_ids_a == {member_a["id"]}


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_parent_sees_all_in_summary(client, db, unique):
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

    chore_a = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_a["id"], allowance_amount="4.000")
    )
    chore_b = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member_b["id"], allowance_amount="9.000")
    )

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    teen_b_headers = await auth_headers_for(client, teen_b.email, teen_b_password)
    await client.post(f"/family/chores/{chore_a['id']}/completions", json={}, headers=teen_a_headers)
    await client.post(f"/family/chores/{chore_b['id']}/completions", json={}, headers=teen_b_headers)

    summary = (await client.get("/family/allowance-summary", headers=head_headers)).json()
    member_ids = {m["member_id"] for m in summary["by_member"]}
    assert member_a["id"] in member_ids
    assert member_b["id"] in member_ids
    assert Decimal(summary["pending_approval_amount"]) == Decimal("13.000")


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_chores(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    chore_a = await _create_chore(client, headers_a, _chore_payload())

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    await _create_family(client, headers_b)

    list_b = await client.get("/family/chores", headers=headers_b)
    assert chore_a["id"] not in {c["id"] for c in list_b.json()}

    detail_b = await client.get(f"/family/chores/{chore_a['id']}", headers=headers_b)
    assert detail_b.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_approve_tenant_b_completion(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    head_a, password_a = await create_test_user(db, org_a, email=unique("head_a") + "@example.com", role="owner")
    teen_a, teen_a_password = await create_test_user(
        db, org_a, email=unique("teen_a") + "@example.com", role="viewer"
    )
    head_b, password_b = await create_test_user(db, org_b, email=unique("head_b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, head_a.email, password_a)
    await _create_family(client, headers_a)
    member_a = await _add_member(client, headers_a, teen_a, "teen")
    chore_a = await _create_chore(client, headers_a, _chore_payload(assigned_to_member_id=member_a["id"]))

    teen_a_headers = await auth_headers_for(client, teen_a.email, teen_a_password)
    completion_a = (
        await client.post(f"/family/chores/{chore_a['id']}/completions", json={}, headers=teen_a_headers)
    ).json()

    headers_b = await auth_headers_for(client, head_b.email, password_b)
    await _create_family(client, headers_b)
    response = await client.post(
        f"/family/chore-completions/{completion_a['id']}/approve", json={}, headers=headers_b
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_chore_tables(db):
    await assert_rls_enabled(db, "family_chores")
    await assert_rls_enabled(db, "family_chore_completions")


# ---------------------------------------------------------------------------
# Read-only financial safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_chore_workflow_creates_no_financial_records(client, db, auth_headers):
    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)

    await _create_family(client, auth_headers)
    chore = await _create_chore(client, auth_headers, _chore_payload(allowance_amount="15.000"))
    await client.get("/family/chores", headers=auth_headers)
    await client.get(f"/family/chores/{chore['id']}", headers=auth_headers)
    await client.get("/family/allowance-summary", headers=auth_headers)

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, Goal) == goals_before
    assert await count_rows(db, JournalEntry) == journals_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_completion_approval_creates_no_financial_records(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(db, org, email=unique("teen") + "@example.com", role="viewer")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    member = await _add_member(client, head_headers, teen, "teen")
    chore = await _create_chore(
        client, head_headers, _chore_payload(assigned_to_member_id=member["id"], allowance_amount="20.000")
    )

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    completion = (
        await client.post(f"/family/chores/{chore['id']}/completions", json={}, headers=teen_headers)
    ).json()

    accounts_before = await count_rows(db, Account)
    journals_before = await count_rows(db, JournalEntry)

    await client.post(
        f"/family/chore-completions/{completion['id']}/approve", json={}, headers=head_headers
    )

    assert await count_rows(db, Account) == accounts_before
    assert await count_rows(db, JournalEntry) == journals_before
