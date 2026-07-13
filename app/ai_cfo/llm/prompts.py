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


def what_if_structured_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for a structured what-if scenario result.

    Only aggregated scenario metadata is sent — no raw transactions or
    personally identifiable details.
    """
    user_content = (
        "Explain the following what-if scenario in 3-5 concise sentences. "
        "Be supportive and educational. Do not make definitive predictions, "
        "do not give investment/tax/legal advice, and mention assumptions.\n\n"
        f"Scenario: {result.get('scenario_label')}\n"
        f"Currency: {result.get('currency')}\n"
        f"Projection months: {result.get('months')}\n"
        f"Baseline monthly net flow: {result.get('baseline_monthly_net_flow')}\n"
        f"Scenario monthly net flow: {result.get('scenario_monthly_net_flow')}\n"
        f"Total impact: {result.get('total_impact')}\n"
        f"Baseline ending balance: {result.get('ending_balance_baseline')}\n"
        f"Scenario ending balance: {result.get('ending_balance_scenario')}\n"
        f"Confidence: {result.get('confidence')}\n"
    )
    warnings = result.get("warnings") or []
    if warnings:
        user_content += "Warnings:\n" + "\n".join(f"- {w['message']}" for w in warnings) + "\n"
    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


def debt_optimizer_structured_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for a structured debt optimization result.

    Only aggregated debt metadata is sent — no raw account numbers or
    personally identifiable details.
    """
    user_content = (
        "Explain the following debt payoff strategy in 3-5 concise sentences. "
        "Be supportive and educational. Do not make definitive predictions, "
        "do not recommend specific financial products, and mention assumptions.\n\n"
        f"Strategy: {result.get('strategy')}\n"
        f"Currency: {result.get('currency')}\n"
        f"Total debt balance: {result.get('total_balance')}\n"
        f"Total minimum payment: {result.get('total_minimum_payment')}\n"
        f"Extra monthly payment: {result.get('extra_monthly_payment')}\n"
        f"Projected payoff months: {result.get('payoff_months')}\n"
        f"Baseline payoff months: {result.get('baseline_months')}\n"
        f"Months saved: {result.get('months_saved')}\n"
        f"Estimated total interest: {result.get('total_interest')}\n"
        f"Estimated interest saved: {result.get('interest_saved')}\n"
        f"Confidence: {result.get('confidence')}\n"
    )
    warnings = result.get("warnings") or []
    if warnings:
        user_content += "Warnings:\n" + "\n".join(f"- {w['message']}" for w in warnings) + "\n"
    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


def savings_optimizer_structured_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for a structured savings optimization result.

    Only aggregated savings metadata is sent — no raw transaction lists or
    personally identifiable details.
    """
    user_content = (
        "Explain the following savings guidance in 3-5 concise sentences. "
        "Be supportive and educational. Do not make definitive predictions, "
        "do not recommend specific investment products, and mention assumptions.\n\n"
        f"Mode: {result.get('mode')}\n"
        f"Currency: {result.get('currency')}\n"
    )
    if result.get("target_amount") is not None:
        user_content += f"Emergency fund target: {result.get('target_amount')}\n"
    if result.get("current_savings") is not None:
        user_content += f"Current savings: {result.get('current_savings')}\n"
    if result.get("gap_amount") is not None:
        user_content += f"Gap: {result.get('gap_amount')}\n"
    if result.get("avg_monthly_net_flow") is not None:
        user_content += f"Average monthly net flow: {result.get('avg_monthly_net_flow')}\n"
    if result.get("current_savings_rate_percent") is not None:
        user_content += f"Current savings rate: {result.get('current_savings_rate_percent')}%\n"
    if result.get("monthly_available_savings") is not None:
        user_content += f"Monthly available savings: {result.get('monthly_available_savings')}\n"
    if result.get("total_allocated") is not None:
        user_content += f"Total allocated to goals: {result.get('total_allocated')}\n"
    if result.get("required_spending_reduction") is not None:
        user_content += f"Required spending reduction: {result.get('required_spending_reduction')}\n"
    if result.get("recommended_strategy") is not None:
        user_content += f"Recommended strategy: {result.get('recommended_strategy')}\n"
    user_content += f"Confidence: {result.get('confidence')}\n"
    warnings = result.get("warnings") or []
    if warnings:
        user_content += "Warnings:\n" + "\n".join(f"- {w['message']}" for w in warnings) + "\n"
    return [
        _system_prompt(),
        {"role": "user", "content": user_content},
    ]


def goal_planner_structured_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """Build a prompt for a structured goal planning result.

    Only aggregated goal metadata is sent — no raw transaction lists or
    personally identifiable details.
    """
    user_content = (
        "Explain the following goal plan in 3-5 concise sentences. "
        "Be supportive and educational. Do not make definitive predictions, "
        "do not recommend specific investment products, and mention assumptions.\n\n"
        f"Mode: {result.get('mode')}\n"
        f"Currency: {result.get('currency')}\n"
    )
    if result.get("goal_name") is not None:
        user_content += f"Goal name: {result.get('goal_name')}\n"
    if result.get("target_amount") is not None:
        user_content += f"Target amount: {result.get('target_amount')}\n"
    if result.get("current_amount") is not None:
        user_content += f"Current amount: {result.get('current_amount')}\n"
    if result.get("remaining_amount") is not None:
        user_content += f"Remaining amount: {result.get('remaining_amount')}\n"
    if result.get("required_monthly_contribution") is not None:
        user_content += f"Required monthly contribution: {result.get('required_monthly_contribution')}\n"
    if result.get("months_to_completion") is not None:
        user_content += f"Months to completion: {result.get('months_to_completion')}\n"
    if result.get("on_track") is not None:
        user_content += f"On track: {result.get('on_track')}\n"
    if result.get("deadline_risk") is not None:
        user_content += f"Deadline risk: {result.get('deadline_risk')}\n"
    if result.get("feasibility") is not None:
        user_content += f"Feasibility: {result.get('feasibility')}\n"
    if result.get("goal_count") is not None:
        user_content += f"Number of goals: {result.get('goal_count')}\n"
    if result.get("strategy") is not None:
        user_content += f"Strategy: {result.get('strategy')}\n"
    if result.get("available_monthly_savings") is not None:
        user_content += f"Available monthly savings: {result.get('available_monthly_savings')}\n"
    if result.get("goals_at_risk") is not None:
        user_content += f"Goals at risk: {len(result.get('goals_at_risk', []))}\n"
    user_content += f"Confidence: {result.get('confidence')}\n"
    warnings = result.get("warnings") or []
    if warnings:
        user_content += "Warnings:\n" + "\n".join(f"- {w['message']}" for w in warnings) + "\n"
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
    "what_if_structured_prompt",
    "debt_optimizer_structured_prompt",
    "savings_optimizer_structured_prompt",
    "goal_planner_structured_prompt",
]
