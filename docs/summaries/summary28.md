> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 35: DB-1107A — Allowance and Chore Dashboard Widget UI**.

# Summary 28 — Card 35: DB-1107A Allowance and Chore Dashboard Widget UI

## What Was Done

Added a Chores & Allowance widget to the AI-centric dashboard, following the same "service now, widget next" pattern as FAM-1303 → DB-1106A. The widget shows assigned chores due soon, overdue chores, pending completions awaiting approval, an allowance summary (pending / approved this month / approved all-time / rejected, with a per-member breakdown where the viewer is allowed to see it), and permission-gated submit-completion / approve-completion HTMX quick actions. Every existing dashboard section — AI Today, commitments, family goals, family budgets, optimizer shortcuts — is preserved unchanged. The widget is strictly read-only with respect to accounts, transactions, journal entries, and goals; only explicit chore actions create or update `FamilyChoreCompletion` rows.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `356391296d35`).
- `app/services/family_chore_service.py`: added two small, role-scoped, read-only helper methods reused by the dashboard (no chore/allowance math duplicated in the router):
  - `list_pending_completions_for_user()` — submitted completions visible to the caller (HEAD/PARENT see all; everyone else sees only their own).
  - `get_approved_allowance_this_month()` — sum of `earned_amount` for completions approved in the current calendar month, scoped the same way as `get_allowance_summary()`.
- `app/schemas/family_chore.py`: added dashboard-facing schemas — `DashboardChoreItem`, `DashboardCompletionItem`, `DashboardAllowanceMemberBreakdown`, `DashboardAllowanceSummary`, `FamilyChoresDashboardResponse`.
- `app/routers/dashboard.py`:
  - `_build_family_chores_dashboard(db, user)` — composes chores/completions/allowance data from `FamilyChoreService`; due-soon/overdue bucketing is view-only categorization of chores the service already scoped by role (mirrors how the budgets/goals dashboard builders categorize inline).
  - `GET /dashboard/api/family-chores` — UI-ready JSON.
  - `GET /dashboard/partials/family-chores` — HTMX widget partial.
  - `POST /dashboard/partials/family-chores/{chore_id}/complete` — submit-completion quick action (assigned member only).
  - `POST /dashboard/partials/family-chore-completions/{completion_id}/approve` — approve quick action (HEAD/PARENT only).
  - Main `dashboard()` route now also builds/passes `family_chores` (wrapped in try/except, matching the existing budgets/goals pattern).
- New templates: `family_chores_widget.html`, `family_chores_list.html`, `family_chore_card.html`, `family_chore_pending_approvals.html`, `family_allowance_summary.html`; `dashboard/index.html` updated to include the new widget after the family-budgets block.
- Reject is intentionally **not** offered as a dashboard quick action — it requires a reason, so the widget links to `/family/chores` instead (the same "View" link precedent already used by the family-budgets widget for a page that also doesn't exist yet as dedicated HTML).
- Added `app/tests/integration/test_dashboard_family_chores.py` with 25 tests: dashboard API sections/data, HTMX partial rendering and empty states, HEAD/PARENT/TEEN/CHILD/VIEWER permission filtering, submit/approve quick actions, repeated-refresh idempotency, read-only financial safety, unauthorized submit/approve rejection, and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `356391296d35` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **524 passed, 1 skipped**

## Next Recommended Card

**FAM-1305 — Allowance Payment Posting Through Accounting Engine**
