> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 38: DB-1107C — Allowance Payment Reversal Dashboard Action**.

# Summary 31 — Card 38: DB-1107C Allowance Payment Reversal Dashboard Action

## What Was Done

Added a "Reverse Payment" action to the Chores & Allowance dashboard widget's Recent Payments list, completing the FAM-1305 → DB-1107B → DB-1107C dashboard payment lifecycle: HEAD/PARENT can now both post and reverse an allowance payment without leaving the dashboard. The action reuses `FamilyChoreService.reverse_payment()` (FAM-1305) completely unchanged, which itself delegates entirely to `AccountingService.reverse_journal_entry()` (ACC-503A) — no new reversal logic was written anywhere. Following the card's guidance to prefer the project's existing HTMX style and not overbuild, the implementation uses the simplest safe pattern already established by the Approve/Submit-Completion quick actions from DB-1107A: a single confirmed button (`hx-confirm`) that refreshes the whole widget — no separate confirmation route or result template was needed.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `bd89e4fcf4b9`).
- `app/schemas/family_chore.py`: `DashboardPaymentHistoryItem` gained `can_reverse: bool = False`.
- `app/routers/dashboard.py`:
  - `_build_family_chores_dashboard()` now computes `can_reverse` per recent-payment item — true only when the viewer is HEAD/PARENT, the item's `payment_status` is `paid`, a `payment_journal_entry_id` exists, and no `payment_reversal_journal_entry_id` exists yet.
  - `POST /partials/family-chore-completions/{id}/reverse-payment` — calls `FamilyChoreService.reverse_payment()` unchanged; refreshes the whole widget on both success and handled error (matching the exact `action_error`/status-400 pattern already used by the Submit-Completion and Approve-Completion routes).
- `app/templates/dashboard/partials/family_chore_ready_to_pay.html`: the Recent Payments row gained a "Reverse" button for eligible Paid items, using `hx-post` + `hx-confirm` + whole-widget `outerHTML` swap.
- Added `app/tests/integration/test_dashboard_allowance_payment_reversal.py` with 21 tests: route/auth and permission gating, Reverse-button visibility rules, balanced reversal journal entry creation, original entry immutability, idempotency, unpaid/never-paid rejection, read-only browsing safety, and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **604 passed, 1 skipped**

## Next Recommended Card

**REP-2000 — Basic Financial Reports**
