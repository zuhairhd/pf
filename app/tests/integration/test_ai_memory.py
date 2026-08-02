"""AI Memory System integration tests."""

from __future__ import annotations

import pytest

from app.models import AIMemory
from app.tests.helpers import assert_rls_enabled, auth_headers_for, create_test_user


async def _other_user_headers(client, db, tenant):
    user, password = await create_test_user(db, tenant, role="viewer")
    await db.commit()
    return await auth_headers_for(client, user.email, password), user


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_memory_requires_auth(client):
    response = await client.post(
        "/ai/memory",
        json={"key": "language", "value": "Arabic", "memory_type": "preference"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_memory(client, db, auth_headers):
    response = await client.post(
        "/ai/memory",
        json={
            "memory_type": "preference",
            "key": "language",
            "value": "I prefer Arabic explanations",
            "summary": "Preferred language: Arabic",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["key"] == "language"
    assert data["value"] == "I prefer Arabic explanations"
    assert data["memory_type"] == "preference"
    assert data["is_active"] is True


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_memories(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )
    response = await client.get("/ai/memory", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["memories"]) >= 1
    assert any(m["key"] == "language" for m in data["memories"])


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_memory(client, db, auth_headers):
    created = await client.post(
        "/ai/memory",
        json={"memory_type": "goal_context", "key": "main_goal", "value": "Emergency fund"},
        headers=auth_headers,
    )
    memory_id = created.json()["id"]

    response = await client.get(f"/ai/memory/{memory_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == memory_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_update_memory(client, db, auth_headers):
    created = await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "summary", "value": "Monthly summaries"},
        headers=auth_headers,
    )
    memory_id = created.json()["id"]

    response = await client.patch(
        f"/ai/memory/{memory_id}",
        json={"value": "Weekly summaries", "summary": "Weekly summaries preferred"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Weekly summaries"
    assert data["summary"] == "Weekly summaries preferred"


@pytest.mark.integration
@pytest.mark.anyio
async def test_delete_memory(client, db, auth_headers):
    created = await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "temp", "value": "Temporary"},
        headers=auth_headers,
    )
    memory_id = created.json()["id"]

    delete = await client.delete(f"/ai/memory/{memory_id}", headers=auth_headers)
    assert delete.status_code == 204

    get = await client.get(f"/ai/memory/{memory_id}", headers=auth_headers)
    assert get.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_duplicate_key_updates_existing(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )
    second = await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "English"},
        headers=auth_headers,
    )
    assert second.status_code == 201
    data = second.json()
    assert data["value"] == "English"

    list_response = await client.get("/ai/memory?memory_type=preference", headers=auth_headers)
    items = [m for m in list_response.json()["memories"] if m["key"] == "language"]
    assert len(items) == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_memory_rejects_secret(client, db, auth_headers):
    response = await client.post(
        "/ai/memory",
        json={"memory_type": "custom", "key": "secret", "value": "My password is secret123"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.anyio
async def test_create_memory_rejects_account_number(client, db, auth_headers):
    response = await client.post(
        "/ai/memory",
        json={
            "memory_type": "custom",
            "key": "account",
            "value": "My account number is 1234567890",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.anyio
async def test_search_memories(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic explanations"},
        headers=auth_headers,
    )
    response = await client.post(
        "/ai/memory/search",
        json={"query": "Arabic"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert any("Arabic" in m["value"] for m in response.json()["memories"])


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_memory_isolation(client, db, tenant_pair):
    tenant_a, tenant_b = tenant_pair
    headers_a, _ = await _other_user_headers(client, db, tenant_a)
    headers_b, _ = await _other_user_headers(client, db, tenant_b)

    created = await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=headers_a,
    )
    memory_id = created.json()["id"]

    response_b = await client.get(f"/ai/memory/{memory_id}", headers=headers_b)
    assert response_b.status_code == 404

    list_b = await client.get("/ai/memory", headers=headers_b)
    assert memory_id not in {m["id"] for m in list_b.json()["memories"]}


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_remember_creates_memory(client, db, auth_headers):
    response = await client.post(
        "/ai/chat",
        json={"message": "Remember that I prefer Arabic explanations"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "remember" in data["answer"].lower()

    memories = await client.get("/ai/memory", headers=auth_headers)
    assert any("Arabic" in m["value"] for m in memories.json()["memories"])


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_forget_deactivates_memory(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )

    response = await client.post(
        "/ai/chat",
        json={"message": "Forget language"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "forgotten" in data["answer"].lower() or "couldn't find" in data["answer"].lower()

    list_response = await client.get("/ai/memory", headers=auth_headers)
    assert not any(m["key"] == "language" and m["is_active"] for m in list_response.json()["memories"])


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_what_do_you_remember_returns_summary(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )

    response = await client.post(
        "/ai/chat",
        json={"message": "What do you remember about me?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "Arabic" in data["answer"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_memory_rls_enabled(db):
    await assert_rls_enabled(db, "ai_memories")


@pytest.mark.integration
@pytest.mark.anyio
async def test_no_financial_records_modified(client, db, auth_headers):
    from app.models import Account, Goal, JournalEntry
    from app.tests.helpers import count_rows

    accounts_before = await count_rows(db, Account)
    goals_before = await count_rows(db, Goal)
    journals_before = await count_rows(db, JournalEntry)

    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )
    await client.post(
        "/ai/chat",
        json={"message": "Remember that I prefer Arabic explanations"},
        headers=auth_headers,
    )

    accounts_after = await count_rows(db, Account)
    goals_after = await count_rows(db, Goal)
    journals_after = await count_rows(db, JournalEntry)

    assert accounts_after == accounts_before
    assert goals_after == goals_before
    assert journals_after == journals_before


@pytest.mark.integration
@pytest.mark.anyio
async def test_extract_endpoint_returns_candidate(client, db, auth_headers):
    response = await client.post(
        "/ai/memory/extract",
        json={"text": "Remember that I prefer monthly summaries"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 1
    candidate = data["candidates"][0]
    assert candidate["memory_type"] == "preference"
    assert "monthly summaries" in candidate["value"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_forget_by_query_endpoint(client, db, auth_headers):
    await client.post(
        "/ai/memory",
        json={"memory_type": "preference", "key": "language", "value": "Arabic"},
        headers=auth_headers,
    )
    response = await client.post(
        "/ai/memory/forget",
        json={"query": "language"},
        headers=auth_headers,
    )
    assert response.status_code == 204

    list_response = await client.get("/ai/memory", headers=auth_headers)
    assert not any(m["key"] == "language" and m["is_active"] for m in list_response.json()["memories"])
