"""Prompt templates for the AI CFO LLM.

Each prompt is returned as a list of messages ready for the OpenAI chat
completions API. Templates include a system prompt that establishes the
AI as an educational financial coach, not a licensed advisor.
"""

from __future__ import annotations

from typing import Any


DEFAULT_DISCLAIMER = (
    "This is educational guidance only and is not financial, investment, "
    "tax, or legal advice. Always consult a qualified professional before "
    "making financial decisions."
)


def _system_prompt() -> dict[str, str]:
    """Return the base system prompt for the AI Financial Coach."""
    return {
        "role": "system",
        "content": (
            "You are an AI Financial Coach for a personal-finance application. "
            "You help users understand their finances, build budgets, plan goals, "
            "manage debt, and make informed decisions. "
            "You are not a licensed financial advisor. "
            "Always be concise, supportive, and factual. "
            "Do not provide specific investment recommendations, tax advice, or legal advice. "
            "When uncertainty exists, acknowledge it and suggest consulting a professional. "
            "Respond in the same language the user used when possible."
        ),
    }


def chat_prompt(user_message: str, context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Build a chat completion prompt for the AI Financial Coach."""
    messages = [_system_prompt()]

    if context:
        context_parts = []
        if "health_score" in context:
            context_parts.append(f"Financial health score: {context['health_score']}/100")
        if "net_worth" in context:
            context_parts.append(f"Net worth: {context['net_worth']}")
        if "currency" in context:
            context_parts.append(f"Currency: {context['currency']}")
        if context_parts:
            messages.append({
                "role": "system",
                "content": "User context:\n" + "\n".join(context_parts),
            })

    messages.append({"role": "user", "content": user_message})
    return messages


def insight_prompt(financial_data: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for generating a prioritized list of AI insights."""
    accounts_summary = "\n".join(
        f"- {a.name} ({a.account_type}): {a.current_balance}"
        for a in financial_data.get("accounts", [])
    ) or "No accounts found."

    budgets_summary = "\n".join(
        f"- {b.name}: budgeted {b.total_budgeted}, actual {b.total_actual}"
        for b in financial_data.get("budgets", [])
    ) or "No active budgets."

    goals_summary = "\n".join(
        f"- {g.name}: {g.current_amount} / {g.target_amount}"
        for g in financial_data.get("goals", [])
    ) or "No active goals."

    loans_summary = "\n".join(
        f"- {l.name}: balance {l.current_balance}, rate {l.interest_rate}"
        for l in financial_data.get("loans", [])
    ) or "No active loans."

    user_content = (
        "Analyze the following financial snapshot and return 1 to 3 concise insights. "
        "For each insight provide: type (cash_flow, budget, debt, savings, goal, general), "
        "priority (critical, high, medium, low), title, message, and confidence (0-100). "
        "Focus on actionable observations and avoid generic platitudes.\n\n"
        f"Net worth: {financial_data.get('net_worth', 'unknown')}\n\n"
        f"Accounts:\n{accounts_summary}\n\n"
        f"Budgets:\n{budgets_summary}\n\n"
        f"Goals:\n{goals_summary}\n\n"
        f"Loans:\n{loans_summary}\n\n"
        "Return the result as a JSON list of objects with keys: "
        "type, priority, title, message, confidence."
    )

    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


def daily_brief_prompt(financial_data: dict[str, Any], health_score: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for generating the daily AI brief content."""
    user_content = (
        "Generate a short daily financial brief in Markdown. "
        "Include a one-sentence summary, the health score, 1-2 key insights, "
        "and 2-3 practical recommendations. Keep it under 250 words.\n\n"
        f"Health score: {health_score.get('overall_score', 'unknown')}/100\n"
        f"Net worth: {financial_data.get('net_worth', 'unknown')}\n"
        f"Total assets: {financial_data.get('total_assets', 'unknown')}\n"
        f"Total liabilities: {financial_data.get('total_liabilities', 'unknown')}\n"
    )

    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


def what_if_prompt(scenario: str, financial_data: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for running a what-if scenario."""
    user_content = (
        "Run a what-if scenario for the following user request. "
        "Return a concise impact summary, projected changes as a JSON list of "
        "{metric, current_value, projected_value, change_description}, "
        "and 2-3 recommendations. Do not make definitive predictions; explain assumptions.\n\n"
        f"Scenario: {scenario}\n\n"
        f"Net worth: {financial_data.get('net_worth', 'unknown')}\n"
        f"Total assets: {financial_data.get('total_assets', 'unknown')}\n"
        f"Total liabilities: {financial_data.get('total_liabilities', 'unknown')}\n"
    )

    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


__all__ = [
    "DEFAULT_DISCLAIMER",
    "chat_prompt",
    "insight_prompt",
    "daily_brief_prompt",
    "what_if_prompt",
]
