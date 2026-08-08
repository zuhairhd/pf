> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 45: ACC-502 — Opening Balances**.

# Summary 38 — Card 45: ACC-502 Opening Balances

## What Was Done

Implemented opening balances: a user configures `Account.opening_balance` (nullable, distinct from a configured zero), and `POST /accounts/opening-balances/post` converts every eligible account's configured amount into a real, balanced journal entry through the unchanged `AccountingService.create_journal_entry()` engine, against an auto-resolved/auto-created "Opening Balance" Equity account.

**A stale premise was corrected mid-implementation:** the brief claimed `Account.current_balance` already existed as a field to reuse. Direct model introspection confirmed it does not (`Loan.current_balance` does; `Account` never had it) — several other modules (`dashboard.py`, `ai_forecast.py`, `ai_orchestrator.py`, `health_score_service.py`) reference it as if it existed, a pre-existing latent bug left untouched (out of this card's scope; documented as a known limitation). This card adds a genuinely new, distinctly-named `opening_balance` field instead.

## Key Changes

- `Account` gained three nullable columns: `opening_balance`, `opening_balance_date`, `opening_balance_journal_entry_id` (Alembic `b7d2e5a91c48`, additive only).
- `app/services/accounting_service.py`: added `post_opening_balances()`/`get_opening_balance_status()`, both built entirely on the unchanged `create_journal_entry()`. Normal-balance-side debit/credit logic (Asset/Expense debit-normal, Liability/Equity/Income credit-normal) correctly flips for a negative opening amount, always balanced.
- The "Opening Balance" Equity offset account (code `3000`) is looked up first, matching the naming the dev seed's `CHART_OF_ACCOUNTS` already established, and only created if genuinely absent — reused across all accounts in a posting run, and always excluded from receiving its own posting.
- `app/routers/accounts.py`: added `POST /accounts/opening-balances/post` and `GET /accounts/opening-balances/status`, both gated to HEAD/PARENT via the same elevated-role check FAM-1305/GOAL-1401B already use (`FamilyAccountAccessService.get_role()`). `PATCH /accounts/{id}` now rejects changing an already-posted opening balance.
- Idempotent: `opening_balance_journal_entry_id` is checked before any posting; a repeat call reports `already_posted` and creates nothing new.
- Added `app/tests/integration/test_opening_balances.py` with 17 tests: posting, balance verification, skip rules, idempotency, status detection, normal-balance-side correctness, permissions, tenant isolation, RLS, and read-only-adjacent safety (budgets/bills/goals/goal-contributions/invitations untouched).

## Verification

- `python -m compileall app` — OK
- `alembic current` — `b7d2e5a91c48` (head, up from `f3a8c1d94b7e`)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 47 tables unchanged, new columns present on `accounts`
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **743 passed, 1 skipped** (up from 726 passed, 1 skipped)

## Next Recommended Card

**ACC-500 — Chart of Accounts (Hidden Foundation)**
