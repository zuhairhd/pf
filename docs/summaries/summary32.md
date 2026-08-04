> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 39: REP-2001 — Financial Reports UI / Report Center**.

# Summary 32 — Card 39: REP-2001 Financial Reports UI / Report Center

## What Was Done

Built a user-facing Report Center on top of the existing REP-2000 JSON report endpoints (`/reports/income-statement`, `/reports/balance-sheet`, `/reports/cash-flow`, `/reports/net-worth`, `/reports/expense-analysis`) — no report calculation logic was touched or duplicated. A new `GET /reports` page shows five report navigation buttons, a date-filter form, and an HTMX-refreshable report panel; five new `GET /reports/partials/*` routes each call the exact same `ReportService` method the corresponding JSON endpoint already calls and render a Bootstrap/HTMX partial. Along the way, a stale "next card" recommendation for REP-2000 itself (already completed as an earlier Card 20) was found and corrected in `NEXT_RECOMMENDED_BUILD_ORDER.md`.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `bd89e4fcf4b9`).
- `app/routers/reports.py`: added `GET /reports` (Report Center page) and five `GET /reports/partials/*` routes. The existing five JSON routes and `app/reports/services.py`/`generators/*` were left completely unmodified.
- New templates: `reports/index.html`, `reports/partials/report_filters.html` (reusable period/as-of date form), one partial per report (`income_statement.html`, `balance_sheet.html`, `cash_flow.html`, `net_worth.html`, `expense_analysis.html`), and a shared `empty_state.html`.
- `app/templates/base.html`: added a "Reports" sidebar link.
- Date defaults: period reports (Income Statement, Cash Flow, Expense Analysis) default to the current month; as-of reports (Balance Sheet, Net Worth) default to today. An invalid range (`start_date > end_date`) renders a safe inline error (400) instead of propagating an exception, and never calls the underlying report service.
- HTMX: report tabs and each report's own filter form both target `#report-panel` with `hx-swap="innerHTML"`, matching the project's existing `/dashboard/partials/*` convention exactly — no new JavaScript.
- Added `app/tests/integration/test_reports_ui.py` with 20 tests: routes/auth, rendering (totals/rows against posted journal entries, empty state for a tenant with no chart of accounts), date-filter defaults and validation, read-only safety (zero `JournalEntry`/`Account`/`Budget`/`Goal`/`Notification`/`AIInsight` rows created by any view), and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **624 passed, 1 skipped**

## Next Recommended Card

**IMP-701 — Excel Import**
