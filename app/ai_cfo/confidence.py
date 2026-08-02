"""Confidence scoring utility for the AI Personal CFO.

Attaches a transparent, explainable confidence score/label to AI-generated
or AI-assisted outputs. Confidence reflects data completeness, data
recency, whether a calculation is deterministic or LLM-assisted, whether
assumptions were required, and whether an LLM fallback was used.

This module is purely additive: it never reads or writes financial
records, and callers decide which factors apply to a given result.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class ConfidenceLabel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Score range and label thresholds.
MIN_SCORE = 0.0
MAX_SCORE = 1.0
HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.45

# Starting point before any factors are applied. Chosen so that a result
# with no factors at all lands in the "medium" band rather than implying
# unwarranted certainty.
BASE_SCORE = 0.60


@dataclass(frozen=True)
class ConfidenceFactor:
    """A single named contributor to a confidence score."""

    name: str
    impact: float
    explanation: str


# ---------------------------------------------------------------------------
# Reusable factor library
# ---------------------------------------------------------------------------

POSITIVE_FACTORS: dict[str, ConfidenceFactor] = {
    "deterministic_calculation": ConfidenceFactor(
        "deterministic_calculation", 0.12,
        "Result is produced by a deterministic calculation, not an LLM estimate.",
    ),
    "sufficient_history": ConfidenceFactor(
        "sufficient_history", 0.10,
        "Enough historical data was available to compute a reliable average.",
    ),
    "recent_data": ConfidenceFactor(
        "recent_data", 0.05,
        "The underlying data is recent.",
    ),
    "complete_required_inputs": ConfidenceFactor(
        "complete_required_inputs", 0.10,
        "All required inputs were provided or found; nothing had to be assumed.",
    ),
    "direct_accounting_data": ConfidenceFactor(
        "direct_accounting_data", 0.10,
        "Figures come directly from posted accounting records or source tables.",
    ),
    "user_confirmed_memory": ConfidenceFactor(
        "user_confirmed_memory", 0.05,
        "Personalization is based on memory the user explicitly confirmed.",
    ),
    "no_llm_dependency": ConfidenceFactor(
        "no_llm_dependency", 0.05,
        "The numeric result does not depend on an LLM call.",
    ),
}

NEGATIVE_FACTORS: dict[str, ConfidenceFactor] = {
    "missing_interest_rate": ConfidenceFactor(
        "missing_interest_rate", -0.20,
        "An interest rate was missing and had to be assumed.",
    ),
    "missing_minimum_payment": ConfidenceFactor(
        "missing_minimum_payment", -0.15,
        "A minimum payment was missing and had to be assumed.",
    ),
    "low_transaction_history": ConfidenceFactor(
        "low_transaction_history", -0.25,
        "Little or no transaction history is available for this calculation.",
    ),
    "stale_data": ConfidenceFactor(
        "stale_data", -0.10,
        "The underlying data may be stale.",
    ),
    "many_assumptions": ConfidenceFactor(
        "many_assumptions", -0.10,
        "Multiple assumptions were required to produce this result.",
    ),
    "forecast_long_horizon": ConfidenceFactor(
        "forecast_long_horizon", -0.08,
        "Long forecast horizons are inherently less certain.",
    ),
    "llm_fallback": ConfidenceFactor(
        "llm_fallback", -0.12,
        "The LLM was unavailable, over quota, or failed; a deterministic fallback was used.",
    ),
    "llm_unavailable": ConfidenceFactor(
        "llm_unavailable", -0.05,
        "No LLM narrative was generated for this response.",
    ),
    "user_input_only": ConfidenceFactor(
        "user_input_only", -0.10,
        "The result relies only on user-provided input that has not been independently verified.",
    ),
    "private_data_filtered": ConfidenceFactor(
        "private_data_filtered", -0.05,
        "Some private or sensitive context was filtered out before use.",
    ),
    "incomplete_goal_data": ConfidenceFactor(
        "incomplete_goal_data", -0.15,
        "The goal is missing a target date or other key planning data.",
    ),
}

ALL_FACTORS: dict[str, ConfidenceFactor] = {**POSITIVE_FACTORS, **NEGATIVE_FACTORS}


def label_from_score(score: float) -> ConfidenceLabel:
    """Map a 0.0-1.0 score to a high/medium/low label."""
    if score >= HIGH_THRESHOLD:
        return ConfidenceLabel.HIGH
    if score >= MEDIUM_THRESHOLD:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW


def explain_confidence(
    factors: list[ConfidenceFactor], score: float, label: ConfidenceLabel
) -> str:
    """Build a short human-readable explanation of a confidence score."""
    parts = [f"{label.value.capitalize()} confidence ({score:.2f})."]
    positives = [f for f in factors if f.impact > 0]
    negatives = [f for f in factors if f.impact < 0]
    if positives:
        parts.append("Supporting factors: " + "; ".join(f.explanation for f in positives))
    if negatives:
        parts.append("Limiting factors: " + "; ".join(f.explanation for f in negatives))
    return " ".join(parts)


@dataclass
class ConfidenceScore:
    """A computed confidence score with its label, factors, and explanation."""

    score: float
    label: ConfidenceLabel
    factors: list[ConfidenceFactor] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        """Serialize to the field names used by API response schemas."""
        return {
            "confidence_score": round(self.score, 4),
            "confidence_label": self.label.value,
            "confidence_factors": [
                {"name": f.name, "impact": f.impact, "explanation": f.explanation}
                for f in self.factors
            ],
            "confidence_explanation": self.explanation,
        }


def calculate_confidence_score(
    factor_names: list[str],
    *,
    base_score: float = BASE_SCORE,
) -> ConfidenceScore:
    """Compute a confidence score from a list of named factors.

    Unknown factor names are ignored rather than raising, so callers can
    pass optional/conditional factor names without extra branching.
    """
    factors: list[ConfidenceFactor] = []
    score = base_score
    for name in factor_names:
        factor = ALL_FACTORS.get(name)
        if factor is None:
            continue
        factors.append(factor)
        score += factor.impact

    score = max(MIN_SCORE, min(MAX_SCORE, score))
    label = label_from_score(score)
    explanation = explain_confidence(factors, score, label)
    return ConfidenceScore(score=score, label=label, factors=factors, explanation=explanation)


def confidence_from_factors(
    factor_names: list[str],
    *,
    base_score: float = BASE_SCORE,
) -> ConfidenceScore:
    """Alias of calculate_confidence_score for readability at call sites."""
    return calculate_confidence_score(factor_names, base_score=base_score)


class ConfidenceScorer:
    """Convenience builder for accumulating factors before scoring.

    Example:
        score = (
            ConfidenceScorer()
            .add("deterministic_calculation")
            .add_if(missing_rate, "missing_interest_rate")
            .build()
        )
    """

    def __init__(self, base_score: float = BASE_SCORE):
        self.base_score = base_score
        self._factor_names: list[str] = []

    def add(self, name: str) -> "ConfidenceScorer":
        self._factor_names.append(name)
        return self

    def add_if(self, condition: bool, name: str) -> "ConfidenceScorer":
        if condition:
            self._factor_names.append(name)
        return self

    def build(self) -> ConfidenceScore:
        return calculate_confidence_score(self._factor_names, base_score=self.base_score)


def confidence_rules() -> dict:
    """Return the scoring rules for API/documentation exposure."""
    return {
        "score_range": {"min": MIN_SCORE, "max": MAX_SCORE},
        "thresholds": {
            "high": HIGH_THRESHOLD,
            "medium": MEDIUM_THRESHOLD,
            "low": MIN_SCORE,
        },
        "base_score": BASE_SCORE,
        "labels": [label.value for label in ConfidenceLabel],
        "positive_factors": [
            {"name": f.name, "impact": f.impact, "explanation": f.explanation}
            for f in POSITIVE_FACTORS.values()
        ],
        "negative_factors": [
            {"name": f.name, "impact": f.impact, "explanation": f.explanation}
            for f in NEGATIVE_FACTORS.values()
        ],
    }


__all__ = [
    "ConfidenceLabel",
    "ConfidenceFactor",
    "ConfidenceScore",
    "ConfidenceScorer",
    "POSITIVE_FACTORS",
    "NEGATIVE_FACTORS",
    "ALL_FACTORS",
    "BASE_SCORE",
    "HIGH_THRESHOLD",
    "MEDIUM_THRESHOLD",
    "calculate_confidence_score",
    "confidence_from_factors",
    "label_from_score",
    "explain_confidence",
    "confidence_rules",
]
