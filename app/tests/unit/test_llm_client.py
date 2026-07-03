"""Unit tests for the LLM client wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_cfo.llm.client import LLMClient, LLMError, LLMResponse


@pytest.mark.unit
@pytest.mark.anyio
async def test_llm_client_not_configured_raises_error():
    with patch("app.ai_cfo.llm.client._get_client", return_value=None):
        client = LLMClient()
        with pytest.raises(LLMError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}])
        assert "not configured" in str(exc_info.value.message).lower()


@pytest.mark.unit
@pytest.mark.anyio
async def test_llm_client_returns_response_on_success():
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.total_tokens = 15

    mock_choice = MagicMock()
    mock_choice.message.content = "  Hello!  "

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.ai_cfo.llm.client._get_client", return_value=mock_client):
        client = LLMClient(model="gpt-4o-mini")
        result = await client.complete([{"role": "user", "content": "hi"}])

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello!"
    assert result.model == "gpt-4o-mini"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
    assert result.cost_usd > 0


@pytest.mark.unit
@pytest.mark.anyio
async def test_llm_client_retries_on_timeout():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=TimeoutError)

    with patch("app.ai_cfo.llm.client._get_client", return_value=mock_client):
        client = LLMClient(max_retries=1, timeout_seconds=0.1)
        with pytest.raises(LLMError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}])
        assert exc_info.value.retryable is True
