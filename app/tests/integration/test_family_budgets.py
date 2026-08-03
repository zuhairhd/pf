"""Family budgets integration tests (FAM-1303).

Covers budget CRUD, visibility/permissions, budget categories linked to
expense accounts, budget-vs-actual calculation from posted journal
entries, and tenant/RLS isolation. Uses synthetic data only.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Account, JournalEntry, JournalLine
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
    create_test_organization,
    create_test_user,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def private_budget_payload():
    today = date.today()
    return {
        "name": "Personal Spending",
        "period": "monthly",
        "start_date": today.replace(day=1).isoformat(),
        "end_date": (today.replace(day=1) + timedelta(days=29)).isoformat(),
        "visibility": "private",
        "categories": [],
    }


@pytest.fixture
def shared_budget_payload():
    today = date.today()
    return {
        "name": "Household Budget",
        "period": "monthly",
        "start_date": today.replace(day=1).isoformat(),
        "end_date": (today.replace(day=1) + timedelta(days=29)).isoformat(),
        "visibility": "shared",
        "categories": [],
    }


@pytest.fixture
def family_budget_payload():
    today = date.today()
    return {
        "name": "Family Groceries",
        "period": "monthly",
        "start_date": today.replace(day=1).isoformat(),
        "end_date": (today.replace(day=1) + timedelta(days=29)).isoformat(),
        "visibility": "family",
        "categories": [],
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


async def _create_budget(client, headers, payload):
    response = await client.post("/family/budgets", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _create_expense_account(client, headers, code: str, name: str):
    response = await client.post(
        "/accounts/",
        json={"code": code, "name": name, "account_type": "Expense"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _post_expense_journal_entry(client, headers, asset_id, expense_id, amount, entry_date):
    response = await client.post(
        "/transactions/",
        json={
            "date": entry_date.isoformat(),
            "narration": "Test expense",
            "lines": [
                {"account_id": expense_id, "debit": str(amount)},
                {"account_id": asset_id, "credit": str(amount)},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Budget CRUD
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_family_budget_requires_auth(client, private_budget_payload):
    response = await client.post("/family/budgets", json=private_budget_payload)
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_can_create_family_budget(client, auth_headers, family_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, family_budget_payload)
    assert budget["visibility"] == "family"
    assert budget["can_manage"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_parent_can_create_family_budget(client, db, unique, shared_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    budget = await _create_budget(client, parent_headers, shared_budget_payload)
    assert budget["owner_user_id"] == parent.id
    assert budget["can_manage"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_can_create_own_private_budget(client, db, unique, private_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    adult, adult_password = await create_test_user(
        db, org, email=unique("adult") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, adult, "adult")

    adult_headers = await auth_headers_for(client, adult.email, adult_password)
    budget = await _create_budget(client, adult_headers, private_budget_payload)
    assert budget["visibility"] == "private"
    assert budget["owner_user_id"] == adult.id


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_create_budget(client, db, unique, private_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post("/family/budgets", json=private_budget_payload, headers=viewer_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_child_cannot_create_budget(client, db, unique, private_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    child, child_password = await create_test_user(
        db, org, email=unique("child") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, child, "child")

    child_headers = await auth_headers_for(client, child.email, child_password)
    response = await client.post("/family/budgets", json=private_budget_payload, headers=child_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_filters_by_visibility(
    client, db, unique, private_budget_payload, shared_budget_payload
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

    shared = await _create_budget(client, head_headers, shared_budget_payload)

    adult_a_headers = await auth_headers_for(client, adult_a.email, adult_a_password)
    private_a = await _create_budget(client, adult_a_headers, private_budget_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    list_response = await client.get("/family/budgets", headers=adult_b_headers)
    assert list_response.status_code == 200, list_response.text
    budget_ids = {b["id"] for b in list_response.json()}
    assert shared["id"] in budget_ids
    assert private_a["id"] not in budget_ids


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_private_budget_detail_rejected(
    client, db, unique, private_budget_payload
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
    private_budget = await _create_budget(client, adult_a_headers, private_budget_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    response = await client.get(f"/family/budgets/{private_budget['id']}", headers=adult_b_headers)
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_archive_requires_permission(client, db, unique, private_budget_payload):
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
    budget = await _create_budget(client, adult_a_headers, private_budget_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    forbidden = await client.post(f"/family/budgets/{budget['id']}/archive", headers=adult_b_headers)
    assert forbidden.status_code == 403

    allowed = await client.post(f"/family/budgets/{budget['id']}/archive", headers=adult_a_headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "archived"
    assert allowed.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Budget categories
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_add_category_linked_to_expense_account(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)
    expense = await _create_expense_account(client, auth_headers, "5500", "Groceries")

    response = await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Groceries", "account_id": expense["id"], "budgeted_amount": "200.000"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["total_budgeted"]) == Decimal("200.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_reject_non_expense_account_category(client, auth_headers, private_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_response = await client.post(
        "/accounts/",
        json={"code": "1500", "name": "Bank", "account_type": "Asset"},
        headers=auth_headers,
    )
    asset = asset_response.json()

    response = await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Bad Category", "account_id": asset["id"], "budgeted_amount": "50.000"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "expense" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_reject_cross_tenant_account_category(
    client, db, unique, tenant_context, private_budget_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    budget = await _create_budget(client, headers_a, private_budget_payload)

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    expense_b = await _create_expense_account(client, headers_b, "5600", "Tenant B Expense")

    response = await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Cross Tenant", "account_id": expense_b["id"], "budgeted_amount": "50.000"},
        headers=headers_a,
    )
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_reject_inaccessible_private_account_category(
    client, db, unique, tenant_context, private_budget_payload
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
    budget = await _create_budget(client, adult_a_headers, private_budget_payload)

    # adult_b creates a private expense account adult_a cannot see.
    await tenant_context(org.id)
    private_expense = await create_test_account(
        db, org.id, code=unique("EXP"), name="Adult B Private Expense",
        account_type="Expense", visibility="private", owner_user_id=adult_b.id,
    )
    await db.commit()

    response = await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Blocked", "account_id": private_expense.id, "budgeted_amount": "50.000"},
        headers=adult_a_headers,
    )
    assert response.status_code == 403
    assert "access" in response.json()["message"].lower()


# ---------------------------------------------------------------------------
# Budget actuals
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_actuals_calculated_from_posted_journal_entries(
    client, auth_headers, private_budget_payload
):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1600", "name": "Cash", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5700", "Dining")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Dining", "account_id": expense["id"], "budgeted_amount": "100.000"},
        headers=auth_headers,
    )

    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=5)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "40.000", mid_period)

    summary_response = await client.get(f"/family/budgets/{budget['id']}/summary", headers=auth_headers)
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    category = summary["categories"][0]
    assert Decimal(category["actual_amount"]) == Decimal("40.000")
    assert Decimal(category["remaining_amount"]) == Decimal("60.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_date_range_filtering_works(client, auth_headers, private_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1700", "name": "Cash2", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5800", "OutOfRange")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "OutOfRange", "account_id": expense["id"], "budgeted_amount": "100.000"},
        headers=auth_headers,
    )

    before_period = date.fromisoformat(private_budget_payload["start_date"]) - timedelta(days=10)
    await _post_expense_journal_entry(
        client, auth_headers, asset["id"], expense["id"], "999.000", before_period
    )

    summary = (
        await client.get(f"/family/budgets/{budget['id']}/summary", headers=auth_headers)
    ).json()
    assert Decimal(summary["categories"][0]["actual_amount"]) == Decimal("0.000")


@pytest.mark.integration
@pytest.mark.anyio
async def test_percent_used_and_over_budget_detection(client, auth_headers, private_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1800", "name": "Cash3", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "5900", "Overspent")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "Overspent", "account_id": expense["id"], "budgeted_amount": "50.000", "alert_threshold": "80"},
        headers=auth_headers,
    )

    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=3)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "75.000", mid_period)

    summary = (
        await client.get(f"/family/budgets/{budget['id']}/summary", headers=auth_headers)
    ).json()
    category = summary["categories"][0]
    assert Decimal(category["percent_used"]) == Decimal("150.00")
    assert category["is_over_budget"] is True
    assert budget["id"] in [budget["id"]]  # sanity
    assert category["id"] in summary["over_budget_category_ids"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_near_limit_category_detected(client, auth_headers, private_budget_payload):
    await _create_family(client, auth_headers)
    budget = await _create_budget(client, auth_headers, private_budget_payload)

    asset_resp = await client.post(
        "/accounts/", json={"code": "1900", "name": "Cash4", "account_type": "Asset"}, headers=auth_headers
    )
    asset = asset_resp.json()
    expense = await _create_expense_account(client, auth_headers, "6000", "NearLimit")

    await client.post(
        f"/family/budgets/{budget['id']}/categories",
        json={"name": "NearLimit", "account_id": expense["id"], "budgeted_amount": "100.000", "alert_threshold": "80"},
        headers=auth_headers,
    )

    mid_period = date.fromisoformat(private_budget_payload["start_date"]) + timedelta(days=3)
    await _post_expense_journal_entry(client, auth_headers, asset["id"], expense["id"], "85.000", mid_period)

    summary = (
        await client.get(f"/family/budgets/{budget['id']}/summary", headers=auth_headers)
    ).json()
    category = summary["categories"][0]
    assert category["is_near_limit"] is True
    assert category["is_over_budget"] is False
    assert category["id"] in summary["near_limit_category_ids"]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_and_parent_can_manage_family_budget(
    client, db, unique, family_budget_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    parent, parent_password = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, parent, "parent")

    budget = await _create_budget(client, head_headers, family_budget_payload)

    parent_headers = await auth_headers_for(client, parent.email, parent_password)
    response = await client.patch(
        f"/family/budgets/{budget['id']}",
        json={"name": "Renamed by parent"},
        headers=parent_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Renamed by parent"


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_cannot_manage_another_adults_private_budget(
    client, db, unique, private_budget_payload
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
    budget = await _create_budget(client, adult_a_headers, private_budget_payload)

    adult_b_headers = await auth_headers_for(client, adult_b.email, adult_b_password)
    response = await client.patch(
        f"/family/budgets/{budget['id']}",
        json={"name": "Hijacked"},
        headers=adult_b_headers,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_can_view_shared_but_not_manage(
    client, db, unique, shared_budget_payload, private_budget_payload
):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    teen, teen_password = await create_test_user(
        db, org, email=unique("teen") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, teen, "teen")

    shared = await _create_budget(client, head_headers, shared_budget_payload)

    teen_headers = await auth_headers_for(client, teen.email, teen_password)
    view_response = await client.get(f"/family/budgets/{shared['id']}", headers=teen_headers)
    assert view_response.status_code == 200, view_response.text

    manage_response = await client.patch(
        f"/family/budgets/{shared['id']}", json={"name": "Teen edit"}, headers=teen_headers
    )
    assert manage_response.status_code == 403

    own_private = await _create_budget(client, teen_headers, private_budget_payload)
    own_manage = await client.patch(
        f"/family/budgets/{own_private['id']}", json={"name": "Teen private edit"}, headers=teen_headers
    )
    assert own_manage.status_code == 200, own_manage.text


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_is_read_only(client, db, unique, shared_budget_payload):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await _create_family(client, head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    shared = await _create_budget(client, head_headers, shared_budget_payload)

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    view_response = await client.get(f"/family/budgets/{shared['id']}", headers=viewer_headers)
    assert view_response.status_code == 200

    manage_response = await client.patch(
        f"/family/budgets/{shared['id']}", json={"name": "Viewer edit"}, headers=viewer_headers
    )
    assert manage_response.status_code == 403


# ---------------------------------------------------------------------------
# Tenant / RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_budgets(client, db, unique, shared_budget_payload):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    budget_a = await _create_budget(client, headers_a, shared_budget_payload)

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    await _create_family(client, headers_b)

    list_b = await client.get("/family/budgets", headers=headers_b)
    assert budget_a["id"] not in {b["id"] for b in list_b.json()}

    detail_b = await client.get(f"/family/budgets/{budget_a['id']}", headers=headers_b)
    assert detail_b.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_use_tenant_b_account_in_budget(
    client, db, unique, private_budget_payload
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    await _create_family(client, headers_a)
    budget_a = await _create_budget(client, headers_a, private_budget_payload)

    headers_b = await auth_headers_for(client, user_b.email, password_b)
    expense_b = await _create_expense_account(client, headers_b, "5100", "Tenant B Expense")

    response = await client.post(
        f"/family/budgets/{budget_a['id']}/categories",
        json={"name": "Cross", "account_id": expense_b["id"], "budgeted_amount": "10.000"},
        headers=headers_a,
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_budget_tables(db):
    await assert_rls_enabled(db, "budgets")
    await assert_rls_enabled(db, "budget_categories")


# ---------------------------------------------------------------------------
# Regression: legacy /budgets router
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_legacy_budgets_route_requires_auth(client):
    response = await client.get("/budgets/")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_legacy_budgets_route_create_and_list(client, auth_headers):
    payload = {
        "name": "Legacy Budget",
        "period": "monthly",
        "start_date": date.today().replace(day=1).isoformat(),
        "end_date": (date.today().replace(day=1) + timedelta(days=29)).isoformat(),
        "categories": [],
    }
    create_response = await client.post("/budgets/", json=payload, headers=auth_headers)
    assert create_response.status_code == 200, create_response.text
    assert create_response.json()["visibility"] == "private"

    list_response = await client.get("/budgets/", headers=auth_headers)
    assert list_response.status_code == 200, list_response.text
    names = {b["name"] for b in list_response.json()}
    assert "Legacy Budget" in names
