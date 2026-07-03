"""Unit tests for the LLM safety filter."""

from __future__ import annotations

import pytest

from app.ai_cfo.llm.safety import SafetyFilter


@pytest.mark.unit
def test_safety_filter_allows_general_question():
    safety = SafetyFilter()
    result = safety.check_input("How can I save more money?")
    assert result["allowed"] is True
    assert result["warning"] is None


@pytest.mark.unit
def test_safety_filter_blocks_investment_recommendation_request():
    safety = SafetyFilter()
    result = safety.check_input("Which stock should I buy today?")
    assert result["allowed"] is False
    assert "investment" in result["warning"].lower() or "advice" in result["warning"].lower()


@pytest.mark.unit
def test_safety_filter_blocks_crypto_investment():
    safety = SafetyFilter()
    result = safety.check_input("Should I invest in crypto?")
    assert result["allowed"] is False


@pytest.mark.unit
def test_safety_filter_blocks_output_with_stock_ticker():
    safety = SafetyFilter()
    result = safety.check_output("You should buy AAPL right now.")
    assert result["allowed"] is False
    assert "investment" in result["modified_output"].lower()


@pytest.mark.unit
def test_safety_filter_adds_disclaimer():
    safety = SafetyFilter(disclaimer="Test disclaimer")
    output = safety.add_disclaimer("Hello")
    assert "Test disclaimer" in output


@pytest.mark.unit
def test_safety_filter_sanitize_returns_disclaimed_output():
    safety = SafetyFilter()
    result = safety.sanitize("Budget looks good.")
    assert "educational guidance only" in result
