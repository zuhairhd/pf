"""LLM integration tests.

These tests verify that cost control, tenant limits, and AI service fallback
work correctly. They do not require a real OpenAI API key.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from app.ai_cfo.llm.client import LLMClient
from app.ai_cfo.llm.cost_control import CostController
from app.config import get_settings
from app.models.analytics import AITokenUsage
from app.services.ai_chat import AIChatService
from app.services.ai_orchestrator import AIOrchestrator
from app.services.ai_forecast import AIForecastService


@pytest.mark.integration
@pytest.mark.anyio
async def test_cost_controller_records_usage(db, tenant, tenant_context):
    """Token usage is recorded to AITokenUsage."""
    await tenant_context(tenant.id)
    controller = CostController(db, tenant.id)
    usage = await controller.record_usage(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost_usd=0.0001,
        request_type="chat",
    )

    assert usage.id is not None
    assert usage.tenant_id == tenant.id
    assert usage.total_tokens == 15

    result = await db.execute(
        select(func.count(AITokenUsage.id)).where(AITokenUsage.tenant_id == tenant.id)
    )
    assert result.scalar() == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_cost_controller_enforces_daily_limit(db, tenant, tenant_context):
    """Daily limit is enforced based on tenant plan."""
    await tenant_context(tenant.id)
    controller = CostController(db, tenant.id)
    settings = get_settings()

    # Free-plan tenant default limit is AI_MAX_REQUESTS_PER_DAY_FREE.
    limit = await controller.get_daily_limit()
    assert limit == settings.AI_MAX_REQUESTS_PER_DAY_FREE

    # Record usage up to the limit.
    for _ in range(limit):
        await controller.record_usage(
            model="gpt-4o-mini",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            cost_usd=0.0,
            request_type="chat",
        )
    await db.commit()

    allowed, used, _ = await controller.check_limit()
    assert used == limit
    assert allowed is False


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_service_falls_back_without_api_key(client, auth_headers):
    """Chat returns rule-based response when no OpenAI key is configured."""
    with patch.object(LLMClient, "is_configured", return_value=False):
        response = await client.post(
            "/ai/chat",
            json={"message": "How do I budget better?", "session_id": None},
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "budget" in data["answer"].lower()
    assert "educational guidance only" in data["answer"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_chat_service_rejects_investment_advice(client, auth_headers):
    """Chat refuses to give specific investment advice."""
    with patch.object(LLMClient, "is_configured", return_value=False):
        response = await client.post(
            "/ai/chat",
            json={"message": "Which stock should I buy today?", "session_id": None},
            headers=auth_headers,
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "investment" in data["answer"].lower() or "advice" in data["answer"].lower()


@pytest.mark.integration
@pytest.mark.anyio
async def test_orchestrator_generates_insights_with_fallback(db, tenant, tenant_context):
    """AIOrchestrator generates insights without requiring an API key."""
    await tenant_context(tenant.id)
    orchestrator = AIOrchestrator(db, tenant.id)

    with patch.object(LLMClient, "is_configured", return_value=False):
        insights = await orchestrator.generate_insights()

    assert len(insights) >= 1
    assert all(i.tenant_id == tenant.id for i in insights)
    assert all(i.title for i in insights)


@pytest.mark.integration
@pytest.mark.anyio
async def test_forecast_service_falls_back_for_what_if(db, tenant, tenant_context):
    """What-if endpoint returns a response without an API key."""
    await tenant_context(tenant.id)
    service = AIForecastService(db, tenant.id)

    with patch.object(LLMClient, "is_configured", return_value=False):
        result = await service.simulate_scenario("What if I save 100 OMR per month?")

    assert result.scenario == "What if I save 100 OMR per month?"
    assert result.impact_summary
    assert "educational guidance only" in result.impact_summary.lower()
