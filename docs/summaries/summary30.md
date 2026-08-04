> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 37: DB-1107B — Allowance Payment Dashboard Action Form**.

# Summary 30 — Card 37: DB-1107B Allowance Payment Dashboard Action Form

## What Was Done

Added an inline, HTMX-driven payment form to the Chores & Allowance dashboard widget so HEAD/PARENT users can post an approved allowance payment without leaving the dashboard, closing out the FAM-1305 → DB-1107B loop the same way FAM-1304 → DB-1107A did for chore tracking. The form requires an explicit payment (Asset) account and expense account selection — the dashboard never guesses or auto-fills accounts. Submitting the form posts through the unchanged `FamilyChoreService.post_payment()` (FAM-1305), which only ever goes through `AccountingService`. The widget's old badge-only "ready to pay" link became a full actionable "Ready to Pay" list, plus a small "Recent Payments" history showing Paid/Reversed status and a safe journal-entry reference.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `bd89e4fcf4b9`).
- `app/services/family_chore_service.py`: added `list_approved_unpaid_completions_for_user()` (full-item version of the existing count) and `list_recent_paid_completions_for_user(limit=5)`; refactored `count_approved_unpaid_completions()` to delegate to the new list method instead of duplicating the query.
- `app/schemas/family_chore.py`: added `DashboardAccountOption`, `DashboardReadyToPayItem`, `DashboardPaymentHistoryItem`; `FamilyChoresDashboardResponse` gained `ready_to_pay` and `recent_payments` lists.
- `app/routers/dashboard.py`:
  - `_build_family_chores_dashboard()` now also returns the ready-to-pay list and recent-payment history.
  - `GET /dashboard/partials/family-chore-completions/{id}/payment-form` — renders the inline account-picker form for one approved-unpaid completion; read-only; HEAD/PARENT only (403 inline-error partial otherwise).
  - `POST /dashboard/partials/family-chore-completions/{id}/post-payment` — submits the chosen accounts and posts through `FamilyChoreService.post_payment()` unchanged; on success sets `HX-Retarget`/`HX-Reswap` response headers so HTMX swaps the whole widget in place; on error, only the inline form re-renders with a message and no journal entry is created.
  - Account picker reuses `FamilyAccountAccessService.list_visible_accounts()` unchanged, filtered by `account_type` — no new visibility logic.
- New templates: `family_chore_payment_form.html` (account selects, date, notes, submit/cancel), `family_chore_ready_to_pay.html` (ready-to-pay list with per-item "Post Payment" buttons + inline form containers, plus the Recent Payments block).
- `family_chores_widget.html` updated: the "Ready to Pay" section (HEAD/PARENT only, gated on `permissions.can_post_payment`) replaces the old plain badge/link.
- Added `app/tests/integration/test_dashboard_allowance_payment_form.py` with 29 tests: form rendering and permission gating, account-picker type filtering and tenant isolation, posting (balanced entry, idempotency, already-paid safety, rejected invalid/unapproved/cross-tenant cases), dashboard state changes after payment, read-only safety while browsing, and RLS/tenant isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **583 passed, 1 skipped**

## Next Recommended Card

**DB-1107C — Allowance Payment Reversal Dashboard Action**
