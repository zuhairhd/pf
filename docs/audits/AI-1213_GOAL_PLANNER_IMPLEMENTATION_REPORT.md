# AI-1213 — Goal Planner Implementation Report

## Summary

Implemented a read-only, tenant-scoped AI Goal Planner for the AI Personal CFO.
The planner analyzes visible financial goals alongside posted income and expense
trends to produce feasibility projections, prioritization recommendations, and
deadline rescue options. It reuses the existing LLM client with deterministic
fallback, cost control, and safety filtering. No financial records are modified.

## Files Changed

- `app/ai_cfo/engines/goal_planner.py` — new deterministic goal planning engine
- `app/ai_cfo/llm/prompts.py` — added `goal_planner_structured_prompt`
- `app/schemas/ai.py` — added Goal Planner request/response schemas
- `app/ai_cfo/engines/__init__.py` — exported `GoalPlanner`, `GoalPlanMode`, `GoalPriorityStrategy`, `GoalPlannerError`
- `app/routers/ai.py` — added `/ai/goal-planner/modes`, `/ai/goal-planner/plan`, `/ai/goal-planner/prioritize`
- `app/tests/integration/test_goal_planner.py` — 23 integration tests

## Routes Added

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ai/goal-planner/modes` | List planning modes and prioritization strategies |
| POST | `/ai/goal-planner/plan` | Run a single goal planning mode |
| POST | `/ai/goal-planner/prioritize` | Prioritize multiple goals using a selected strategy |

All routes require `require_tenant_member` and use `get_db_with_tenant_context` so
RLS policies remain active.

## Planning Modes

1. **single_goal_feasibility** — Analyze one existing goal's required monthly
   contribution, projected completion date, on-track status, and deadline risk.
2. **hypothetical_goal** — Plan a not-yet-created goal from target amount,
   optional current amount, optional target date, and optional monthly contribution.
3. **multi_goal_prioritization** — Allocate available monthly savings across
   multiple visible goals using a chosen strategy.
4. **deadline_rescue** — Calculate the shortfall for an at-risk goal and suggest
   options: increase contribution, extend deadline, reduce target, or reallocate
   from other goals.
5. **family_goal_plan** — Build a shared allocation plan across visible family
   goals using a family contribution amount.

## Projection Rules

- Required monthly contribution = remaining_amount / months_to_target_date.
- Months to completion = ceil(remaining_amount / monthly_contribution).
- Projected completion date = today + (months_to_completion × 30 days).
- On-track is True when projected completion is on or before the target date.
- Deadline risk is `high` when the goal cannot reach its target date at the
given contribution, `medium` when the required contribution exceeds the current
contribution, and `low` otherwise.
- Feasibility ratings: `achieved`, `high`, `medium`, `low`, `challenging`, or
`unknown`, based on required contribution vs. recent average net cash flow.

## Goal Prioritization Rules

Supported strategies:

- **equal_split** — Divide available savings evenly across goals.
- **priority_first** — Fully fund highest-priority goals before lower-priority ones.
- **closest_deadline** — Fund goals with the nearest target dates first.
- **lowest_gap_first** — Fund goals with the smallest remaining amount first.

Sequential strategies cap each allocation at the goal's remaining gap so no goal
is over-funded, and any unallocated remainder is reported.

## LLM Narrative Behavior

- Deterministic narrative is returned by default.
- If `include_narrative=True`, the engine checks the tenant's daily LLM quota and
whether the LLM client is configured.
- If quota is exceeded or no API key is configured, deterministic narrative is
returned (tests pass without an OpenAI API key).
- When LLM is used, only aggregated planning metadata is sent; raw transaction
lists and personally identifiable details are excluded.
- `SafetyFilter.sanitize()` adds the educational disclaimer and filters
investment-style recommendations.

## Safety / Disclaimer Behavior

- All responses include `DEFAULT_DISCLAIMER` at the router layer.
- The engine is read-only: it never creates or modifies goals, contributions,
accounts, journal entries, or transactions.
- No specific investment, tax, or legal advice is provided.
- No guaranteed outcomes are expressed.

## Privacy Behavior

- Goal visibility rules from `FamilyGoalService` are enforced for every goal
looked up by ID or loaded automatically.
- Private goals belonging to another user return `403`.
- Cross-tenant goals return `404` because RLS prevents the lookup.

## Permission Behavior

- Minimum requirement: authenticated tenant member (`require_tenant_member`).
- Family role checks (`head`, `parent`, `adult`, `teen`, `child`, `viewer`) are
applied through `FamilyGoalService.can_view_goal()`.

## RLS / Tenant Safety

- All database queries include the tenant filter.
- Routes use `get_db_with_tenant_context`, which sets `app.current_tenant_id`
for RLS policies.
- `FORCE RLS` was not modified or removed.
- Tests assert RLS is enabled on `goals` and `goal_contributions`.

## Test Results

- Goal Planner tests: 23 passed
- Full suite: **336 passed, 1 skipped**

Tests cover:
- Mode/strategy catalog (auth and content)
- Single-goal feasibility, required contribution, on-track detection, deadline risk
- Hypothetical goal planning and validation
- Multi-goal prioritization (equal_split, priority_first, closest_deadline, lowest_gap_first)
- Deadline rescue shortfall and options
- Read-only safety (no goal/contribution/journal changes)
- Deterministic narrative fallback without API key
- Disclaimer presence
- Cross-tenant and private-goal rejection
- RLS active on goal tables

## Known Limitations

- Goal achievement "probability" is expressed as feasibility rating and
  deadline-risk labels, not a formal statistical probability.
- Family goal plan uses equal-split allocation only; strategy selection for
  family plans can be added later.
- Investment returns, inflation, and irregular income are not modeled.
- No dedicated UI template/page exists yet.

## Recommended Next Card

**AI-1219 — Proactive Alerts** or **AI-1223 — Dashboard v2 AI-centric**

The Goal Planner completes the current batch of AI CFO engines. The next logical
steps are either proactive financial alerts based on goals/cash flow or an
AI-centric dashboard that surfaces goal-planning insights alongside the other
engines.
