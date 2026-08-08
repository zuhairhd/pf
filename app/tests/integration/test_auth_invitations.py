"""Tenant/family member invitation flow tests (AUTH-305).

Covers invitation create/list/cancel (authenticated, tenant-scoped) and
acceptance (unauthenticated, token-driven), idempotency, permissions,
tenant isolation, RLS, and read-only safety of every action except the
final accept step (which creates a User + FamilyMember row only -- never
a journal entry, account, budget, bill, or goal record).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.rls import set_tenant_context_async
from app.models import (
    Account,
    Bill,
    Budget,
    Family,
    FamilyInvitation,
    FamilyMember,
    Goal,
    GoalContribution,
    JournalEntry,
    User,
)
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
    rls_status,
)


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


def _invite_payload(email: str, role: str = "adult") -> dict:
    return {
        "email": email,
        "first_name": "Invitee",
        "last_name": "Person",
        "relationship_type": "spouse",
        "role": role,
    }


async def _get_invitation_token(db, invitation_id: int) -> str:
    """Fetch the raw invitation token directly from the DB, matching the
    existing PasswordReset-token test pattern (never exposed via the API)."""
    result = await db.execute(select(FamilyInvitation).where(FamilyInvitation.id == invitation_id))
    return result.scalar_one().token


# ---------------------------------------------------------------------------
# Create / permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_invitation_requires_auth(client):
    response = await client.post("/family/members/invitations", json=_invite_payload("nobody@example.com"))
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_create_invitation(client, auth_headers, unique):
    await _create_family(client, auth_headers)
    response = await client.post(
        "/family/members/invitations",
        json=_invite_payload(unique("invitee") + "@example.com"),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "pending"
    assert data["expires_at"] is not None
    assert "token" not in data


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_create_invitation(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post(
        "/family/members/invitations",
        json=_invite_payload(unique("someone") + "@example.com"),
        headers=viewer_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_duplicate_pending_invitation_is_idempotent(client, auth_headers, unique):
    await _create_family(client, auth_headers)
    email = unique("dup") + "@example.com"

    first = await client.post("/family/members/invitations", json=_invite_payload(email), headers=auth_headers)
    assert first.status_code == 200, first.text

    second = await client.post("/family/members/invitations", json=_invite_payload(email), headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_invitation_rejects_existing_account_email(client, auth_headers, test_user, unique):
    await _create_family(client, auth_headers)
    response = await client.post(
        "/family/members/invitations",
        json=_invite_payload(test_user.email),
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text
    assert "already registered" in response.json()["message"].lower()


# ---------------------------------------------------------------------------
# List / cancel / tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_listing_does_not_leak_invitations(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    await _create_family(client, headers_b, name="Family B")

    invite_email = unique("secret") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(invite_email), headers=headers_a
    )
    assert created.status_code == 200, created.text

    list_b = await client.get("/family/members/invitations", headers=headers_b)
    assert list_b.status_code == 200, list_b.text
    assert invite_email not in [i["email"] for i in list_b.json()]

    list_a = await client.get("/family/members/invitations", headers=headers_a)
    assert invite_email in [i["email"] for i in list_a.json()]


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_cancel_rejected(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    await _create_family(client, headers_b, name="Family B")

    created = await client.post(
        "/family/members/invitations",
        json=_invite_payload(unique("target") + "@example.com"),
        headers=headers_a,
    )
    invitation_id = created.json()["id"]

    response = await client.post(
        f"/family/members/invitations/{invitation_id}/cancel", headers=headers_b
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_pending_invitation(client, auth_headers, unique):
    await _create_family(client, auth_headers)
    created = await client.post(
        "/family/members/invitations",
        json=_invite_payload(unique("cancelme") + "@example.com"),
        headers=auth_headers,
    )
    invitation_id = created.json()["id"]

    response = await client.post(f"/family/members/invitations/{invitation_id}/cancel", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Acceptance
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_acceptance_creates_and_activates_member(client, db, auth_headers, test_user, unique):
    await _create_family(client, auth_headers)
    email = unique("newmember") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email, role="adult"), headers=auth_headers
    )
    assert created.status_code == 200, created.text
    invitation_id = created.json()["id"]
    token = await _get_invitation_token(db, invitation_id)

    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert "access_token" in tokens

    await set_tenant_context_async(db, test_user.organization_id)
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.tenant_id == test_user.organization_id,
            FamilyMember.email == email,
        )
    )
    member = result.scalar_one()
    assert member.is_active is True
    assert member.role == "adult"
    assert member.user_id is not None

    result = await db.execute(select(FamilyInvitation).where(FamilyInvitation.id == invitation_id))
    invitation = result.scalar_one()
    assert invitation.status == "accepted"
    assert invitation.member_id == member.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_accepted_invitation_cannot_be_accepted_twice(client, db, auth_headers, unique):
    await _create_family(client, auth_headers)
    email = unique("oncer") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email), headers=auth_headers
    )
    invitation_id = created.json()["id"]
    token = await _get_invitation_token(db, invitation_id)

    first = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "AnotherPass123!"},
    )
    assert second.status_code == 400, second.text
    assert "accepted" in second.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancelled_invitation_cannot_be_accepted(client, db, auth_headers, unique):
    await _create_family(client, auth_headers)
    email = unique("cancelled") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email), headers=auth_headers
    )
    invitation_id = created.json()["id"]
    token = await _get_invitation_token(db, invitation_id)

    cancel_response = await client.post(
        f"/family/members/invitations/{invitation_id}/cancel", headers=auth_headers
    )
    assert cancel_response.status_code == 200

    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert response.status_code == 400, response.text
    assert "cancelled" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_expired_invitation_cannot_be_accepted(client, db, auth_headers, unique):
    await _create_family(client, auth_headers)
    email = unique("expired") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email), headers=auth_headers
    )
    invitation_id = created.json()["id"]

    result = await db.execute(select(FamilyInvitation).where(FamilyInvitation.id == invitation_id))
    invitation = result.scalar_one()
    invitation.expires_at = datetime.utcnow() - timedelta(days=1)
    await db.commit()

    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": invitation.token, "password": "InviteePass123!"},
    )
    assert response.status_code == 400, response.text
    assert "expired" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_invalid_token_rejected(client):
    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": "not-a-real-token", "password": "InviteePass123!"},
    )
    assert response.status_code == 400
    assert "invalid" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_accept_rejects_email_with_existing_account_in_another_tenant(
    client, db, auth_headers, unique
):
    """An email that gains an account elsewhere after being invited cannot
    accept into a different tenant -- the closest equivalent to
    'cross-tenant acceptance' in this single-tenant-per-user architecture.

    (Most real-world cases are already caught earlier, at invitation-create
    time -- see test_create_invitation_rejects_existing_account_email. This
    test exercises the accept-time defense-in-depth check for the race
    where the account appears only after the invitation was created.)"""
    shared_email = unique("shared") + "@example.com"

    await _create_family(client, auth_headers)
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(shared_email), headers=auth_headers
    )
    assert created.status_code == 200, created.text
    invitation_id = created.json()["id"]
    token = await _get_invitation_token(db, invitation_id)

    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    await create_test_user(db, org_b, email=shared_email, role="owner")

    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert response.status_code == 400, response.text
    assert "already exists" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_acceptance_always_uses_invitation_tenant(client, db, auth_headers, test_user, unique):
    """The resulting account always joins the inviting tenant -- there is no
    parameter in the accept request that could redirect it elsewhere."""
    await _create_family(client, auth_headers)
    email = unique("boundtenant") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email), headers=auth_headers
    )
    invitation_id = created.json()["id"]
    token = await _get_invitation_token(db, invitation_id)

    response = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert response.status_code == 200, response.text

    access_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me_response = await client.get("/family/permissions", headers=access_headers)
    assert me_response.status_code == 200

    result = await db.execute(select(User).where(User.email == email))
    new_user = result.scalar_one()
    assert new_user.organization_id == test_user.organization_id


# ---------------------------------------------------------------------------
# RLS
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_member_and_related_tables(db):
    await assert_rls_enabled(db, "family_members")
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")


@pytest.mark.integration
@pytest.mark.anyio
async def test_family_invitations_table_intentionally_has_no_rls(db):
    """family_invitations is deliberately RLS-exempt, matching
    email_verifications/password_resets -- see app/core/rls.py GLOBAL_TABLES
    and app/models/family.py's FamilyInvitation docstring. Tenant isolation
    for authenticated operations is enforced at the service layer instead
    (see the cross-tenant listing/cancel tests above)."""
    status = await rls_status(db, "family_invitations")
    assert status["rls_enabled"] is False


# ---------------------------------------------------------------------------
# Read-only safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_invitation_actions_create_no_financial_records(
    client, db, auth_headers, test_user, tenant_context, unique
):
    await _create_family(client, auth_headers)

    await tenant_context(test_user.organization_id)
    before = {
        "journal_entries": await count_rows(
            db, JournalEntry, JournalEntry.tenant_id == test_user.organization_id
        ),
        "accounts": await count_rows(db, Account, Account.tenant_id == test_user.organization_id),
        "budgets": await count_rows(db, Budget, Budget.tenant_id == test_user.organization_id),
        "bills": await count_rows(db, Bill, Bill.tenant_id == test_user.organization_id),
        "goals": await count_rows(db, Goal, Goal.tenant_id == test_user.organization_id),
        "goal_contributions": await count_rows(
            db, GoalContribution, GoalContribution.tenant_id == test_user.organization_id
        ),
    }

    email = unique("readonly") + "@example.com"
    created = await client.post(
        "/family/members/invitations", json=_invite_payload(email), headers=auth_headers
    )
    invitation_id = created.json()["id"]

    await client.get("/family/members/invitations", headers=auth_headers)

    token = await _get_invitation_token(db, invitation_id)
    accept_response = await client.post(
        "/family/members/invitations/accept",
        json={"token": token, "password": "InviteePass123!"},
    )
    assert accept_response.status_code == 200, accept_response.text

    await tenant_context(test_user.organization_id)
    after = {
        "journal_entries": await count_rows(
            db, JournalEntry, JournalEntry.tenant_id == test_user.organization_id
        ),
        "accounts": await count_rows(db, Account, Account.tenant_id == test_user.organization_id),
        "budgets": await count_rows(db, Budget, Budget.tenant_id == test_user.organization_id),
        "bills": await count_rows(db, Bill, Bill.tenant_id == test_user.organization_id),
        "goals": await count_rows(db, Goal, Goal.tenant_id == test_user.organization_id),
        "goal_contributions": await count_rows(
            db, GoalContribution, GoalContribution.tenant_id == test_user.organization_id
        ),
    }
    assert before == after
