"""Family Goals dashboard contribution-history and reversal tests (DB-1105B).

Covers the dashboard's per-goal contribution history, the eligibility rules
for showing a "Reverse" action, the HTMX reversal route, idempotency,
read-only safety, and tenant/RLS isolation. The reversal route is a thin
wrapper around the already-tested FamilyGoalService.reverse_contribution()
(GOAL-1401B) -- these tests exercise the dashboard layer, not the reversal
engine itself.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core.rls import set_tenant_context_async
from app.models import (
    Account,
    Bill,
    Budget,
    JournalEntry,
    JournalLine,
)
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
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


async def _create_shared_asset_account(db, tenant_id, name):
    await set_tenant_context_async(db, tenant_id)
    return await create_test_account(
        db, tenant_id=tenant_id, name=name, account_type="Asset", visibility="shared"
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


def _reverse_url(goal_id: int, contribution_id: int) -> str:
    return f"/dashboard/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse"


# ---------------------------------------------------------------------------
# Dashboard rendering / eligibility
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_shows_recent_posted_contribution(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    source = await _create_shared_asset_account(db, org.id, unique("Source"))
    destination = await _create_shared_asset_account(db, org.id, unique("Destination"))
    await db.commit()

    await _post_contribution(client, headers, goal["id"], source, destination, amount="150.000")

    response = await client.get("/dashboard/partials/family-goals", headers=headers)
    assert response.status_code == 200, response.text
    assert "150.000" in response.text
    assert "Posted" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_progress_only_contribution_shows_no_reverse_button(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(
        f"/family/goals/{goal['id']}/contributions",
        json={"amount": "75.000", "date": date.today().isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    contribution_id = response.json()["id"]

    dashboard_response = await client.get("/dashboard/partials/family-goals", headers=headers)
    assert dashboard_response.status_code == 200, dashboard_response.text
    assert "Progress Only" in dashboard_response.text
    assert f'contributions/{contribution_id}/reverse' not in dashboard_response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_reversed_contribution_shows_reversed_badge_and_no_button(
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

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)

    await client.post(
        f"/family/goals/{goal['id']}/contributions/{contribution['id']}/reverse",
        json={},
        headers=headers,
    )

    response = await client.get("/dashboard/partials/family-goals", headers=headers)
    assert response.status_code == 200, response.text
    assert "Reversed" in response.text
    assert f'contributions/{contribution["id"]}/reverse' not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_eligible_posted_contribution_shows_reverse_button_for_head(
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

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)

    response = await client.get("/dashboard/partials/family-goals", headers=headers)
    assert response.status_code == 200, response.text
    assert f'contributions/{contribution["id"]}/reverse' in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_does_not_see_reverse_button(client, db, unique, goal_payload):
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
    response = await client.get("/dashboard/partials/family-goals", headers=viewer_headers)
    assert response.status_code == 200, response.text
    assert f'contributions/{contribution["id"]}/reverse' not in response.text


# ---------------------------------------------------------------------------
# Route / auth
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_reverse_dashboard_route_requires_auth(client, db, unique, goal_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, headers)
    goal = await _create_goal(client, headers, goal_payload)

    response = await client.post(_reverse_url(goal["id"], 999999))
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_authorized_user_can_reverse_posted_contribution(client, db, unique, goal_payload):
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

    response = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert response.status_code == 200, response.text
    assert "Reversed" in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_viewer_cannot_reverse(client, db, unique, goal_payload):
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
    response = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=viewer_headers)
    assert response.status_code == 400, response.text

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.reversed_entry_id == contribution["journal_entry_id"]
        )
    )
    assert result.scalar() == 0


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_dashboard_reverse_rejected(client, db, unique, goal_payload):
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

    response = await client.post(_reverse_url(goal_a["id"], contribution["id"]), headers=headers_b)
    assert response.status_code == 400, response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_contribution_from_another_goal_rejected(client, db, unique, goal_payload):
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

    response = await client.post(_reverse_url(goal_two["id"], contribution["id"]), headers=headers)
    assert response.status_code == 400, response.text


# ---------------------------------------------------------------------------
# Reversal behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_reverse_creates_balanced_reversal_journal_entry(
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

    contribution = await _post_contribution(client, headers, goal["id"], source, destination, amount="200.000")

    response = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert response.status_code == 200, response.text

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.reversed_entry_id == contribution["journal_entry_id"])
    )
    reversal_entry = result.scalar_one()

    lines_result = await db.execute(
        select(JournalLine).where(JournalLine.journal_entry_id == reversal_entry.id)
    )
    lines = list(lines_result.scalars().all())
    assert len(lines) == 2
    debits = sum(float(line.debit) for line in lines)
    credits = sum(float(line.credit) for line in lines)
    assert debits == credits == 200.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_original_contribution_and_journal_entry_remain_after_dashboard_reverse(
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

    contribution = await _post_contribution(client, headers, goal["id"], source, destination)
    original_journal_entry_id = contribution["journal_entry_id"]

    await set_tenant_context_async(db, org.id)
    original_lines_before = list(
        (await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == original_journal_entry_id)))
        .scalars()
        .all()
    )
    before_snapshot = sorted((l.account_id, str(l.debit), str(l.credit)) for l in original_lines_before)

    response = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert response.status_code == 200, response.text

    await set_tenant_context_async(db, org.id)
    from app.models import GoalContribution

    stored_contribution = await db.get(GoalContribution, contribution["id"])
    assert stored_contribution is not None
    assert stored_contribution.posting_status == "reversed"
    assert stored_contribution.reversal_journal_entry_id is not None

    original_entry = await db.get(JournalEntry, original_journal_entry_id)
    assert original_entry is not None
    original_lines_after = list(
        (await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == original_journal_entry_id)))
        .scalars()
        .all()
    )
    after_snapshot = sorted((l.account_id, str(l.debit), str(l.credit)) for l in original_lines_after)
    assert before_snapshot == after_snapshot


@pytest.mark.integration
@pytest.mark.anyio
async def test_goal_progress_reduced_after_dashboard_reverse(client, db, unique, goal_payload):
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

    response = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert response.status_code == 200, response.text

    progress_after = await client.get(f"/family/goals/{goal['id']}/progress", headers=headers)
    assert progress_after.json()["current"] == 0.0


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_dashboard_reverse_is_idempotent(client, db, unique, goal_payload):
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

    first = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert first.status_code == 200, first.text

    second = await client.post(_reverse_url(goal["id"], contribution["id"]), headers=headers)
    assert second.status_code == 200, second.text

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(func.count(JournalEntry.id)).where(
            JournalEntry.reversed_entry_id == contribution["journal_entry_id"]
        )
    )
    assert result.scalar() == 1


# ---------------------------------------------------------------------------
# Read-only safety
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_dashboard_view_creates_no_journal_entries(
    client, auth_headers, test_user, db, tenant_context
):
    await tenant_context(test_user.organization_id)
    before = await count_rows(
        db, JournalEntry, JournalEntry.tenant_id == test_user.organization_id
    )

    response = await client.get("/dashboard/", headers=auth_headers)
    assert response.status_code == 200

    await tenant_context(test_user.organization_id)
    after = await count_rows(
        db, JournalEntry, JournalEntry.tenant_id == test_user.organization_id
    )
    assert before == after


@pytest.mark.integration
@pytest.mark.anyio
async def test_loading_widget_partial_creates_no_journal_entries(
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

    await _post_contribution(client, headers, goal["id"], source, destination)

    await set_tenant_context_async(db, org.id)
    before = await count_rows(db, JournalEntry, JournalEntry.tenant_id == org.id)
    before_accounts = await count_rows(db, Account, Account.tenant_id == org.id)
    before_budgets = await count_rows(db, Budget, Budget.tenant_id == org.id)
    before_bills = await count_rows(db, Bill, Bill.tenant_id == org.id)

    response = await client.get("/dashboard/partials/family-goals", headers=headers)
    assert response.status_code == 200

    await set_tenant_context_async(db, org.id)
    after = await count_rows(db, JournalEntry, JournalEntry.tenant_id == org.id)
    after_accounts = await count_rows(db, Account, Account.tenant_id == org.id)
    after_budgets = await count_rows(db, Budget, Budget.tenant_id == org.id)
    after_bills = await count_rows(db, Bill, Bill.tenant_id == org.id)

    assert before == after
    assert before_accounts == after_accounts
    assert before_budgets == after_budgets
    assert before_bills == after_bills


# ---------------------------------------------------------------------------
# RLS / tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_contribution_on_dashboard(
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
    destination_a = await _create_shared_asset_account(db, org_a.id, unique("Dest A"))
    await db.commit()

    await _post_contribution(client, headers_a, goal_a["id"], source_a, destination_a, amount="333.000")

    await _create_family(client, headers_b, name="Family B")
    response_b = await client.get("/dashboard/partials/family-goals", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert "333.000" not in response_b.text
    assert goal_a["name"] not in response_b.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_and_journal_tables_via_dashboard(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")
