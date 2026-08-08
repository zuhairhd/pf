"""Account opening balance tests (ACC-502).

Covers posting configured opening balances into real, idempotent journal
entries through the existing AccountingService engine, normal-balance
rules, permission gating, tenant isolation, RLS, and read-only-adjacent
safety (no unrelated financial records touched).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.rls import set_tenant_context_async
from app.models import (
    Bill,
    Budget,
    FamilyInvitation,
    Goal,
    GoalContribution,
    JournalEntry,
    JournalLine,
)
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    count_rows,
    create_test_organization,
    create_test_user,
)


async def _create_account(client, headers, **overrides):
    payload = {
        "code": overrides.pop("code"),
        "name": overrides.pop("name"),
        "account_type": overrides.pop("account_type"),
        **overrides,
    }
    response = await client.post("/accounts/", json=payload, headers=headers)
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


# ---------------------------------------------------------------------------
# Posting behavior
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_opening_balance_posted_for_nonzero_account(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset",
        opening_balance="500.000",
    )

    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["accounts_posted"] == 1
    assert data["accounts_already_posted"] == 0

    result_row = next(r for r in data["results"] if r["account_id"] == account["id"])
    assert result_row["status"] == "posted"
    assert result_row["journal_entry_id"] is not None


@pytest.mark.integration
@pytest.mark.anyio
async def test_journal_entry_balances_debits_and_credits(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="500.000"
    )
    await _create_account(
        client, headers, code="2000", name="Credit Card", account_type="Liability", opening_balance="150.000"
    )

    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_debit"] == data["total_credit"]
    assert Decimal(str(data["total_debit"])) == Decimal("650.000")

    await set_tenant_context_async(db, org.id)
    result = await db.execute(select(JournalEntry).where(JournalEntry.tenant_id == org.id))
    entries = result.scalars().all()
    assert len(entries) == 2
    for entry in entries:
        lines_result = await db.execute(select(JournalLine).where(JournalLine.journal_entry_id == entry.id))
        lines = list(lines_result.scalars().all())
        assert len(lines) == 2
        assert sum(l.debit for l in lines) == sum(l.credit for l in lines)


@pytest.mark.integration
@pytest.mark.anyio
async def test_zero_balance_account_skipped(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1010", name="Empty Wallet", account_type="Asset", opening_balance="0"
    )

    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    result_row = next(r for r in data["results"] if r["account_id"] == account["id"])
    assert result_row["status"] == "skipped_zero"
    assert result_row["journal_entry_id"] is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_account_without_opening_balance_skipped(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1020", name="No Opening Set", account_type="Asset"
    )

    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    result_row = next(r for r in data["results"] if r["account_id"] == account["id"])
    assert result_row["status"] == "skipped_no_balance"
    assert result_row["journal_entry_id"] is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_repeated_posting_is_idempotent(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="300.000"
    )

    first = await client.post("/accounts/opening-balances/post", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["accounts_posted"] == 1

    second = await client.post("/accounts/opening-balances/post", headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["accounts_posted"] == 0
    assert second.json()["accounts_already_posted"] == 1

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(JournalEntry).where(
            JournalEntry.tenant_id == org.id,
            JournalEntry.narration.like("Opening balance:%"),
        )
    )
    entries = result.scalars().all()
    assert len(entries) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_status_endpoint_detects_already_posted(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="500.000"
    )

    before = await client.get("/accounts/opening-balances/status", headers=headers)
    assert before.status_code == 200, before.text
    before_row = next(r for r in before.json()["results"] if r["account_id"] == account["id"])
    assert before_row["status"] == "pending"

    post_response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert post_response.status_code == 200, post_response.text

    after = await client.get("/accounts/opening-balances/status", headers=headers)
    assert after.status_code == 200, after.text
    after_row = next(r for r in after.json()["results"] if r["account_id"] == account["id"])
    assert after_row["status"] == "already_posted"
    assert after_row["journal_entry_id"] is not None


# ---------------------------------------------------------------------------
# Normal balance rules
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_asset_normal_balance_debits_account(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="200.000"
    )
    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    journal_entry_id = next(
        r for r in response.json()["results"] if r["account_id"] == account["id"]
    )["journal_entry_id"]

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(JournalLine).where(
            JournalLine.journal_entry_id == journal_entry_id,
            JournalLine.account_id == account["id"],
        )
    )
    line = result.scalar_one()
    assert Decimal(str(line.debit)) == Decimal("200.000")
    assert Decimal(str(line.credit)) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_liability_normal_balance_credits_account(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="2000", name="Credit Card", account_type="Liability", opening_balance="150.000"
    )
    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    journal_entry_id = next(
        r for r in response.json()["results"] if r["account_id"] == account["id"]
    )["journal_entry_id"]

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(JournalLine).where(
            JournalLine.journal_entry_id == journal_entry_id,
            JournalLine.account_id == account["id"],
        )
    )
    line = result.scalar_one()
    assert Decimal(str(line.credit)) == Decimal("150.000")
    assert Decimal(str(line.debit)) == Decimal("0")


@pytest.mark.integration
@pytest.mark.anyio
async def test_opening_balance_equity_account_reused_across_multiple_accounts(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="100.000"
    )
    await _create_account(
        client, headers, code="1010", name="Bank", account_type="Asset", opening_balance="200.000"
    )

    response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    equity_id = data["opening_balance_equity_account_id"]
    assert equity_id is not None
    # The equity account is created mid-run, so it wasn't in the account list
    # this same call started with -- it never receives its own posting here.
    assert equity_id not in [r["account_id"] for r in data["results"]]

    # A follow-up call resolves the now-existing equity account up front and
    # must always report it as the offset account, never post it against
    # itself, and never create a third journal entry.
    second = await client.post("/accounts/opening-balances/post", headers=headers)
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["opening_balance_equity_account_id"] == equity_id
    equity_row = next(r for r in second_data["results"] if r["account_id"] == equity_id)
    assert equity_row["status"] == "skipped_offset_account"
    assert second_data["accounts_posted"] == 0


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_post_requires_auth(client):
    response = await client.post("/accounts/opening-balances/post")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_status_requires_auth(client):
    response = await client.get("/accounts/opening-balances/status")
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_post_opening_balances(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await client.post("/family", json={"name": "Test Family", "currency": "OMR"}, headers=head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    await _create_account(
        client, head_headers, code="1000", name="Cash", account_type="Asset", opening_balance="500.000"
    )

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.post("/accounts/opening-balances/post", headers=viewer_headers)
    assert response.status_code == 403, response.text

    await set_tenant_context_async(db, org.id)
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.tenant_id == org.id)
    )
    assert result.scalars().first() is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_viewer_cannot_view_opening_balance_status(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    viewer, viewer_password = await create_test_user(
        db, org, email=unique("viewer") + "@example.com", role="viewer"
    )

    head_headers = await auth_headers_for(client, head.email, head_password)
    await client.post("/family", json={"name": "Test Family", "currency": "OMR"}, headers=head_headers)
    await _add_member(client, head_headers, viewer, "viewer")

    viewer_headers = await auth_headers_for(client, viewer.email, viewer_password)
    response = await client.get("/accounts/opening-balances/status", headers=viewer_headers)
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Tenant isolation / RLS
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_accounts_never_posted(client, db, unique):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a, email=unique("a") + "@example.com", role="owner")
    user_b, password_b = await create_test_user(db, org_b, email=unique("b") + "@example.com", role="owner")

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    account_a = await _create_account(
        client, headers_a, code="1000", name="Org A Cash", account_type="Asset", opening_balance="777.000"
    )

    # Tenant B posts its own (empty) opening balances -- must never touch A's account.
    response_b = await client.post("/accounts/opening-balances/post", headers=headers_b)
    assert response_b.status_code == 200, response_b.text
    assert response_b.json()["accounts_considered"] == 0

    status_b = await client.get("/accounts/opening-balances/status", headers=headers_b)
    assert status_b.status_code == 200
    assert account_a["id"] not in [r["account_id"] for r in status_b.json()["results"]]

    await set_tenant_context_async(db, org_a.id)
    result = await db.execute(select(JournalEntry).where(JournalEntry.tenant_id == org_a.id))
    assert result.scalars().first() is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_accounts_and_journal_tables(db):
    await assert_rls_enabled(db, "accounts")
    await assert_rls_enabled(db, "journal_entries")
    await assert_rls_enabled(db, "journal_lines")


# ---------------------------------------------------------------------------
# Read-only-adjacent safety and account update guard
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_opening_balance_actions_do_not_touch_unrelated_records(
    client, db, auth_headers, test_user, tenant_context, unique
):
    await tenant_context(test_user.organization_id)
    before = {
        "budgets": await count_rows(db, Budget, Budget.tenant_id == test_user.organization_id),
        "bills": await count_rows(db, Bill, Bill.tenant_id == test_user.organization_id),
        "goals": await count_rows(db, Goal, Goal.tenant_id == test_user.organization_id),
        "goal_contributions": await count_rows(
            db, GoalContribution, GoalContribution.tenant_id == test_user.organization_id
        ),
        "invitations": await count_rows(
            db, FamilyInvitation, FamilyInvitation.tenant_id == test_user.organization_id
        ),
    }

    await _create_account(
        client, auth_headers, code="1000", name="Cash", account_type="Asset", opening_balance="500.000"
    )
    await client.get("/accounts/opening-balances/status", headers=auth_headers)
    post_response = await client.post("/accounts/opening-balances/post", headers=auth_headers)
    assert post_response.status_code == 200, post_response.text

    await tenant_context(test_user.organization_id)
    after = {
        "budgets": await count_rows(db, Budget, Budget.tenant_id == test_user.organization_id),
        "bills": await count_rows(db, Bill, Bill.tenant_id == test_user.organization_id),
        "goals": await count_rows(db, Goal, Goal.tenant_id == test_user.organization_id),
        "goal_contributions": await count_rows(
            db, GoalContribution, GoalContribution.tenant_id == test_user.organization_id
        ),
        "invitations": await count_rows(
            db, FamilyInvitation, FamilyInvitation.tenant_id == test_user.organization_id
        ),
    }
    assert before == after


@pytest.mark.integration
@pytest.mark.anyio
async def test_cannot_change_opening_balance_after_posted(client, db, unique):
    org = await create_test_organization(db, name=unique("Org"), slug=unique("org"))
    await set_tenant_context_async(db, org.id)
    head, head_password = await create_test_user(db, org, email=unique("head") + "@example.com", role="owner")
    headers = await auth_headers_for(client, head.email, head_password)

    account = await _create_account(
        client, headers, code="1000", name="Cash", account_type="Asset", opening_balance="500.000"
    )
    post_response = await client.post("/accounts/opening-balances/post", headers=headers)
    assert post_response.status_code == 200, post_response.text

    update_response = await client.patch(
        f"/accounts/{account['id']}",
        json={"opening_balance": "999.000"},
        headers=headers,
    )
    assert update_response.status_code == 400, update_response.text
