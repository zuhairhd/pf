"""Async OpenAI client wrapper for the AI CFO.

Provides a small, safe interface around the OpenAI API with retries,
timeouts, token/cost tracking, and graceful fallback when the API is
unavailable or misconfigured.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

from app.config import get_settings


class LLMError(Exception):
    """Raised when an LLM request fails and no fallback is available."""

    def __init__(self, message: str, *, retryable: bool = False):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


@dataclass
class LLMResponse:
    """Structured response from the LLM."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


def _get_client() -> Optional[AsyncOpenAI]:
    """Create an async OpenAI client if an API key is configured."""
    settings = get_settings()
    api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return AsyncOpenAI(api_key=api_key)


class LLMClient:
    """Async LLM client with retries, timeouts, and structured responses."""

    # Pricing per 1K tokens (USD) — update as OpenAI pricing changes.
    PRICING: dict[str, dict[str, float]] = {
        "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.00060},
        "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    }

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        max_retries: int = 2,
        timeout_seconds: float = 30.0,
    ):
        self.settings = get_settings()
        self.model = model or self.settings.OPENAI_MODEL or "gpt-4o-mini"
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self._client: Optional[AsyncOpenAI] = _get_client()

    def is_configured(self) -> bool:
        """Return True if an OpenAI API key is available."""
        return self._client is not None

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate API cost in USD from token counts."""
        rates = self.PRICING.get(self.model, self.PRICING["gpt-4o-mini"])
        prompt_cost = (prompt_tokens / 1000.0) * rates["prompt"]
        completion_cost = (completion_tokens / 1000.0) * rates["completion"]
        return round(prompt_cost + completion_cost, 6)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send a chat completion request to the configured LLM.

        Raises:
            LLMError: if the API is not configured or the request fails.
        """
        if not self._client:
            raise LLMError(
                "OpenAI API key is not configured",
                retryable=False,
            )

        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    timeout=self.timeout_seconds,
                )

                choice = response.choices[0]
                content = choice.message.content or ""
                usage = response.usage

                prompt_tokens = usage.prompt_tokens if usage else 0
                completion_tokens = usage.completion_tokens if usage else 0
                total_tokens = usage.total_tokens if usage else 0

                cost = self._estimate_cost(prompt_tokens, completion_tokens)

                return LLMResponse(
                    content=content.strip(),
                    model=self.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost,
                )

            except (APITimeoutError, RateLimitError, asyncio.TimeoutError, TimeoutError) as exc:
                last_exception = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise LLMError(
                    f"LLM request timed out or was rate-limited after {self.max_retries + 1} attempts",
                    retryable=True,
                ) from exc

            except APIError as exc:
                raise LLMError(
                    f"OpenAI API error: {exc.message}",
                    retryable=False,
                ) from exc

            except Exception as exc:
                raise LLMError(
                    f"Unexpected LLM error: {exc}",
                    retryable=False,
                ) from exc

        # Should never reach here, but satisfy the type checker.
        raise LLMError(
            "LLM request failed",
            retryable=True,
        ) from last_exception
