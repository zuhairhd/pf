# AI-1212 — Savings Optimizer Implementation Report

## Summary

Implemented a read-only, tenant-scoped Savings Optimizer for the AI Personal CFO. The optimizer analyzes a tenant's recent cash flow, emergency-fund adequacy, and active visible goals, then recommends savings capacity, emergency-fund targets, goal allocations, and spending reductions. Projections are deterministic and rule-based; an optional LLM narrative is generated only when the LLM is configured and the tenant budget allows, otherwise a deterministic fallback narrative is returned. The feature never writes transfers, journal entries, accounts, goals, or budgets, and is protected by existing auth/RBAC guards and PostgreSQL RLS.

---

## Files Changed

- `app/ai_cfo/engines/savings_optimizer.py` — new `SavingsOptimizer` engine with cash-flow snapshot, emergency-fund analysis, savings-capacity calculation, goal allocation, spending-reduction guidance, strategy comparison, and narrative generation.
- `app/ai_cfo/engines/__init__.py` — exports `SavingsOptimizer`, `SavingsOptimizerError`, `SavingsModeType`, and `AllocationStrategy`.
- `app/ai_cfo/llm/prompts.py` — added `savings_optimizer_structured_prompt` for LLM narrative summaries.
- `app/schemas/ai.py` — added `SavingsOptimizerRequest`, emergency-fund, savings-capacity, goal-allocation, reduce-spending, and compare-strategies result schemas, plus `SavingsOptimizerResponse` and `SavingsOptimizerCompareResponse`.
- `app/routers/ai.py` — added `/ai/savings-optimizer/strategies`, `/ai/savings-optimizer/simulate`, and `/ai/savings-optimizer/compare` endpoints.
- `app/tests/integration/test_savings_optimizer.py` — new integration test suite covering all modes, validation, permissions, read-only safety, tenant isolation, and RLS.

---

## Routes Added

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/ai/savings-optimizer/strategies` | Catalog of supported savings optimization modes. |
| POST | `/ai/savings-optimizer/simulate` | Run a single savings optimization mode. |
| POST | `/ai/savings-optimizer/compare` | Compare goal allocation strategies side-by-side. |

All routes require authentication and tenant membership (`require_tenant_member`) and use `get_db_with_tenant_context` so RLS remains active.

---

## Savings Optimization Modes

1. **emergency_fund** — Calculate target emergency fund, current savings, gap, months to target, and risk level.
2. **savings_capacity** — Estimate monthly savings capacity from recent income/expense averages and optional target savings rate.
3. **goal_allocation** — Allocate monthly available savings across visible active goals using a chosen strategy.
4. **reduce_spending** — Calculate how much spending must be cut to hit a target monthly savings amount.
5. **compare_strategies** — Compare goal allocation strategies (equal_split, priority_first, closest_deadline, lowest_gap_first) and recommend one.

---

## Projection Rules

- All money math uses `Decimal` with 3-decimal precision.
- Income and expense averages are computed from posted journal entries over the last 90 days.
- Total assets are the signed normal balances of all Asset accounts.
- Monthly projections start from a relevant baseline (account balance, total goal progress, or total assets) and add the monthly contribution/savings each month.
- Confidence is lowered when no recent income or expense history is found.

---

## Emergency Fund Rules

- `target_amount = average_monthly_expenses * target_months_of_expenses`.
- `current_savings` is read from the optional `account_id` if provided; otherwise it is 0.
- `gap_amount = max(target_amount - current_savings, 0)`.
- `months_to_target = ceil(gap_amount / monthly_contribution)` when both are positive.
- Risk level:
  - `low` — current savings meet or exceed the target.
  - `medium` — current savings cover at least one month of expenses but are below target.
  - `high` — current savings cover less than one month of expenses.
  - `unknown` — no recent expense history.

---

## Savings Capacity Rules

- `avg_monthly_net_flow = avg_monthly_income - avg_monthly_expenses`.
- `current_savings_rate_percent = (net_flow / income) * 100` when income > 0.
- Suggested monthly savings range = 20% to 50% of positive disposable income.
- If `target_savings_rate` is provided, `target_monthly_savings = income * (target_savings_rate / 100)` and `savings_gap = max(target_monthly_savings - disposable_income, 0)`.

---

## Goal Allocation Rules

- Only active, visible goals are considered.
- Strategies:
  - **equal_split** — divide `monthly_available_savings` equally across all goals.
  - **priority_first** — fill the highest-priority goal first, then cascade to the next.
  - **closest_deadline** — fill the goal with the nearest target_date first.
  - **lowest_gap_first** — fill the goal with the smallest remaining amount first.
- For sequential strategies, allocation is capped at each goal's remaining gap.
- Output includes per-goal recommended allocation, new monthly contribution, projected progress percent, and estimated months to completion.

---

## LLM Narrative Behavior

- The optimizer first computes deterministic numeric projections.
- If `include_narrative=true`, the engine checks the tenant's AI cost budget and whether the LLM client is configured.
- If the budget is exhausted or the LLM is unavailable, a deterministic fallback narrative is returned.
- If allowed, only aggregated savings metadata (mode, balances, rates, gaps, allocations, confidence) is sent to the LLM — never raw transaction lists or account numbers.
- Returned narrative is sanitized through the existing `SafetyFilter`.
- All narratives include an educational disclaimer and do not guarantee future outcomes or recommend specific products.

---

## Safety / Disclaimer Behavior

- The optimizer is **read-only**: it never writes transfers, transactions, journal entries, accounts, goals, or budgets.
- Every response includes a disclaimer stating that projections are educational and not guarantees.
- Warnings are generated for negative cash flow, insufficient emergency savings, and savings gaps.
- The engine does not provide investment, tax, legal, or product advice.

---

## Privacy Behavior

- Only aggregated balances, averages, and goal metadata are used for projections.
- When an LLM narrative is requested, raw transaction lists or account numbers are not sent; only summarized savings metadata is transmitted.
- All data access is tenant-scoped and subject to RLS.

---

## Permissions Behavior

- All routes require a logged-in tenant member.
- `account_id` inputs are validated through `FamilyAccountAccessService` for tenant membership and view rights; private accounts owned by another user return `403`.
- `goal_ids` inputs are validated through `FamilyGoalService`; private goals not visible to the current user return `403`.
- Cross-tenant accounts and goals are rejected with `404` to avoid leaking existence.

---

## RLS / Tenant Safety

- All database queries filter by the authenticated user's `organization_id`.
- `get_db_with_tenant_context` sets the PostgreSQL `app.current_tenant_id` GUC, so RLS policies are enforced for every query.
- Direct test inserts use the `tenant_context` fixture to set the RLS context safely.
- The test suite verifies RLS is enabled on `goals` and `accounts`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q --tb=short` — **313 passed, 1 skipped**

The new `app/tests/integration/test_savings_optimizer.py` suite covers:
- Auth requirements
- Strategy/mode catalog
- Emergency fund target, gap, months-to-target, and risk level
- Low-savings warning
- Savings capacity rate, suggestions, target rate gap, and negative cash-flow warning
- Goal allocation: equal_split, priority_first, closest_deadline
- Unauthorized private goal rejection
- Cross-tenant goal rejection
- Cross-tenant account rejection
- Private account rejection
- Reduce spending required reduction and expense candidates
- Compare strategies recommendation
- Read-only safety (no journal entries created)
- Deterministic LLM fallback without API key
- Disclaimer presence
- RLS activation

---

## Known Limitations

- The optimizer uses 90-day historical averages and does not model income volatility, seasonal variation, taxes, or investment returns.
- Emergency fund analysis does not distinguish essential vs. discretionary expenses unless expense-account naming is used by the caller.
- Goal allocation does not yet post actual contributions or create accounting entries.
- No dedicated savings-optimizer UI template is built; the feature is API-first.

---

## Recommended Next Card

**AI-1213 — Goal Planner**: With the Savings Optimizer in place, the next natural AI CFO engine is a focused goal planner that recommends goal priorities, feasibility, and contribution adjustments based on income, expenses, and timelines.
