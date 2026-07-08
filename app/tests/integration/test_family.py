"""Family finance module integration tests."""

from __future__ import annotations

import pytest

from app.models import Family, FamilyMember, FamilyRole
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


@pytest.fixture
def family_payload():
    return {"name": "The Smith Family", "currency": "OMR"}


@pytest.fixture
def member_payload():
    return {
        "email": "spouse@example.com",
        "first_name": "Jane",
        "last_name": "Smith",
        "relationship_type": "spouse",
        "role": "adult",
    }


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_family_requires_auth(client, family_payload):
    response = await client.post("/family", json=family_payload)
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_family(client, auth_headers, family_payload):
    response = await client.post("/family", json=family_payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == family_payload["name"]
    assert data["currency"] == family_payload["currency"]
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "head"


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_family_already_exists(client, auth_headers, family_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    response = await client.post("/family", json={"name": "Other"}, headers=auth_headers)
    assert response.status_code == 400
    assert "already exists" in response.text.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_family(client, auth_headers, family_payload):
    create_response = await client.post("/family", json=family_payload, headers=auth_headers)
    family_id = create_response.json()["id"]

    response = await client.get("/family", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == family_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_family(client, auth_headers, family_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    response = await client.patch(
        "/family",
        json={"name": "Updated Family"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Updated Family"


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_update_family(client, db, unique, family_payload):
    """A non-head family member cannot update the family profile."""
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, _ = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    headers_head = await auth_headers_for(client, head.email, "SecurePass123!")
    await client.post("/family", json=family_payload, headers=headers_head)

    # Add viewer as a family member with viewer role.
    await client.post(
        "/family/members",
        json={
            "email": viewer.email,
            "first_name": viewer.first_name,
            "last_name": viewer.last_name,
            "relationship_type": "child",
            "role": "viewer",
            "user_id": viewer.id,
        },
        headers=headers_head,
    )

    headers_viewer = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.patch(
        "/family",
        json={"name": "Hacked"},
        headers=headers_viewer,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_add_family_member(client, auth_headers, family_payload, member_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    response = await client.post("/family/members", json=member_payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == member_payload["email"]
    assert data["role"] == member_payload["role"]
    assert data["relationship_type"] == member_payload["relationship_type"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_family_members(client, auth_headers, family_payload, member_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    await client.post("/family/members", json=member_payload, headers=auth_headers)

    response = await client.get("/family/members", headers=auth_headers)
    assert response.status_code == 200, response.text
    members = response.json()
    assert len(members) == 2
    assert any(m["role"] == "head" for m in members)
    assert any(m["email"] == member_payload["email"] for m in members)


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_family_member(client, auth_headers, family_payload, member_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    create_response = await client.post("/family/members", json=member_payload, headers=auth_headers)
    member_id = create_response.json()["id"]

    response = await client.patch(
        f"/family/members/{member_id}",
        json={"role": "parent"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "parent"


@pytest.mark.integration
@pytest.mark.anyio
async def test_delete_family_member(client, auth_headers, family_payload, member_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    create_response = await client.post("/family/members", json=member_payload, headers=auth_headers)
    member_id = create_response.json()["id"]

    response = await client.delete(f"/family/members/{member_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True

    get_response = await client.get("/family/members", headers=auth_headers)
    assert not any(m["id"] == member_id for m in get_response.json())


@pytest.mark.integration
@pytest.mark.anyio
async def test_family_permissions_head(client, auth_headers, family_payload):
    await client.post("/family", json=family_payload, headers=auth_headers)
    response = await client.get("/family/permissions", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["role"] == "head"
    assert data["can_manage_members"] is True
    assert data["can_edit_family"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_family_permissions_viewer(client, db, unique, family_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, _ = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    headers_head = await auth_headers_for(client, head.email, "SecurePass123!")
    await client.post("/family", json=family_payload, headers=headers_head)
    await client.post(
        "/family/members",
        json={
            "email": viewer.email,
            "first_name": viewer.first_name,
            "last_name": viewer.last_name,
            "relationship_type": "child",
            "role": "viewer",
            "user_id": viewer.id,
        },
        headers=headers_head,
    )

    headers_viewer = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.get("/family/permissions", headers=headers_viewer)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["role"] == "viewer"
    assert data["can_view_family"] is True
    assert data["can_manage_members"] is False


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_family(
    client, db, unique, family_payload, member_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    create_response = await client.post("/family", json=family_payload, headers=headers_a)
    family_id = create_response.json()["id"]
    member_response = await client.post("/family/members", json=member_payload, headers=headers_a)
    member_id = member_response.json()["id"]

    # Tenant B cannot read the family.
    response = await client.get("/family", headers=headers_b)
    assert response.status_code == 200
    assert response.json() is None

    # Tenant B cannot read members.
    response = await client.get("/family/members", headers=headers_b)
    assert response.status_code == 200
    assert response.json() == []

    # Confirm Tenant A still sees its own member.
    list_a = await client.get("/family/members", headers=headers_a)
    assert any(m["id"] == member_id for m in list_a.json())


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_family_tables(db):
    await assert_rls_enabled(db, "families")
    await assert_rls_enabled(db, "family_members")
