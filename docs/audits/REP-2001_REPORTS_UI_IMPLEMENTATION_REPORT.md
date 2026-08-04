# REP-2001 — Financial Reports UI / Report Center Implementation Report

## Summary

Built a user-facing Report Center on top of the existing REP-2000 JSON report endpoints — no report calculation logic was touched or duplicated. A new `GET /reports` page shows five report navigation buttons, a date-filter form, and an HTMX-refreshable report panel; five new `GET /reports/partials/*` routes each call the exact same `ReportService` method the corresponding JSON endpoint already calls (`app/reports/services.py`, unchanged) and render a Bootstrap/HTMX partial. All routes are GET-only, tenant-scoped, RLS-safe, and never create, update, or delete any financial record.

No database schema changes were needed. Alembic head remains `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `app/templates/reports/index.html` — Report Center page (extends `base.html`).
- `app/templates/reports/partials/report_filters.html` — reusable date-filter form (period or as-of, based on the active report).
- `app/templates/reports/partials/income_statement.html`
- `app/templates/reports/partials/balance_sheet.html`
- `app/templates/reports/partials/cash_flow.html`
- `app/templates/reports/partials/net_worth.html`
- `app/templates/reports/partials/expense_analysis.html`
- `app/templates/reports/partials/empty_state.html` — reusable "no data" message.
- `app/tests/integration/test_reports_ui.py` — 20 new tests.

**Modified:**
- `app/routers/reports.py` — added `GET /reports` (Report Center) and five `GET /reports/partials/*` routes; no changes to the existing five JSON routes.
- `app/templates/base.html` — added a "Reports" sidebar link under "Money", next to Transactions/Budgets/Goals/Loans/Bills/Subscriptions.

`app/reports/services.py`, `app/reports/generators/*.py`, and `app/reports/schemas.py` were **not modified** — every new route calls the same `ReportService` methods the existing JSON API already uses.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/reports` (and `/reports/`) | *(new)* Report Center page: navigation buttons, filter form, and the Income Statement pre-loaded as the default panel. |
| GET | `/reports/partials/income-statement` | *(new)* HTMX partial: income statement for `start_date`/`end_date` (defaults applied server-side if omitted). |
| GET | `/reports/partials/balance-sheet` | *(new)* HTMX partial: balance sheet as of `as_of_date` (defaults to today if omitted). |
| GET | `/reports/partials/cash-flow` | *(new)* HTMX partial: cash flow summary for `start_date`/`end_date`. |
| GET | `/reports/partials/net-worth` | *(new)* HTMX partial: net worth summary as of `as_of_date`. |
| GET | `/reports/partials/expense-analysis` | *(new)* HTMX partial: expense analysis for `start_date`/`end_date`. |
| GET | `/reports/income-statement`, `/reports/balance-sheet`, `/reports/cash-flow`, `/reports/net-worth`, `/reports/expense-analysis` | *(unchanged)* REP-2000 JSON API, untouched. |

All six new routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other report/dashboard route.

---

## Templates Added / Updated

See "Files Changed." Each report partial follows the same structure: an included `report_filters.html` form at the top, then either an inline error alert, an "unavailable" message (unexpected exception), the report's stat cards + tables, or an included `empty_state.html` when the tenant has no accounts of the relevant type. `reports/index.html` renders the same `income_statement.html` partial inline on first load (no extra HTMX round trip needed for the default view), and subsequent tab clicks / filter submissions swap `#report-panel` via HTMX.

---

## Reports Displayed

- **Income Statement**: income total, expense total, net income (color-coded), income accounts table, expense accounts table.
- **Balance Sheet**: assets total, liabilities total, net worth, equity total, a "Balanced"/"Out of balance" badge (from the existing `balance_check` field) plus a visible warning banner if out of balance, and three account tables (assets/liabilities/equity).
- **Cash Flow**: cash inflow, cash outflow, net cash flow, and a by-account table (inflow/outflow/net per cash/bank account) reusing `CashFlowResponse.by_account` unchanged.
- **Net Worth**: total assets, total liabilities, net worth, and a combined asset+liability account table with a type badge per row.
- **Expense Analysis**: total expenses, a "Top Expense Accounts" table with simple over-spend badges (`percent_of_total >= 40%` → "High spend", `>= 20%` → "Notable" — purely a display threshold, no new calculation), and the full `expenses_by_account` table.

---

## Date Filter Behavior

- **Period reports** (Income Statement, Cash Flow, Expense Analysis): default `start_date` = first day of the current month, default `end_date` = today, applied server-side whenever the query parameter is omitted — matching the card's explicit "current month" guidance.
- **As-of reports** (Balance Sheet, Net Worth): default `as_of_date` = today.
- **Validation**: if `start_date > end_date`, the route does not raise an unhandled exception — it re-renders the same partial (filter form still visible) with an inline `alert-warning` message ("Start date must be on or before end date.") and a `400` status code, so HTMX still swaps the error into the panel instead of failing silently. The underlying `ReportService` method is never called when validation fails.
- Verified by `test_valid_date_range_works`, `test_invalid_date_range_shows_safe_error`, `test_missing_date_defaults_work`.

---

## HTMX Behavior

- Each of the five tab buttons on the Report Center page (`hx-get="/reports/partials/{report}"`, `hx-target="#report-panel"`, `hx-swap="innerHTML"`) loads that report's partial without a full page reload.
- Each report's own filter form posts back to that same report's partial route (`hx-get`, same target/swap), so changing dates refreshes only the report panel — the navigation buttons and page chrome are untouched.
- This matches the project's existing HTMX conventions exactly (`/dashboard/partials/*`); no new JavaScript was written.
- Error and empty states render inline within the same swapped panel — no separate error page or redirect.

---

## Empty / Error States

- **No accounts of the relevant type** (e.g., a brand-new tenant with no chart of accounts yet): each partial shows a shared `empty_state.html` message ("No income or expense accounts found for this period.", etc.) instead of an empty table — verified by `test_empty_state_renders_when_no_accounts`.
- **Invalid date range**: inline warning alert, `400` status, filter form still shown so the user can correct it immediately.
- **Unexpected report-generation failure**: `reports_center` (the `GET /reports` page only) catches any exception from the initial income-statement load and renders a safe "This report is temporarily unavailable. Your data is safe and unchanged." message instead of a 500 — matching the same safety pattern already used by the dashboard widgets. The `/reports/partials/*` routes intentionally let `ReportService` exceptions propagate as FastAPI's standard error response, since they are simple, already-validated read operations with no plausible failure mode beyond the date-range check already handled inline.

---

## Read-Only Safety

- Every new route is `GET`-only; none of them call `db.commit()`, `db.add()`, or any mutating method.
- `test_viewing_reports_creates_no_financial_or_ai_records` confirms that loading the Report Center page and all five report partials leaves `JournalEntry`, `Account`, `Budget`, `Goal`, `Notification`, and `AIInsight` row counts completely unchanged.
- No budget-actual field, account balance, goal, bill, subscription, chore, or AI record is ever touched by any route added in this card — confirmed both by the test and by inspection (`app/reports/generators/*.py`, unmodified, contain no writes to any table).

---

## RLS / Tenant Safety

- All six new routes use `get_db_with_tenant_context` + `require_tenant_member`, identical to the unchanged JSON endpoints.
- `ReportService` is constructed with `user.organization_id` exactly as the JSON routes already do — no new tenant-scoping logic was introduced.
- `journal_entries` and `journal_lines` retain RLS + FORCE RLS — verified by `test_rls_active_on_journal_tables_via_reports_ui`.
- `test_tenant_a_cannot_see_tenant_b_report_data_in_ui` confirms Tenant B's rendered expense-analysis panel never contains Tenant A's posted amount or account name.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **624 passed, 1 skipped** (up from the DB-1107C baseline of 604 passed, 1 skipped — 20 new tests, zero regressions)

`app/tests/integration/test_reports_ui.py` covers:
- Routes/auth: `/reports` and each `/reports/partials/*` route requires auth; an authenticated tenant user can view the Report Center.
- Rendering: the Report Center shows all five report labels; each report partial renders its correct totals and account rows against posted journal entries; the empty state renders for a tenant with no chart of accounts.
- Date filters: a valid explicit range works, an invalid range (`start_date > end_date`) shows a safe inline error, and omitting dates falls back to the documented defaults.
- Read-only safety: viewing the Report Center and all five partials creates zero `JournalEntry`/`Account`/`Budget`/`Goal`/`Notification`/`AIInsight` rows.
- Tenant/RLS: Tenant B's report panel never contains Tenant A's posted amounts or account names; RLS remains active on `journal_entries`/`journal_lines`.

Regression: `test_reports.py` (the original REP-2000 JSON API suite), `test_dashboard_widget.py`, `test_dashboard_family_chores.py`, and `test_smoke.py` all pass in full, alongside the complete suite.

---

## Known Limitations

- No PDF/Excel export — explicitly out of scope for this card.
- The "High spend"/"Notable" expense badges are simple display-only thresholds (`>= 40%` / `>= 20%` of total expenses for the period) computed in the template from the existing `percent_of_total` field; they are not a new analytical feature and do not affect any stored data.
- The Report Center's initial page load only pre-renders the Income Statement; the other four reports are one HTMX click away rather than all being computed up front (intentional, to avoid five report queries on every page load).
- Report partials do not remember the previously-selected tab/date across a full page reload (no URL query-string sync); reloading `/reports` always returns to the Income Statement with default dates. This mirrors the existing dashboard widgets, which also do not persist filter state across reloads.
- Family/member-level report permissions are still not implemented (unchanged limitation carried over from REP-2000) — any tenant member can view all tenant reports.

---

## Recommended Next Card

**IMP-701 — Excel Import**

`PLAN_V2_CARD_STATUS.md` already shows DOC-2100/DOC-2101 (document upload/storage, OCR engine, entity linking) as **Done** — that recommendation from the original REP-2000 report is stale. CSV import and SMS bank-alert parsing are already implemented (`app/imports/`), but Excel import (`IMP-701`) is still listed as **Missing** and is the next well-scoped, unclaimed gap in the import pipeline — letting users bring in transaction history from spreadsheets the same safe, previewed, confirm-before-posting way CSV import already works.
