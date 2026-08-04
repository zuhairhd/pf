> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 36: FAM-1305 — Allowance Payment Posting Through Accounting Engine**.

# Summary 29 — Card 36: FAM-1305 Allowance Payment Posting Through Accounting Engine

## What Was Done

Implemented allowance payment posting for approved chore completions through the existing `AccountingService`, closing the loop opened by FAM-1304 (allowance tracking) and DB-1107A (dashboard visibility). Posting an approved completion's `earned_amount` now creates a balanced double-entry journal entry (debit an Expense account, credit an Asset/payment account) instead of only leaving the amount as a numeric field. Posting and reversal are HEAD/PARENT-only, idempotent, tenant/account-validated, and never bypass the accounting engine — reversal reuses ACC-503A's existing `AccountingService.reverse_journal_entry()` and never deletes or mutates a posted entry.

## Key Changes

- Migration `bd89e4fcf4b9` adds seven nullable/defaulted payment-posting columns to the existing `family_chore_completions` table: `payment_status`, `payment_account_id`, `expense_account_id`, `payment_journal_entry_id`, `payment_reversal_journal_entry_id`, `paid_at`, `paid_by_user_id`. No table is dropped or recreated; RLS + FORCE RLS (already active from FAM-1304) is untouched.
- `app/services/family_chore_service.py`:
  - `can_user_post_payment()` / `require_post_payment()` — HEAD/PARENT only, separate from the assigned member's ability to submit a completion.
  - `post_payment()` — validates the completion is approved with `earned_amount > 0`, validates payment (Asset) and expense (Expense) accounts belong to the tenant and are usable via `FamilyAccountAccessService`, then posts through `AccountingService.create_journal_entry()`. Idempotent on `payment_journal_entry_id`, with a deterministic-reference (`ALLOW-{tenant_id}-{completion_id}`) safety net.
  - `reverse_payment()` — delegates to `AccountingService.reverse_journal_entry()`; idempotent on `payment_reversal_journal_entry_id`.
  - `count_approved_unpaid_completions()` — role-scoped count used only by the dashboard's "ready to pay" badge.
  - `get_allowance_summary()` extended with `approved_unpaid_amount`, `paid_amount`, `reversed_amount` (overall and per-member), without changing any existing field's meaning.
- `app/routers/family.py`: added `POST /chore-completions/{id}/post-payment` and `POST /chore-completions/{id}/reverse-payment`.
- `app/routers/dashboard.py` + templates: the Chores & Allowance widget now shows a "N ready to pay" badge (HEAD/PARENT only) linking to `/family/chores` — no account-selecting payment form was added, so the dashboard never silently chooses accounts.
- Added `app/tests/integration/test_family_allowance_payment.py` with 30 tests covering payment posting, account validation, permissions, idempotency, reversal, allowance summary changes, dashboard safety, and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (new head)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables; new columns present on `family_chore_completions`
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **554 passed, 1 skipped**

## Next Recommended Card

**DB-1107B — Allowance Payment Dashboard Action Form**
