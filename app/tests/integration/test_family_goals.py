"""Family goals integration tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import FamilyRole, Goal, GoalContribution, GoalStatus
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
    create_test_family_member,
    create_test_organization,
    create_test_user,
)


@pytest.fixture
def goal_payload():
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


@pytest.fixture
def family_goal_payload():
    return {
        "name": "Home Renovation",
        "goal_type": "house",
        "target_amount": "5000.000",
        "target_date": (date.today() + timedelta(days=730)).isoformat(),
        "monthly_contribution": "200.000",
        "description": "Kitchen upgrade",
        "priority": 1,
        "visibility": "family",
    }


@pytest.fixture
def contribution_payload():
    return {
        "amount": "250.000",
        "date": date.today().isoformat(),
        "description": "Monthly deposit",
    }


async def _create_family(client, auth_headers, name="Test Family"):
    response = await client.post("/family", json={"name": name, "currency": "OMR"}, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _add_member(client, auth_headers, user, role: str):
    payload = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "relationship_type": "other",
        "role": role,
        "user_id": user.id,
    }
    response = await client.post("/family/members", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    member = response.json()

    # Activate the member so permission checks use the assigned role.
    patch_response = await client.patch(
        f"/family/members/{member['id']}",
        json={"is_active": True},
        headers=auth_headers,
    )
    assert patch_response.status_code == 200, patch_response.text
    return patch_response.json()


async def _create_goal(client, auth_headers, payload):
    response = await client.post("/family/goals", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_family_goal_requires_auth(client, goal_payload):
    response = await client.post("/family/goals", json=goal_payload)
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_create_family_goal(client, auth_headers, goal_payload):
    await _create_family(client, auth_headers)
    goal = await _create_goal(client, auth_headers, goal_payload)
    assert goal["name"] == goal_payload["name"]
    assert goal["visibility"] == "shared"
    assert goal["family_id"] is not None
    assert goal["owner_user_id"] is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_create_family_goal(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    response = await client.post("/family/goals", json=goal_payload, headers=parent_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["owner_user_id"] == parent.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_can_create_private_goal(client, db, unique, private_goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post("/family/goals", json=private_goal_payload, headers=adult_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["visibility"] == "private"
    assert data["owner_user_id"] == adult.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_can_see_shared_and_family_goals(
    client, db, unique, goal_payload, family_goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    shared = await _create_goal(client, head_headers, goal_payload)
    family = await _create_goal(client, head_headers, family_goal_payload)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.get("/family/goals", headers=adult_headers)
    assert response.status_code == 200, response.text
    goal_ids = {g["id"] for g in response.json()}
    assert shared["id"] in goal_ids
    assert family["id"] in goal_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_cannot_see_another_adults_private_goal(
    client, db, unique, private_goal_payload
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

    adult_a_headers = await auth_headers_for(client, adult_a.email, adult_a_password)
    private_goal = await _create_goal(client, adult_a_headers, private_goal_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    list_response = await client.get("/family/goals", headers=adult_b_headers)
    assert private_goal["id"] not in {g["id"] for g in list_response.json()}

    detail_response = await client.get(f"/family/goals/{private_goal['id']}", headers=adult_b_headers)
    assert detail_response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_can_see_shared_and_family_goals(
    client, db, unique, goal_payload, family_goal_payload, private_goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(
        db, org, email=unique("teen") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, teen, "teen")

    shared = await _create_goal(client, head_headers, goal_payload)
    family = await _create_goal(client, head_headers, family_goal_payload)
    private_goal = await _create_goal(client, head_headers, private_goal_payload)

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    response = await client.get("/family/goals", headers=teen_headers)
    assert response.status_code == 200, response.text
    goal_ids = {g["id"] for g in response.json()}
    assert shared["id"] in goal_ids
    assert family["id"] in goal_ids
    assert private_goal["id"] not in goal_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_limited_visibility(
    client, db, unique, goal_payload, family_goal_payload, private_goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(
        db, org, email=unique("child") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, child, "child")

    shared = await _create_goal(client, head_headers, goal_payload)
    family = await _create_goal(client, head_headers, family_goal_payload)

    child_headers = await auth_headers_for(client, child.email, child_password)
    response = await client.get("/family/goals", headers=child_headers)
    assert response.status_code == 200, response.text
    goal_ids = {g["id"] for g in response.json()}
    assert family["id"] in goal_ids
    assert shared["id"] not in goal_ids

    # Child can create and see their own private goal.
    private_payload = {**private_goal_payload, "name": "Child Savings"}
    create_response = await client.post("/family/goals", json=private_payload, headers=child_headers)
    assert create_response.status_code == 200, create_response.text
    private_goal = create_response.json()
    assert private_goal["owner_user_id"] == child.id

    list_response = await client.get("/family/goals", headers=child_headers)
    child_goal_ids = {g["id"] for g in list_response.json()}
    assert private_goal["id"] in child_goal_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_is_read_only(client, db, unique, goal_payload, contribution_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    shared = await _create_goal(client, head_headers, goal_payload)

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    list_response = await client.get("/family/goals", headers=viewer_headers)
    assert list_response.status_code == 200
    assert shared["id"] in {g["id"] for g in list_response.json()}

    create_response = await client.post("/family/goals", json=goal_payload, headers=viewer_headers)
    assert create_response.status_code == 400

    update_response = await client.patch(
        f"/family/goals/{shared['id']}", json={"name": "Hacked"}, headers=viewer_headers
    )
    assert update_response.status_code == 403

    cancel_response = await client.post(f"/family/goals/{shared['id']}/cancel", headers=viewer_headers)
    assert cancel_response.status_code == 403

    contribute_response = await client.post(
        f"/family/goals/{shared['id']}/contributions",
        json=contribution_payload,
        headers=viewer_headers,
    )
    assert contribute_response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_goal_requires_permission(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )
    teen, teen_password = await create_test_user(
        db, org, email=unique("teen") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")
    await _add_member(client, head_headers, teen, "teen")

    shared = await _create_goal(client, head_headers, goal_payload)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    update_response = await client.patch(
        f"/family/goals/{shared['id']}", json={"name": "Updated"}, headers=adult_headers
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated"

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    teen_update = await client.patch(
        f"/family/goals/{shared['id']}", json={"name": "Hacked"}, headers=teen_headers
    )
    assert teen_update.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_and_complete_goal_permissions(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    shared = await _create_goal(client, head_headers, goal_payload)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    complete_response = await client.post(f"/family/goals/{shared['id']}/complete", headers=adult_headers)
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"

    cancel_response = await client.post(f"/family/goals/{shared['id']}/cancel", headers=adult_headers)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


@pytest.mark.integration
@pytest.mark.anyio
async def test_contribution_updates_progress(
    client, db, unique, goal_payload, contribution_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    shared = await _create_goal(client, head_headers, goal_payload)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post(
        f"/family/goals/{shared['id']}/contributions",
        json=contribution_payload,
        headers=adult_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["amount"] == contribution_payload["amount"]

    progress_response = await client.get(f"/family/goals/{shared['id']}/progress", headers=adult_headers)
    assert progress_response.status_code == 200, progress_response.text
    progress = progress_response.json()
    assert progress["current"] == 250.0
    assert progress["progress_percentage"] == 25.0

    # Second contribution completes the goal.
    await client.post(
        f"/family/goals/{shared['id']}/contributions",
        json={"amount": "750.000", "date": date.today().isoformat()},
        headers=adult_headers,
    )
    goal_response = await client.get(f"/family/goals/{shared['id']}", headers=adult_headers)
    assert goal_response.json()["status"] == "completed"


@pytest.mark.integration
@pytest.mark.anyio
async def test_contribution_with_inaccessible_account_rejected(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    # Create a private account owned by head under the correct tenant context.
    await set_tenant_context_async(db, org.id)
    private_account = await create_test_account(
        db, tenant_id=org.id, visibility="private", owner_user_id=head.id
    )
    await db.commit()

    shared = await _create_goal(client, head_headers, goal_payload)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post(
        f"/family/goals/{shared['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "account_id": private_account.id,
        },
        headers=adult_headers,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_goals(
    client, db, unique, goal_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    goal_a = await _create_goal(client, headers_a, goal_payload)

    await _create_family(client, headers_b, name="Family B")

    list_b = await client.get("/family/goals", headers=headers_b)
    assert list_b.status_code == 200
    assert goal_a["id"] not in {g["id"] for g in list_b.json()}

    detail_b = await client.get(f"/family/goals/{goal_a['id']}", headers=headers_b)
    assert detail_b.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_contribute_to_tenant_b_goal(
    client, db, unique, goal_payload, contribution_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    goal_a = await _create_goal(client, headers_a, goal_payload)

    await _create_family(client, headers_b, name="Family B")

    response = await client.post(
        f"/family/goals/{goal_a['id']}/contributions",
        json=contribution_payload,
        headers=headers_b,
    )
    assert response.status_code in (403, 404)


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_goal_contributions(client, db, unique, goal_payload, contribution_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    shared = await _create_goal(client, head_headers, goal_payload)

    await client.post(
        f"/family/goals/{shared['id']}/contributions",
        json=contribution_payload,
        headers=head_headers,
    )

    response = await client.get(f"/family/goals/{shared['id']}/contributions", headers=head_headers)
    assert response.status_code == 200, response.text
    contributions = response.json()
    assert len(contributions) == 1
    assert contributions[0]["contributed_by_user_id"] == head.id
