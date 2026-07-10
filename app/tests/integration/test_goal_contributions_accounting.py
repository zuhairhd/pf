"""Goal contribution accounting integration tests.

Covers posting family goal contributions through the double-entry accounting
engine, account validation, idempotency, tenant isolation, and RLS.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.rls import set_tenant_context_async
from app.models import GoalContribution, JournalEntry, JournalLine
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
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
        "description": "Save for vacation",
        "priority": 1,
        "visibility": "shared",
    }


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


async def _create_goal(client, headers, payload):
    response = await client.post("/family/goals", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _create_shared_asset_account(db, tenant_id, name, owner_user_id=None):
    await set_tenant_context_async(db, tenant_id)
    return await create_test_account(
        db,
        tenant_id=tenant_id,
        name=name,
        account_type="Asset",
        visibility="shared",
        owner_user_id=owner_user_id,
    )


async def _create_private_asset_account(db, tenant_id, name, owner_user_id):
    await set_tenant_context_async(db, tenant_id)
    return await create_test_account(
        db,
        tenant_id=tenant_id,
        name=name,
        account_type="Asset",
        visibility="private",
        owner_user_id=owner_user_id,
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_progress_only_contribution_creates_no_journal_entry(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "100.000", "date": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["posting_status"] == "progress_only"
    assert data["journal_entry_id"] is None
    assert data["source_account_id"] is None
    assert data["destination_account_id"] is None

    # No journal entry should have been created.
    journal_count = await db.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(
            __import__("sqlalchemy", fromlist=["func"]).func.count(JournalEntry.id)
        ).where(JournalEntry.reference.like(f"GOAL-{org.id}-{goal['id']}-%"))
    )
    assert journal_count == 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_progress_only_contribution_updates_progress(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "250.000", "date": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    progress_response = await client.get(f"/family/goals/{goal['id']}/progress", headers=headers)
    assert progress_response.status_code == 200, progress_response.text
    progress = progress_response.json()
    assert progress["current"] == 250.0
    assert progress["progress_percentage"] == 25.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_posted_contribution_creates_balanced_journal_entry(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "200.000",
            "date": date.today().isoformat(),
            "source_account_id": source.id,
            "destination_account_id": destination.id,
            "post_to_accounting": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["posting_status"] == "posted"
    assert data["journal_entry_id"] is not None

    # Verify the journal entry is balanced and has the right reference.
    await set_tenant_context_async(db, org.id)
    entry = await db.get(JournalEntry, data["journal_entry_id"])
    assert entry is not None
    assert entry.reference == f"GOAL-{org.id}-{goal['id']}-{data['id']}"
    assert entry.narration == f"Goal contribution: {goal_payload['name']}"

    lines = await db.scalars(
        __import__("sqlalchemy", fromlist=["select"]).select(JournalLine).where(
            JournalLine.journal_entry_id == entry.id
        )
    )
    lines = list(lines.all())
    assert len(lines) == 2
    debits = sum(float(line.debit) for line in lines)
    credits = sum(float(line.credit) for line in lines)
    assert debits == credits
    assert debits == 200.0

    # Destination is debited, source is credited.
    destination_line = next(line for line in lines if line.account_id == destination.id)
    source_line = next(line for line in lines if line.account_id == source.id)
    assert float(destination_line.debit) == 200.0
    assert float(destination_line.credit) == 0.0
    assert float(source_line.credit) == 200.0
    assert float(source_line.debit) == 0.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_posting_does_not_duplicate_journal_entry(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "150.000",
            "date": date.today().isoformat(),
            "source_account_id": source.id,
            "destination_account_id": destination.id,
            "post_to_accounting": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    contribution_id = response.json()["id"]
    first_journal_entry_id = response.json()["journal_entry_id"]

    # Post the same contribution again.
    repeat_response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution_id}/post",
        headers=headers,
    )
    assert repeat_response.status_code == 200, repeat_response.text
    assert repeat_response.json()["journal_entry_id"] == first_journal_entry_id

    # Only one journal entry for this contribution reference.
    await set_tenant_context_async(db, org.id)
    journal_count = await db.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(
            __import__("sqlalchemy", fromlist=["func"]).func.count(JournalEntry.id)
        ).where(JournalEntry.reference == f"GOAL-{org.id}-{goal['id']}-{contribution_id}")
    )
    assert journal_count == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_requires_both_accounts(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": source.id,
            "post_to_accounting": True,
        },
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert "destination_account_id" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_rejects_source_account_from_other_tenant(
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
    destination_b = await _create_shared_asset_account(db, org_b.id, unique("Dest B"))
    await db.commit()

    # Source account from tenant A used in tenant B should not be found.
    source_a = await _create_shared_asset_account(db, org_a.id, unique("Source A"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal_a['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": source_a.id,
            "destination_account_id": destination_b.id,
            "post_to_accounting": True,
        },
        headers=headers_b,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_rejects_destination_account_from_other_tenant(
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

    source_a = await _create_shared_asset_account(db, org_a.id, unique("Source A"))
    destination_b = await _create_shared_asset_account(db, org_b.id, unique("Dest B"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal_a['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": source_a.id,
            "destination_account_id": destination_b.id,
            "post_to_accounting": True,
        },
        headers=headers_a,
    )
    assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_rejects_inaccessible_private_source_account(
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
    goal = await _create_goal(client, head_headers, goal_payload)

    # Private source account owned by head.
    private_source = await _create_private_asset_account(db, org.id, unique("PrivateSource"), head.id)
    shared_destination = await _create_shared_asset_account(db, org.id, unique("Dest"))
    await db.commit()

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": private_source.id,
            "destination_account_id": shared_destination.id,
            "post_to_accounting": True,
        },
        headers=adult_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_rejects_inaccessible_private_destination_account(
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
    goal = await _create_goal(client, head_headers, goal_payload)

    shared_source = await _create_shared_asset_account(db, org.id, unique("Source"))
    private_destination = await _create_private_asset_account(db, org.id, unique("PrivateDest"), head.id)
    await db.commit()

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": shared_source.id,
            "destination_account_id": private_destination.id,
            "post_to_accounting": True,
        },
        headers=adult_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_posting_rejects_non_asset_accounts(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    expense_source = await create_test_account(
        db,
        tenant_id=org.id,
        name=unique("ExpenseSource"),
        account_type="Expense",
        visibility="shared",
    )
    shared_destination = await _create_shared_asset_account(db, org.id, unique("Dest"))
    await db.commit()

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": expense_source.id,
            "destination_account_id": shared_destination.id,
            "post_to_accounting": True,
        },
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert "asset" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_post_contribution(
    client, db, unique, goal_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")
    goal = await _create_goal(client, head_headers, goal_payload)

    shared_source = await _create_shared_asset_account(db, org.id, unique("Source"))
    shared_destination = await _create_shared_asset_account(db, org.id, unique("Dest"))
    await db.commit()

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": shared_source.id,
            "destination_account_id": shared_destination.id,
            "post_to_accounting": True,
        },
        headers=viewer_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_b_cannot_use_tenant_a_account_for_posting(
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

    source_b = await _create_shared_asset_account(db, org_b.id, unique("Source B"))
    destination_a = await _create_shared_asset_account(db, org_a.id, unique("Dest A"))
    await db.commit()

    # User B tries to contribute to goal A using an account from tenant B.
    response = await client.post(
        f"/family/goals/{goal_a['id']}/contributions",
        json={
            "amount": "100.000",
            "date": date.today().isoformat(),
            "source_account_id": source_b.id,
            "destination_account_id": destination_a.id,
            "post_to_accounting": True,
        },
        headers=headers_b,
    )
    assert response.status_code in (403, 404), response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")
