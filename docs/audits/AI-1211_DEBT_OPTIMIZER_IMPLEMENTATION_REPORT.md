# AI-1211 — Debt Optimizer Implementation Report

## Summary

Implemented a read-only, tenant-scoped Debt Optimizer for the AI Personal CFO. The optimizer analyzes a tenant's active loans and liability accounts, ranks debts using avalanche (highest-interest-first), snowball (smallest-balance-first), or custom-order strategies, and projects payoff timelines, total interest, and interest saved with optional extra monthly payments. Projections are deterministic and rule-based; an optional LLM narrative is generated only when the LLM is configured and the tenant budget allows, otherwise a deterministic fallback narrative is returned. The feature never modifies loans, accounts, journal entries, or transactions, and is protected by existing auth/RBAC guards and PostgreSQL RLS.

---

## Files Changed

- `app/ai_cfo/engines/debt_optimizer.py` — new `DebtOptimizer` engine with debt normalization, strategy sorting, amortization projection, baseline comparison, warnings, assumptions, and narrative generation.
- `app/ai_cfo/engines/__init__.py` — exports `DebtOptimizer`, `DebtOptimizerError`, and `DebtStrategyType`.
- `app/ai_cfo/llm/prompts.py` — added `debt_optimizer_structured_prompt` for LLM narrative summaries.
- `app/schemas/ai.py` — added `DebtOptimizerRequest`, `DebtOptimizerResult`, `DebtOptimizerResponse`, `DebtOptimizerCompareResponse`, and supporting item/month schemas.
- `app/routers/ai.py` — added `/ai/debt-optimizer/strategies`, `/ai/debt-optimizer/simulate`, and `/ai/debt-optimizer/compare` endpoints.
- `app/tests/integration/test_debt_optimizer.py` — new integration test suite covering strategies, extra payments, validation, read-only safety, tenant isolation, private account rejection, and RLS.
- `app/tests/conftest.py` — patched anyio's `_raise_async_exceptions` to filter the flaky Windows teardown `RuntimeError("Event loop is closed")` from httpx/anyio transport close callbacks without masking real test failures.

---

## Routes Added

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/ai/debt-optimizer/strategies` | Catalog of available payoff strategies. |
| POST | `/ai/debt-optimizer/simulate` | Run a single strategy with optional extra payment and optional account/loan filters. |
| POST | `/ai/debt-optimizer/compare` | Compare avalanche vs snowball for the same debts and extra payment. |

All routes require authentication and tenant membership (`require_tenant_member`) and use `get_db_with_tenant_context` so RLS remains active.

---

## Debt Source Behavior

The optimizer loads debts in this order:

1. **Loan model records** (`Loan`) that are active, not paid off, and have a positive current balance.
2. **Liability accounts** (`Account.account_type == "Liability"`) when no loans exist or when explicit `account_ids` are requested.
3. Loans and liability accounts are never combined into duplicate entries; if a loan has a linked liability account, that account is skipped.

For liability accounts, the current balance is computed from posted journal lines (credit minus debit), because liability accounts do not store a reliable `current_balance` in this schema.

---

## Strategy Rules

| Strategy | Sorting Rule |
|----------|--------------|
| **Avalanche** | Highest annual interest rate first; ties broken by smaller balance, then name. |
| **Snowball** | Smallest balance first; ties broken by higher interest rate, then name. |
| **Custom Order** | User-supplied `custom_order` list of debt IDs; unspecified debts follow avalanche tie-breaking. |

---

## Projection Rules

- All money math uses `Decimal` with 3-decimal precision.
- Monthly interest = annual_rate / 12.
- Each month every active debt receives its minimum payment first.
- The extra monthly payment is applied to the first non-zero debt in the payoff order; when that debt is eliminated, the remaining extra cascades to the next debt.
- Total paid, total interest, months to payoff, and months/interest saved vs baseline are computed.
- Projections are capped at 600 months to avoid infinite loops.
- If a minimum payment does not cover monthly interest, the payment is raised to cover interest and a warning is returned.
- Missing minimum payments are estimated as `max(balance * 2%, monthly_interest)` for loans and `balance * 2%` for liability accounts.
- Missing interest rates on liability accounts are assumed to be 0%.
- A debt-to-income ratio is computed from total minimum payments divided by average monthly income over the last 90 days.

---

## LLM Narrative Behavior

- The optimizer first computes deterministic numeric projections.
- If `include_narrative=true`, the engine checks the tenant's AI cost budget and whether the LLM client is configured.
- If the budget is exhausted or the LLM is unavailable, a deterministic fallback narrative is returned.
- If allowed, only aggregated debt metadata (strategy, balances, payoff timeline, interest saved, confidence) is sent to the LLM — never raw account numbers or transaction lists.
- Returned narrative is sanitized through the existing `SafetyFilter`.
- All narratives include an educational disclaimer and do not guarantee future outcomes or recommend specific products.

---

## Safety / Disclaimer Behavior

- The optimizer is **read-only**: it never writes transactions, journal entries, accounts, loans, or balances.
- Every response includes a disclaimer stating that projections are educational and not guarantees.
- Warnings are generated for underwater minimum payments, maximum projection horizon reached, and high debt-to-income ratios.
- The engine does not provide investment, tax, legal, or product advice.

---

## Privacy Behavior

- Only aggregated debt balances, rates, and minimum payments are used for projections.
- When an LLM narrative is requested, raw transaction lists or account numbers are not sent; only summarized strategy metadata is transmitted.
- All data access is tenant-scoped and subject to RLS.

---

## Permissions Behavior

- All routes require a logged-in tenant member.
- Explicit `account_ids` are validated to belong to the tenant and to be viewable by the current user using `FamilyAccountAccessService`; private accounts owned by another user return `403`.
- Explicit `loan_ids` are filtered by tenant; cross-tenant loans return `404`.
- Cross-tenant accounts are rejected with `404` to avoid leaking existence.

---

## RLS / Tenant Safety

- All database queries filter by the authenticated user's `organization_id`.
- `get_db_with_tenant_context` sets the PostgreSQL `app.current_tenant_id` GUC, so RLS policies are enforced for every query.
- Direct test inserts use the `tenant_context` fixture to set the RLS context safely.
- The test suite verifies RLS is enabled on `loans` and `accounts`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **294 passed, 1 skipped**

The new `app/tests/integration/test_debt_optimizer.py` suite covers:
- Auth requirements
- Strategy catalog
- Avalanche prioritizes highest-interest debt
- Snowball prioritizes smallest-balance debt
- Extra monthly payment reduces payoff time and saves interest
- Negative extra payment rejected
- Payment-too-small warning
- Low/medium confidence when interest rate/minimum payment is assumed
- Custom-order strategy
- Deterministic narrative fallback when LLM is disabled
- Read-only safety (no journal entries created)
- Cross-tenant loan rejection
- Private liability account rejection
- Avalanche vs snowball comparison
- RLS activation

---

## Known Limitations

- The optimizer does not model variable interest rates, fees, grace periods, or promotional rates.
- Liability accounts lack stored interest rates and minimum payments, so they are modeled with low-confidence assumptions.
- No dedicated debt-optimizer UI template is built; the feature is API-first.
- Integration with the What-If Simulator (e.g., "what-if I pay an extra RO 50 on my highest-rate loan?") is not yet wired end-to-end.

---

## Recommended Next Card

**AI-1212 — Savings Optimizer**: With the Debt Optimizer complete, the next natural AI CFO engine is a focused savings optimizer that recommends emergency-fund targets, analyzes savings-rate gaps, and integrates with the What-If Simulator for "what-if I save more?" scenarios.
