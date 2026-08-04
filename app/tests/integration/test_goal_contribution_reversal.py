"""Goal contribution reversal integration tests (GOAL-1401B).

Covers reversing posted family goal contributions through the existing
AccountingService.reverse_journal_entry() engine, progress-total handling,
idempotency, permissions, tenant isolation, and RLS.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

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


async def _post_contribution(client, headers, goal_id, source, destination, amount="200.000"):
    response = await client.post(
        f"/family/goals/{goal_id}/contributions",
        json={
            "amount": amount,
            "date": date.today().isoformat(),
            "source_account_id": source.id,
            "destination_account_id": destination.id,
            "post_to_accounting": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Reversal behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_posted_contribution_can_be_reversed(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={"reason": "Duplicate entry"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["posting_status"] == "reversed"
    assert data["reversal_journal_entry_id"] is not None
    assert data["reversed_at"] is not None
    assert data["reversal_reason"] == "Duplicate entry"


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversal_creates_balanced_reversing_journal_entry(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination, amount="200.000")

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    reversal_id = response.json()["reversal_journal_entry_id"]

    await set_tenant_context_async(db, org.id)
    result = await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == reversal_id))
    lines = list(result.scalars().all())
    assert len(lines) == 2
    debits = sum(float(line.debit) for line in lines)
    credits = sum(float(line.credit) for line in lines)
    assert debits == credits == 200.0

    # Debit/credit sides are swapped relative to the original posting:
    # original debited destination and credited source.
    destination_line = next(line for line in lines if line.account_id == destination.id)
    source_line = next(line for line in lines if line.account_id == source.id)
    assert float(destination_line.credit) == 200.0
    assert float(destination_line.debit) == 0.0
    assert float(source_line.debit) == 200.0
    assert float(source_line.credit) == 0.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_original_journal_entry_unchanged_after_reversal(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)
    original_journal_entry_id = contribution["journal_entry_id"]

    await set_tenant_context_async(db, org.id)
    original_lines_before = list(
        (
            await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == original_journal_entry_id))
        ).scalars().all()
    )
    before_snapshot = sorted(
        (line.account_id, str(line.debit), str(line.credit)) for line in original_lines_before
    )

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    await set_tenant_context_async(db, org.id)
    original_entry = await db.get(JournalEntry, original_journal_entry_id)
    assert original_entry is not None
    original_lines_after = list(
        (
            await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == original_journal_entry_id))
        ).scalars().all()
    )
    after_snapshot = sorted(
        (line.account_id, str(line.debit), str(line.credit)) for line in original_lines_after
    )
    assert before_snapshot == after_snapshot


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_reversal_does_not_duplicate_journal_entries(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)

    first = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_reversal_id = first.json()["reversal_journal_entry_id"]

    second = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["reversal_journal_entry_id"] == first_reversal_id

    await set_tenant_context_async(db, org.id)
    count = await db.scalar(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.reversed_entry_id == contribution["journal_entry_id"]
        )
    )
    assert count == 1


# ---------------------------------------------------------------------------
# Progress calculation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversed_contribution_no_longer_counts_toward_progress(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination, amount="300.000")

    progress_before = await client.get(f"/family/goals/{goal['id']}/progress", headers=headers)
    assert progress_before.json()["current"] == 300.0

    reverse_response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert reverse_response.status_code == 200, reverse_response.text

    progress_after = await client.get(f"/family/goals/{goal['id']}/progress", headers=headers)
    assert progress_after.json()["current"] == 0.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_progress_only_contribution_still_counts_if_not_reversed(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "150.000", "date": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    progress = await client.get(f"/family/goals/{goal['id']}/progress", headers=headers)
    assert progress.json()["current"] == 150.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_cannot_reverse_progress_only_contribution(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "150.000", "date": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    contribution_id = response.json()["id"]

    reverse_response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution_id}/reverse",
        json={},
        headers=headers,
    )
    assert reverse_response.status_code == 400
    assert "never posted" in reverse_response.json()["message"].lower()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_reverse_contribution(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")
    goal = await _create_goal(client, head_headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, head_headers, goal["id"], source, destination)

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=parent_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["posting_status"] == "reversed"


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_reverse_contribution(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")
    goal = await _create_goal(client, head_headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, head_headers, goal["id"], source, destination)

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=viewer_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_cannot_reverse_others_private_goal_contribution(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    private_payload = dict(goal_payload)
    private_payload["visibility"] = "private"
    goal = await _create_goal(client, head_headers, private_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, head_headers, goal["id"], source, destination)

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=adult_headers,
    )
    assert response.status_code == 403, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_reverse_tenant_b_contribution(client, db, unique, goal_payload):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    await _create_family(client, headers_a, name="Family A")
    goal_a = await _create_goal(client, headers_a, goal_payload)

    source_a = await _create_shared_asset_account(db, org_a.id, unique("Source A"))
    destination_a = await _create_shared_asset_account(db, org_a.id, unique("Dest A"))
    await db.commit()

    contribution = await _post_contribution(client, headers_a, goal_a["id"], source_a, destination_a)

    await _create_family(client, headers_b, name="Family B")

    response = await client.post(
        f"/family/goals/{goal_a['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers_b,
    )
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# API-level safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reverse_route_requires_auth(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/999999/reverse",
        json={},
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_invalid_contribution_id_returns_safe_404(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions/999999/reverse",
        json={},
        headers=headers,
    )
    assert response.status_code == 404
    assert "Traceback" not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_contribution_from_different_goal_rejected(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal_one = await _create_goal(client, headers, goal_payload)
    other_payload = dict(goal_payload)
    other_payload["name"] = "Other Goal"
    goal_two = await _create_goal(client, headers, other_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal_one["id"], source, destination)

    response = await client.post(
        f"/family/goals/{goal_two['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_already_reversed_contribution_returns_existing_state(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)

    first = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={"reason": "First reason"},
        headers=headers,
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={"reason": "Second reason"},
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["posting_status"] == "reversed"
    assert second.json()["reversal_journal_entry_id"] == first.json()["reversal_journal_entry_id"]


# ---------------------------------------------------------------------------
# RLS
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_and_journal_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
