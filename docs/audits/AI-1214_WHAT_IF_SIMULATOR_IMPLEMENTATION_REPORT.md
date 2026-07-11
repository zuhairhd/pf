# AI-1214 — What-If Simulator Implementation Report

## Summary

Implemented a read-only, tenant-scoped What-If Simulator for the AI Personal CFO. The simulator lets authenticated tenant members model financial scenarios (savings increases, expense reductions, income changes, emergency expenses, subscription cancellation, goal contribution increases, and new monthly payments) without modifying any real financial records. Projections are deterministic and rule-based; an optional LLM narrative is generated only when the LLM is configured and the tenant budget allows it, otherwise a deterministic fallback narrative is returned. The feature is protected by existing auth/RBAC guards and PostgreSQL RLS.

---

## Files Changed

- `app/ai_cfo/engines/__init__.py` — package marker for the engines sub-module.
- `app/ai_cfo/engines/whatif_simulator.py` — new `WhatIfSimulator` engine with scenario handlers, projection builder, and narrative generation.
- `app/ai_cfo/llm/prompts.py` — added `what_if_structured_prompt` for LLM narrative summaries.
- `app/schemas/ai.py` — added structured What-If request/response schemas (`WhatIfScenarioRequest` union, `WhatIfResult`, `WhatIfSimulationResponse`, `WhatIfCompareRequest`, `WhatIfCompareResponse`, etc.).
- `app/routers/ai.py` — added `/ai/what-if/scenarios`, `/ai/what-if/simulate`, and `/ai/what-if/compare` endpoints.
- `app/middleware/error_handling.py` — made the `RequestValidationError` handler Decimal-safe via `jsonable_encoder`.
- `app/tests/integration/test_whatif.py` — new integration test suite covering all scenario types, permissions, tenant isolation, read-only safety, and RLS.

---

## Routes Added

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/ai/what-if/scenarios` | Catalog of supported scenario types and required fields. |
| POST | `/ai/what-if/simulate` | Run a single what-if scenario and return projections. |
| POST | `/ai/what-if/compare` | Run multiple scenarios side-by-side with a best/worst summary. |

All routes require authentication and tenant membership (`require_tenant_member`) and use `get_db_with_tenant_context` so RLS remains active.

---

## Scenario Types Supported

1. **increase_monthly_savings** — model extra monthly savings and optional linked goal.
2. **reduce_expense_category** — model reducing a recurring expense by fixed amount or percent.
3. **income_increase** — model a raise or new income stream (fixed or percent).
4. **emergency_expense** — model a one-time unexpected expense in a given month.
5. **cancel_subscription** — model cancelling a recurring subscription.
6. **goal_contribution_increase** — model increasing monthly contributions to a goal.
7. **new_monthly_payment** — model a new recurring payment with optional down payment.

---

## Projection Rules

- **Baseline snapshot** is built from the current tenant's asset balances and the average monthly income/expense over the last 90 days of posted journal entries.
- **Income** is measured from credit activity on Income accounts; **expenses** from debit activity on Expense accounts.
- **Total assets** are the signed normal balances of all Asset accounts.
- **Monthly projections** start from the current total assets and add the baseline net flow each month, plus the scenario's monthly delta and any one-time deltas (e.g., emergency expense, down payment).
- **Total impact** is the net difference between the scenario and baseline ending balances over the horizon.
- **Confidence** is lowered when no recent income or expense history is found.

---

## LLM Narrative Behavior

- The simulator first computes deterministic numeric projections.
- If `include_narrative=true`, the engine checks the tenant's AI cost budget and whether the LLM client is configured.
- If the budget is exhausted or the LLM is unavailable, a deterministic fallback narrative is returned.
- If allowed, only an aggregated scenario summary (not raw transaction lists) is sent to the LLM.
- Returned narrative is sanitized through the existing `SafetyFilter`.
- All narratives include an educational disclaimer and do not guarantee future outcomes.

---

## Safety / Disclaimer Behavior

- The simulator is **read-only**: it never writes transactions, journal entries, accounts, goals, bills, or subscriptions.
- Every response includes a disclaimer stating that projections are educational and not guarantees.
- Warnings are generated for negative projected balances, insufficient emergency reserves, and missing historical data.
- The engine does not provide investment, tax, or legal advice.

---

## Privacy Behavior

- Only aggregated balances and averages are used for projections.
- When an LLM narrative is requested, raw transaction lists or account numbers are not sent; only summarized scenario metadata is transmitted.
- All data access is tenant-scoped and subject to RLS.

---

## Permissions Behavior

- All routes require a logged-in tenant member.
- Scenario inputs that reference accounts (`target_account_id`, `source_account_id`, `expense_account_id`) are validated through `FamilyAccountAccessService` for tenant membership and visibility/usage rights.
- Scenario inputs that reference goals (`goal_id`) are validated through `FamilyGoalService.can_view_goal`, so private goals are only visible to their owner or elevated family roles.
- Cross-tenant accounts, subscriptions, and goals are rejected with `404` to avoid leaking existence.

---

## RLS / Tenant Safety

- All database queries filter by the authenticated user's `organization_id`.
- `get_db_with_tenant_context` sets the PostgreSQL `app.current_tenant_id` GUC, so RLS policies are enforced for every query.
- Direct test inserts use the `tenant_context` fixture to set the RLS context safely.
- The test suite verifies RLS is enabled on `accounts`, `goals`, and `subscriptions`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -v --tb=no` — **279 passed, 1 skipped**

The new `app/tests/integration/test_whatif.py` suite covers:
- Auth requirements
- Scenario catalog
- All seven scenario types
- Comparison endpoint
- Invalid months and negative amounts
- Read-only safety (no journal entries created)
- LLM fallback without API key
- Disclaimer presence
- Cross-tenant account/subscription/goal rejection
- Unauthorized private-goal rejection
- RLS activation

---

## Known Limitations

- The simulator uses simple historical averages and does not model taxes, investment returns, inflation, or seasonal income variation.
- Goal contribution simulations treat the extra contribution as a cash-flow reallocation; they do not post accounting entries.
- Family-level permissions rely on the existing `FamilyService` role model; fine-grained report-style permissions for children/viewers are not added in this card.
- No dedicated simulator UI template is built; the feature is API-first.

---

## Recommended Next Card

**AI-1211 — Debt Optimizer**: With the What-If Simulator in place, the next natural AI CFO engine is a focused debt-optimization service that recommends payoff strategies (avalanche/snowball) and integrates with the simulator for "what-if I pay extra?" scenarios.
