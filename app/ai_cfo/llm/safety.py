"""Safety filtering and disclaimer injection for LLM outputs.

Guards against off-topic, harmful, or overly specific financial advice.
Adds required disclaimers and strips potentially risky content.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai_cfo.llm.prompts import DEFAULT_DISCLAIMER


# Topics that should trigger a refusal or strong disclaimer.
SENSITIVE_TOPICS = [
    "invest in",
    "buy stock",
    "sell stock",
    "buy shares",
    "sell shares",
    "which stock",
    "what stock",
    "stock to buy",
    "crypto investment",
    "forex trading",
    "tax evasion",
    "hide money",
    "loan fraud",
    "guaranteed return",
]

# Phrases that indicate a request for specific investment advice.
INVESTMENT_REQUEST_PATTERNS = [
    r"which\s+\w+\s+should\s+i\s+buy",
    r"what\s+\w+\s+should\s+i\s+invest",
]

# Patterns that look like specific investment recommendations.
INVESTMENT_RECOMMENDATION_PATTERNS = [
    r"\b(buy|sell|hold)\s+[A-Z]{1,5}\b",
    r"\binvest\s+in\s+[A-Z][A-Za-z\s]+\b",
    r"\b(crypto|cryptocurrency|stock|share)\s+(to\s+buy|to\s+invest|recommendation)\b",
]


class SafetyFilter:
    """Filter LLM inputs and outputs for safety and compliance."""

    def __init__(self, disclaimer: str = DEFAULT_DISCLAIMER):
        self.disclaimer = disclaimer

    def check_input(self, user_input: str) -> dict[str, Any]:
        """Check user input for sensitive or disallowed topics.

        Returns a dict with `allowed` and `warning` keys.
        """
        lower_input = user_input.lower()

        for topic in SENSITIVE_TOPICS:
            if topic in lower_input:
                return {
                    "allowed": False,
                    "warning": (
                        "I can't provide specific investment, tax, or legal advice. "
                        "Please consult a qualified professional."
                    ),
                }

        for pattern in INVESTMENT_REQUEST_PATTERNS:
            if re.search(pattern, lower_input):
                return {
                    "allowed": False,
                    "warning": (
                        "I can't provide specific investment recommendations. "
                        "Please consult a qualified financial advisor."
                    ),
                }

        return {"allowed": True, "warning": None}

    def check_output(self, output: str) -> dict[str, Any]:
        """Check LLM output for unsupported recommendations.

        Returns a dict with `allowed`, `modified_output`, and `warning` keys.
        """
        for pattern in INVESTMENT_RECOMMENDATION_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return {
                    "allowed": False,
                    "modified_output": (
                        "I'm not able to provide specific investment recommendations. "
                        "I can help you understand budgeting, saving, debt management, "
                        "and goal planning instead."
                    ),
                    "warning": "Output contained possible investment recommendation.",
                }

        return {"allowed": True, "modified_output": output, "warning": None}

    def add_disclaimer(self, output: str) -> str:
        """Append the educational disclaimer to the output if not already present."""
        if self.disclaimer in output:
            return output
        return f"{output}\n\n*{self.disclaimer}*"

    def sanitize(self, output: str) -> str:
        """Apply output checks and add disclaimer."""
        check = self.check_output(output)
        text = check["modified_output"] if not check["allowed"] else output
        return self.add_disclaimer(text)
