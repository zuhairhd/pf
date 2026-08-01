"""AI Chat Interface integration tests."""

from __future__ import annotations

import pytest

from app.models import AIChatMessage, AIChatSession
from app.tests.helpers import auth_headers_for, create_test_user


async def _other_user_headers(client, db, tenant):
    user, password = await create_test_user(db, tenant, role="viewer")
    await db.commit()
    return await auth_headers_for(client, user.email, password), user


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_requires_auth(client):
    response = await client.post("/ai/chat", json={"message": "hello"})
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_send_message_creates_session(client, db, auth_headers):
    response = await client.post(
        "/ai/chat",
        json={"message": "How do I start saving?"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["answer"]
    assert data["session_id"] is not None
    assert data["disclaimer"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_send_message_maintains_session(client, db, auth_headers):
    first = await client.post(
        "/ai/chat",
        json={"message": "I want to save for a car"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = await client.post(
        "/ai/chat",
        json={"message": "How much should I save monthly?", "session_id": session_id},
        headers=auth_headers,
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == session_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_sessions(client, db, auth_headers):
    await client.post("/ai/chat", json={"message": "hello"}, headers=auth_headers)
    response = await client.get("/ai/chat/sessions", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) >= 1
    assert data["sessions"][0]["title"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_session_history(client, db, auth_headers):
    chat = await client.post(
        "/ai/chat",
        json={"message": "What is a budget?"},
        headers=auth_headers,
    )
    session_id = chat.json()["session_id"]

    response = await client.get(f"/ai/chat/sessions/{session_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 2  # user + assistant
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"


@pytest.mark.integration
@pytest.mark.anyio
async def test_get_session_messages_alias(client, db, auth_headers):
    chat = await client.post(
        "/ai/chat",
        json={"message": "Tell me about debt"},
        headers=auth_headers,
    )
    session_id = chat.json()["session_id"]

    response = await client.get(
        f"/ai/chat/sessions/{session_id}/messages", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


@pytest.mark.integration
@pytest.mark.anyio
async def test_suggested_questions(client, db, auth_headers):
    chat = await client.post(
        "/ai/chat",
        json={"message": "I need help with my budget"},
        headers=auth_headers,
    )
    session_id = chat.json()["session_id"]

    response = await client.get(
        f"/ai/chat/sessions/{session_id}/suggested-questions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["questions"]) >= 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_delete_session(client, db, auth_headers):
    chat = await client.post(
        "/ai/chat",
        json={"message": "delete me"},
        headers=auth_headers,
    )
    session_id = chat.json()["session_id"]

    delete = await client.delete(
        f"/ai/chat/sessions/{session_id}", headers=auth_headers
    )
    assert delete.status_code == 204

    get = await client.get(f"/ai/chat/sessions/{session_id}", headers=auth_headers)
    assert get.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_cross_tenant_session_isolation(client, db, tenant_pair):
    tenant_a, tenant_b = tenant_pair
    headers_a, _ = await _other_user_headers(client, db, tenant_a)
    headers_b, _ = await _other_user_headers(client, db, tenant_b)

    chat_a = await client.post(
        "/ai/chat",
        json={"message": "tenant A message"},
        headers=headers_a,
    )
    session_id_a = chat_a.json()["session_id"]

    # Tenant B cannot access tenant A session.
    response_b = await client.get(
        f"/ai/chat/sessions/{session_id_a}", headers=headers_b
    )
    assert response_b.status_code == 404

    # Tenant B listing only shows tenant B sessions.
    list_b = await client.get("/ai/chat/sessions", headers=headers_b)
    assert session_id_a not in {s["id"] for s in list_b.json()["sessions"]}


@pytest.mark.integration
@pytest.mark.anyio
async def test_fallback_works_without_api_key(client, db, auth_headers):
    response = await client.post(
        "/ai/chat",
        json={"message": "What is investing?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]
    assert data["tokens_used"] == 0
    assert data["follow_up_questions"]
