"""Family account visibility and shared/private data rules.

Covers role-based account visibility, management permissions, posting safety,
and tenant isolation.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.rls import set_tenant_context_async
from app.models import Account, Family, FamilyRole
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
    create_test_family_member,
    create_test_organization,
    create_test_user,
)


async def _setup_family_with_roles(db, unique):
    """Create a tenant with a head, parent, two adults, teen, child, and viewer."""
    org = await create_test_organization(db, name=unique("FamilyOrg"), slug=unique("family-org"))
    await set_tenant_context_async(db, org.id)

    head, _ = await create_test_user(
        db, org, email=unique("head") + "@example.com", role="owner"
    )
    parent, _ = await create_test_user(
        db, org, email=unique("parent") + "@example.com", role="editor"
    )
    adult1, _ = await create_test_user(
        db, org, email=unique("adult1") + "@example.com", role="viewer"
    )
    adult2, _ = await create_test_user(
        db, org, email=unique("adult2") + "@example.com", role="viewer"
    )
    teen, _ = await create_test_user(
        db, org, email=unique("teen") + "@example.com", role="viewer"
    )
    child, _ = await create_test_user(
        db, org, email=unique("child") + "@example.com", role="viewer"
    )
    viewer, _ = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    family = Family(tenant_id=org.id, name=unique("Family"), currency="OMR")
    db.add(family)
    await db.flush()
    await db.refresh(family)

    await create_test_family_member(db, family.id, org.id, head, FamilyRole.HEAD.value)
    await create_test_family_member(db, family.id, org.id, parent, FamilyRole.PARENT.value)
    await create_test_family_member(db, family.id, org.id, adult1, FamilyRole.ADULT.value)
    await create_test_family_member(db, family.id, org.id, adult2, FamilyRole.ADULT.value)
    await create_test_family_member(db, family.id, org.id, teen, FamilyRole.TEEN.value)
    await create_test_family_member(db, family.id, org.id, child, FamilyRole.CHILD.value)
    await create_test_family_member(db, family.id, org.id, viewer, FamilyRole.VIEWER.value)
    await db.commit()

    users = {
        "head": head,
        "parent": parent,
        "adult1": adult1,
        "adult2": adult2,
        "teen": teen,
        "child": child,
        "viewer": viewer,
    }
    return org, family, users


async def _login(client, user, password: str = "SecurePass123!") -> dict[str, str]:
    return await auth_headers_for(client, user.email, password)


async def _setup_accounts(db, org, users, unique):
    """Create accounts with different visibilities and owners."""
    shared = await create_test_account(
        db,
        org.id,
        code=unique("shared"),
        name=unique("Shared Account"),
        account_type="Asset",
        visibility="shared",
    )
    family_account = await create_test_account(
        db,
        org.id,
        code=unique("family"),
        name=unique("Family Account"),
        account_type="Asset",
        visibility="family",
    )
    head_private = await create_test_account(
        db,
        org.id,
        code=unique("headpriv"),
        name=unique("Head Private Account"),
        account_type="Asset",
        visibility="private",
        owner_user_id=users["head"].id,
    )
    adult1_private = await create_test_account(
        db,
        org.id,
        code=unique("a1priv"),
        name=unique("Adult1 Private Account"),
        account_type="Asset",
        visibility="private",
        owner_user_id=users["adult1"].id,
    )
    adult2_private = await create_test_account(
        db,
        org.id,
        code=unique("a2priv"),
        name=unique("Adult2 Private Account"),
        account_type="Asset",
        visibility="private",
        owner_user_id=users["adult2"].id,
    )
    teen_private = await create_test_account(
        db,
        org.id,
        code=unique("teenpriv"),
        name=unique("Teen Private Account"),
        account_type="Asset",
        visibility="private",
        owner_user_id=users["teen"].id,
    )
    shared_expense = await create_test_account(
        db,
        org.id,
        code=unique("sharedexp"),
        name=unique("Shared Expense"),
        account_type="Expense",
        visibility="shared",
    )
    await db.commit()
    return {
        "shared": shared,
        "family": family_account,
        "head_private": head_private,
        "adult1_private": adult1_private,
        "adult2_private": adult2_private,
        "teen_private": teen_private,
        "shared_expense": shared_expense,
    }


async def _visible_account_ids(client, headers):
    response = await client.get("/family/accounts/visible", headers=headers)
    assert response.status_code == 200, response.text
    return {a["id"] for a in response.json()}


@pytest.mark.integration
@pytest.mark.anyio
async def test_head_and_parent_can_see_all_family_accounts(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    for role in ("head", "parent"):
        headers = await _login(client, users[role])
        visible = await _visible_account_ids(client, headers)
        expected = {a.id for a in accounts.values()}
        assert visible == expected, f"{role} should see all accounts"


@pytest.mark.integration
@pytest.mark.anyio
async def test_adult_can_see_shared_family_and_own_private_only(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    headers = await _login(client, users["adult1"])
    visible = await _visible_account_ids(client, headers)

    expected = {
        accounts["shared"].id,
        accounts["family"].id,
        accounts["adult1_private"].id,
        accounts["shared_expense"].id,
    }
    assert visible == expected
    assert accounts["adult2_private"].id not in visible
    assert accounts["head_private"].id not in visible
    assert accounts["teen_private"].id not in visible


@pytest.mark.integration
@pytest.mark.anyio
async def test_teen_child_and_viewer_visibility(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    teen_headers = await _login(client, users["teen"])
    teen_visible = await _visible_account_ids(client, teen_headers)
    assert accounts["shared"].id in teen_visible
    assert accounts["family"].id in teen_visible
    assert accounts["teen_private"].id in teen_visible
    assert accounts["adult1_private"].id not in teen_visible

    child_headers = await _login(client, users["child"])
    child_visible = await _visible_account_ids(client, child_headers)
    assert accounts["shared"].id in child_visible
    assert accounts["family"].id in child_visible
    assert accounts["adult1_private"].id not in child_visible

    viewer_headers = await _login(client, users["viewer"])
    viewer_visible = await _visible_account_ids(client, viewer_headers)
    assert accounts["shared"].id in viewer_visible
    assert accounts["family"].id in viewer_visible
    assert accounts["adult1_private"].id not in viewer_visible


@pytest.mark.integration
@pytest.mark.anyio
async def test_account_detail_rejects_unauthorized_private_account(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    adult1_headers = await _login(client, users["adult1"])
    response = await client.get(
        f"/accounts/{accounts['adult2_private'].id}", headers=adult1_headers
    )
    assert response.status_code == 403

    head_headers = await _login(client, users["head"])
    response = await client.get(
        f"/accounts/{accounts['adult2_private'].id}", headers=head_headers
    )
    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.anyio
async def test_make_account_shared_or_private_requires_manage_permission(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    viewer_headers = await _login(client, users["viewer"])
    response = await client.post(
        f"/family/accounts/{accounts['adult1_private'].id}/share",
        headers=viewer_headers,
    )
    assert response.status_code == 403

    response = await client.post(
        f"/family/accounts/{accounts['shared'].id}/make-private",
        headers=viewer_headers,
    )
    assert response.status_code == 403

    adult1_headers = await _login(client, users["adult1"])
    response = await client.post(
        f"/family/accounts/{accounts['adult1_private'].id}/share",
        headers=adult1_headers,
    )
    assert response.status_code == 200
    assert response.json()["visibility"] == "shared"


@pytest.mark.integration
@pytest.mark.anyio
async def test_unauthorized_member_cannot_change_visibility(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    viewer_headers = await _login(client, users["viewer"])
    response = await client.patch(
        f"/accounts/{accounts['shared'].id}/visibility",
        json={"visibility": "private"},
        headers=viewer_headers,
    )
    assert response.status_code == 403

    teen_headers = await _login(client, users["teen"])
    response = await client.patch(
        f"/accounts/{accounts['shared'].id}/visibility",
        json={"visibility": "private"},
        headers=teen_headers,
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.anyio
async def test_bill_mark_paid_rejects_inaccessible_payment_account(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    bill_payload = {
        "name": "Electricity",
        "provider": "Majan",
        "typical_amount": "45.000",
        "due_date": (date.today() + timedelta(days=5)).isoformat(),
        "frequency": "monthly",
        "payment_account_id": accounts["adult2_private"].id,
        "expense_account_id": accounts["shared_expense"].id,
    }

    adult1_headers = await _login(client, users["adult1"])
    create_response = await client.post("/bills", json=bill_payload, headers=adult1_headers)
    assert create_response.status_code == 200, create_response.text
    bill_id = create_response.json()["id"]

    response = await client.post(
        f"/bills/{bill_id}/mark-paid", headers=adult1_headers
    )
    assert response.status_code == 400
    assert "permission" in response.text.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_subscription_mark_paid_rejects_inaccessible_payment_account(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    sub_payload = {
        "name": "Mobile",
        "provider": "Ooredoo",
        "amount": "15.000",
        "frequency": "monthly",
        "next_billing_date": (date.today() + timedelta(days=10)).isoformat(),
        "payment_account_id": accounts["adult2_private"].id,
        "expense_account_id": accounts["shared_expense"].id,
    }

    adult1_headers = await _login(client, users["adult1"])
    create_response = await client.post("/subscriptions", json=sub_payload, headers=adult1_headers)
    assert create_response.status_code == 200, create_response.text
    sub_id = create_response.json()["id"]

    response = await client.post(
        f"/subscriptions/{sub_id}/mark-paid", headers=adult1_headers
    )
    assert response.status_code == 400
    assert "permission" in response.text.lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_csv_import_confirm_rejects_inaccessible_bank_account(client, db, unique):
    org, family, users = await _setup_family_with_roles(db, unique)
    accounts = await _setup_accounts(db, org, users, unique)

    csv_content = "Date,Description,Amount\n2026-07-01,Test Expense,-45.000\n"
    adult1_headers = await _login(client, users["adult1"])

    upload_response = await client.post(
        "/imports/csv/upload",
        json={"original_filename": "test.csv", "file_content": csv_content},
        headers=adult1_headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    job_id = upload_response.json()["job_id"]

    response = await client.post(
        f"/imports/{job_id}/confirm",
        json={
            "bank_account_id": accounts["adult2_private"].id,
            "default_expense_account_id": accounts["shared_expense"].id,
        },
        headers=adult1_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["imported_rows"] == 0
    assert data["skipped_rows"] == 1

    # Confirm the row was skipped due to account access, not posted.
    rows_response = await client.get(
        f"/imports/{job_id}/rows?status=invalid", headers=adult1_headers
    )
    rows = rows_response.json()["rows"]
    assert any(
        any("permission" in err for err in (r["validation_errors"] or []))
        for r in rows
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_accounts(client, db, unique):
    org_a, family_a, users_a = await _setup_family_with_roles(db, unique)
    accounts_a = await _setup_accounts(db, org_a, users_a, unique)

    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, _ = await create_test_user(db, org_b, email=unique("user_b") + "@example.com", role="owner")

    head_a_headers = await _login(client, users_a["head"])
    b_headers = await _login(client, user_b)

    response = await client.get(
        f"/accounts/{accounts_a['shared'].id}", headers=b_headers
    )
    assert response.status_code == 404

    visible = await _visible_account_ids(client, b_headers)
    assert accounts_a["shared"].id not in visible


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_accounts_table(db):
    await assert_rls_enabled(db, "accounts")
