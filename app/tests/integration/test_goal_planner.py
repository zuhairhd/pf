"""Goal Planner integration tests.

These tests use synthetic goal data only and verify that the planner is
read-only, tenant-scoped, and produces deterministic projections.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.rls import set_tenant_context_async
from app.models import Goal, GoalContribution, GoalStatus, GoalVisibility, JournalEntry
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


async def _create_account(client, headers, code: str, name: str, account_type: str, **kwargs):
    response = await client.post(
        "/accounts/",
        json={"code": code, "name": name, "account_type": account_type, **kwargs},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _post_journal_entry(client, headers, lines: list[dict], narration: str = "Test entry"):
    response = await client.post(
        "/transactions/",
        json={
            "date": date.today().isoformat(),
            "narration": narration,
            "lines": lines,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _count_journal_entries(db):
    result = await db.execute(select(func.count(JournalEntry.id)))
    return result.scalar()


async def _count_goals(db):
    result = await db.execute(select(func.count(Goal.id)))
    return result.scalar()


async def _count_contributions(db):
    result = await db.execute(select(func.count(GoalContribution.id)))
    return result.scalar()


async def _create_goal(
    db,
    tenant_context,
    tenant_id: int,
    user_id: int,
    name: str,
    target: str,
    current: str = "0.000",
    monthly: str = "0.000",
    visibility: str = "private",
    target_date: date | None = None,
    priority: int = 1,
):
    await tenant_context(tenant_id)
    goal = Goal(
        tenant_id=tenant_id,
        name=name,
        target_amount=Decimal(target),
        current_amount=Decimal(current),
        monthly_contribution=Decimal(monthly),
        visibility=visibility,
        owner_user_id=user_id,
        status=GoalStatus.ACTIVE.value,
        target_date=target_date,
        priority=priority,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


@pytest.mark.integration
@pytest.mark.anyio
async def test_modes_catalog_requires_auth(client):
    response = await client.get("/ai/goal-planner/modes")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_modes_catalog_returns_modes_and_strategies(client, auth_headers):
    response = await client.get("/ai/goal-planner/modes", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    modes = {m["mode"] for m in data["modes"]}
    assert "single_goal_feasibility" in modes
    assert "hypothetical_goal" in modes
    assert "multi_goal_prioritization" in modes
    assert "deadline_rescue" in modes
    assert "family_goal_plan" in modes
    strategies = {s["strategy"] for s in data["strategies"]}
    assert "equal_split" in strategies
    assert "priority_first" in strategies
    assert "closest_deadline" in strategies
    assert "lowest_gap_first" in strategies


@pytest.mark.integration
@pytest.mark.anyio
async def test_single_goal_calculates_required_contribution(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    target_date = date.today() + timedelta(days=120)
    goal = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Vacation",
        "1200.000",
        "0.000",
        "0.000",
        target_date=target_date,
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    goal_data = data["goal"]
    assert goal_data["goal_id"] == goal.id
    assert goal_data["remaining_amount"] == "1200.000"
    assert Decimal(goal_data["required_monthly_contribution"]) > Decimal("0")
    assert goal_data["on_track"] is False
    assert goal_data["deadline_risk"] == "high"


@pytest.mark.integration
@pytest.mark.anyio
async def test_single_goal_detects_on_track(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    target_date = date.today() + timedelta(days=365)
    goal = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Car",
        "1200.000",
        "0.000",
        "200.000",
        target_date=target_date,
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    goal_data = response.json()["result"]["goal"]
    assert goal_data["on_track"] is True
    assert goal_data["deadline_risk"] == "low"


@pytest.mark.integration
@pytest.mark.anyio
async def test_single_goal_override_contribution(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    target_date = date.today() + timedelta(days=180)
    goal = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Education",
        "1000.000",
        "0.000",
        "0.000",
        target_date=target_date,
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
            "monthly_contribution": "100.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    goal_data = response.json()["result"]["goal"]
    assert goal_data["monthly_contribution"] == "100.000"
    assert goal_data["months_to_completion"] == 10


@pytest.mark.integration
@pytest.mark.anyio
async def test_hypothetical_goal_calculates_months_to_target(client, auth_headers):
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "hypothetical_goal",
            "goal_name": "New Phone",
            "target_amount": "600.000",
            "current_amount": "0.000",
            "target_date": (date.today() + timedelta(days=120)).isoformat(),
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["target_amount"] == "600.000"
    assert Decimal(data["required_monthly_contribution"]) > Decimal("0")
    assert data["months_to_completion"] is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_hypothetical_goal_missing_target_date(client, auth_headers):
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "hypothetical_goal",
            "goal_name": "Generic Goal",
            "target_amount": "600.000",
            "monthly_contribution": "100.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["months_to_completion"] == 6


@pytest.mark.integration
@pytest.mark.anyio
async def test_hypothetical_goal_rejects_invalid_amount(client, auth_headers):
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "hypothetical_goal",
            "target_amount": "-100.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.anyio
async def test_multi_goal_equal_split(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    g1 = await _create_goal(db, tenant_context, user.organization_id, user.id, "A", "1000.000")
    g2 = await _create_goal(db, tenant_context, user.organization_id, user.id, "B", "1000.000")

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "multi_goal_prioritization",
            "available_monthly_savings": "100.000",
            "strategy": "equal_split",
            "goal_ids": [g1.id, g2.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["strategy"] == "equal_split"
    assert data["total_allocated"] == "100.000"
    allocations = {a["goal_id"]: a["monthly_contribution"] for a in data["goals"]}
    assert Decimal(allocations[g1.id]) == Decimal("50.000")
    assert Decimal(allocations[g2.id]) == Decimal("50.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_multi_goal_priority_first(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    first = await _create_goal(db, tenant_context, user.organization_id, user.id, "First", "500.000", priority=1)
    second = await _create_goal(db, tenant_context, user.organization_id, user.id, "Second", "2000.000", priority=2)

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "multi_goal_prioritization",
            "available_monthly_savings": "100.000",
            "strategy": "priority_first",
            "goal_ids": [first.id, second.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    allocations = {a["goal_id"]: a["monthly_contribution"] for a in data["goals"]}
    assert Decimal(allocations[first.id]) == Decimal("100.000")
    assert Decimal(allocations[second.id]) == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_multi_goal_closest_deadline(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    soon = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Soon",
        "1000.000",
        target_date=date.today() + timedelta(days=30),
        priority=2,
    )
    later = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Later",
        "1000.000",
        target_date=date.today() + timedelta(days=180),
        priority=1,
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "multi_goal_prioritization",
            "available_monthly_savings": "100.000",
            "strategy": "closest_deadline",
            "goal_ids": [soon.id, later.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order = [a["goal_id"] for a in data["goals"]]
    assert order[0] == soon.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_multi_goal_lowest_gap_first(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    small = await _create_goal(db, tenant_context, user.organization_id, user.id, "Small", "500.000", current="400.000")
    large = await _create_goal(db, tenant_context, user.organization_id, user.id, "Large", "2000.000", current="0.000")

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "multi_goal_prioritization",
            "available_monthly_savings": "100.000",
            "strategy": "lowest_gap_first",
            "goal_ids": [small.id, large.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    order = [a["goal_id"] for a in data["goals"]]
    assert order[0] == small.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_multi_goal_insufficient_savings_warning(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    g1 = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Urgent",
        "1000.000",
        target_date=date.today() + timedelta(days=30),
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "multi_goal_prioritization",
            "available_monthly_savings": "10.000",
            "strategy": "equal_split",
            "goal_ids": [g1.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert g1.id in data["goals_at_risk"]
    assert data["total_funding_gap"] > "0"


@pytest.mark.integration
@pytest.mark.anyio
async def test_deadline_rescue_calculates_shortfall_and_options(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    target_date = date.today() + timedelta(days=120)
    goal = await _create_goal(
        db,
        tenant_context,
        user.organization_id,
        user.id,
        "Rescue",
        "1200.000",
        "0.000",
        "50.000",
        target_date=target_date,
    )

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "deadline_rescue",
            "goal_id": goal.id,
            "available_monthly_savings": "300.000",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["goal_id"] == goal.id
    assert Decimal(data["required_monthly_contribution"]) > Decimal("0")
    assert Decimal(data["shortfall"]) > Decimal("0")
    options = {o["option"]: o for o in data["options"]}
    assert "increase_contribution" in options
    assert "extend_deadline" in options
    assert "reduce_target" in options
    assert "reallocate" in options


@pytest.mark.integration
@pytest.mark.anyio
async def test_prioritize_endpoint(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    g1 = await _create_goal(db, tenant_context, user.organization_id, user.id, "P1", "1000.000", priority=1)
    g2 = await _create_goal(db, tenant_context, user.organization_id, user.id, "P2", "1000.000", priority=2)

    response = await client.post(
        "/ai/goal-planner/prioritize",
        json={
            "available_monthly_savings": "100.000",
            "strategy": "equal_split",
            "goal_ids": [g1.id, g2.id],
            "months": 6,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["result"]
    assert data["strategy"] == "equal_split"
    assert data["goal_count"] == 2


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_private_goal_rejected(
    client, db, unique, tenant_context
):
    org = await create_test_organization(db, name=unique("Goal Plan Org"), slug=unique("goal-plan-org"))
    user_a, password_a = await create_test_user(db, org, email=unique("a") + "@example.com", role="viewer")
    user_b, password_b = await create_test_user(db, org, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await tenant_context(org.id)
    goal = Goal(
        tenant_id=org.id,
        name="Private Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("50.000"),
        visibility=GoalVisibility.PRIVATE.value,
        owner_user_id=user_b.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=headers_a,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_plan_tenant_b_goal(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)

    await set_tenant_context_async(db, org_b.id)
    goal_b = Goal(
        tenant_id=org_b.id,
        name="B Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("0.000"),
        visibility=GoalVisibility.SHARED.value,
        owner_user_id=user_b.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal_b)
    await db.commit()
    await db.refresh(goal_b)

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal_b.id,
        },
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_access_private_goal_details(
    client, db, unique, tenant_context
):
    org = await create_test_organization(db, name=unique("Viewer Org"), slug=unique("viewer-org"))
    viewer, viewer_pass = await create_test_user(db, org, email=unique("viewer") + "@example.com", role="viewer")
    owner, owner_pass = await create_test_user(db, org, email=unique("owner") + "@example.com", role="owner")

    headers_viewer = await auth_headers_for(client, viewer.email, viewer_pass)

    await tenant_context(org.id)
    goal = Goal(
        tenant_id=org.id,
        name="Private Detail Goal",
        target_amount=Decimal("1000.000"),
        current_amount=Decimal("0.000"),
        monthly_contribution=Decimal("50.000"),
        visibility=GoalVisibility.PRIVATE.value,
        owner_user_id=owner.id,
        status=GoalStatus.ACTIVE.value,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=headers_viewer,
    )
    assert response.status_code == 403
    assert "Private Detail Goal" not in response.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_planner_does_not_modify_goals(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    goal = await _create_goal(db, tenant_context, user.organization_id, user.id, "ReadOnly", "800.000")

    goals_before = await _count_goals(db)
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    goals_after = await _count_goals(db)
    assert goals_before == goals_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_planner_does_not_create_contributions_or_journals(
    client, auth_headers, db, tenant_context, test_user_credentials
):
    user = test_user_credentials["user"]
    goal = await _create_goal(db, tenant_context, user.organization_id, user.id, "NoSideEffects", "500.000")

    contributions_before = await _count_contributions(db)
    entries_before = await _count_journal_entries(db)
    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    contributions_after = await _count_contributions(db)
    entries_after = await _count_journal_entries(db)
    assert contributions_before == contributions_after
    assert entries_before == entries_after


@pytest.mark.integration
@pytest.mark.anyio
async def test_deterministic_narrative_without_api_key(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    goal = await _create_goal(db, tenant_context, user.organization_id, user.id, "Narrative", "500.000")

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
            "include_narrative": True,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    narrative = response.json()["result"]["narrative"]
    assert "Goal planning mode:" in narrative
    assert "educational" in narrative.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_disclaimer_present(client, auth_headers, db, tenant_context, test_user_credentials):
    user = test_user_credentials["user"]
    goal = await _create_goal(db, tenant_context, user.organization_id, user.id, "Disclaimer", "500.000")

    response = await client.post(
        "/ai/goal-planner/plan",
        json={
            "mode": "single_goal_feasibility",
            "goal_id": goal.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert "educational" in response.json()["disclaimer"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_goal_tables(db):
    await assert_rls_enabled(db, "goals")
    await assert_rls_enabled(db, "goal_contributions")
