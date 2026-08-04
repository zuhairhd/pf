# IMP-703 — Import UI Implementation Report

## Summary

Built a browser-facing Import Center on top of the existing `app/imports/` pipeline (CSV — IMP-700, SMS — IMP-702, Excel — IMP-701). No parser, validation, duplicate-detection, or confirm/posting logic was rebuilt: every new route is a thin wrapper that calls the exact same `ImportService` methods the JSON API already uses (`create_job`, `create_excel_job`, `create_sms_job`, `get_job`, `get_job_rows`, `confirm_job`, `cancel_job`), plus one new read-only `ImportService.list_jobs()` method added to support import history. Confirm still posts through the unchanged `AccountingService.create_journal_entry` and the unchanged `FamilyAccountAccessService` account-visibility checks.

Users can now open `GET /imports`, pick CSV / Excel / SMS, upload or paste their data, see a live preview of valid/invalid/duplicate rows, choose accounts, and confirm or cancel — entirely through server-rendered Bootstrap/HTMX partials matching the project's existing conventions (`app/templates/reports/`, `app/templates/dashboard/`).

No database schema changes were needed. Alembic head remains `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `app/templates/imports/index.html` — Import Center page (extends `base.html`).
- `app/templates/imports/preview_page.html` — full-page, bookmarkable import preview.
- `app/templates/imports/partials/csv_form.html`
- `app/templates/imports/partials/excel_form.html`
- `app/templates/imports/partials/sms_form.html`
- `app/templates/imports/partials/preview.html` — shared job summary + rows table + confirm/cancel controls.
- `app/tests/integration/test_import_ui.py` — 29 new tests.
- `docs/audits/IMP-703_IMPORT_UI_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/imports/routes.py` — added the "Import Center UI (IMP-703)" section (11 new routes); the existing five JSON/API routes are unchanged.
- `app/imports/services.py` — added `ImportService.list_jobs()` (read-only, tenant-scoped, newest-first); no other service method was changed.
- `app/templates/base.html` — added an "Imports" sidebar link under "Money", next to Reports.

`app/imports/parsers/csv_parser.py`, `app/imports/parsers/excel_parser.py`, `app/imports/parsers/sms_parser.py`, and the confirm/posting logic inside `ImportService` were **not modified** in behavior.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/imports` (and `/imports/`) | *(new)* Import Center: method cards, upload workspace, import history. |
| GET | `/imports/partials/csv-form` | *(new)* CSV upload form partial (read-only). |
| GET | `/imports/partials/excel-form` | *(new)* Excel upload form partial (read-only). |
| GET | `/imports/partials/sms-form` | *(new)* SMS paste form partial (read-only). |
| POST | `/imports/ui/csv` | *(new)* Browser-friendly CSV upload; calls `ImportService.create_job()` unchanged. |
| POST | `/imports/ui/excel` | *(new)* Browser-friendly Excel upload; calls `ImportService.create_excel_job()` unchanged. |
| POST | `/imports/ui/sms` | *(new)* Browser-friendly SMS paste; calls `ImportService.create_sms_job()` unchanged. |
| GET | `/imports/ui/{job_id}/preview` | *(new)* Full-page, bookmarkable preview (lazily loads the partial below via HTMX). |
| GET | `/imports/partials/{job_id}/preview` | *(new)* HTMX partial: job summary, rows, confirm/cancel controls. |
| POST | `/imports/ui/{job_id}/confirm` | *(new)* Browser-friendly confirm; calls `ImportService.confirm_job()` unchanged. |
| POST | `/imports/ui/{job_id}/cancel` | *(new)* Browser-friendly cancel; calls `ImportService.cancel_job()` unchanged. |
| POST | `/imports/csv/upload`, `/imports/excel/upload`, `/imports/sms/parse`, GET/POST `/imports/{job_id}*` | *(unchanged)* Existing JSON API, untouched. |

All 11 new routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other import/report route. Route-shape analysis confirmed no ambiguity with the existing JSON routes (verified via `app.openapi()` — see Test Results).

---

## Templates Added / Updated

- `imports/index.html` — three method-card buttons (`hx-get` to the matching form partial, swapped into `#import-workspace`), the CSV form pre-loaded by default, and an import-history table (empty state when there are no jobs yet).
- `imports/partials/{csv,excel,sms}_form.html` — each form posts via `hx-post`/`hx-encoding="multipart/form-data"` (CSV/Excel) or a plain `hx-post` (SMS) to its `/imports/ui/*` route, targeting `#import-workspace`. Inline `form_error` alerts on failure re-render the same form.
- `imports/partials/preview.html` — the shared preview/confirm/cancel panel, rooted at a stable `#import-preview-panel` element. Confirm and cancel forms inside it both target `#import-preview-panel` with `hx-swap="outerHTML"`, so the same partial is reused for the initial post-upload view, the dedicated preview page, and every subsequent confirm/cancel refresh.
- `imports/preview_page.html` — extends `base.html`; lazily loads `partials/preview.html` via `hx-trigger="load"` so the full page and every HTMX entry point share one source of truth.

---

## Import Center Behavior

`GET /imports` shows three method cards (CSV / Excel / SMS), an upload workspace pre-loaded with the CSV form, and an import-history table listing the tenant's most recent jobs (type, filename, status, total/valid/invalid/duplicate/imported counts, created date, and a "View" link to that job's preview). A brand-new tenant sees a friendly empty state ("No import jobs yet...") instead of an empty table.

---

## CSV UI Behavior

The CSV form uploads a file via multipart (`file`, optional `mapping` JSON text). The new `POST /imports/ui/csv` route reads the file's bytes, decodes them as UTF-8 (with BOM handling via `utf-8-sig`), and calls the exact same `ImportService.create_job()` the JSON `POST /imports/csv/upload` route already uses — the `CSVParser` is never touched. An empty file or undecodable content returns a safe inline `form_error` (400) instead of a crash; invalid mapping JSON is caught the same way.

---

## Excel UI Behavior

The Excel form uploads a `.xlsx` file plus optional `sheet_name`, `mapping` JSON, `default_account_id` (a select populated from the user's visible accounts), and `default_currency`. `POST /imports/ui/excel` performs the same `.xlsx`-only extension check and size check the JSON route already performs, then calls the exact same `ImportService.create_excel_job()` — the `ExcelParser` is never touched. Unsupported extensions (e.g. `.xls`) and corrupted workbooks both return a safe inline `form_error` (400), never a 500.

---

## SMS UI Behavior

The SMS form is a single textarea for pasted bank alert text (plus an optional label). `POST /imports/ui/sms` calls the exact same `ImportService.create_sms_job()` the JSON `POST /imports/sms/parse` route already uses. Since the SMS parser never raises a hard error for unrecognized text (it marks the row `invalid` with validation errors instead), an unparseable paste still returns `200` with the row shown as "Invalid" in the preview, matching the existing SMS parser's documented behavior.

---

## Preview / Confirm / Cancel Behavior

The preview panel shows the job's total/valid/invalid/duplicate/imported counts as stat cards, a status badge (Preview / Completed / Cancelled), and a rows table (row number, status badge, date, description, amount, and any validation errors) for up to 200 rows. While the job is in `preview` status and has at least one valid row, a Confirm form is shown (bank account required, default income/expense accounts optional, an "also import duplicates" checkbox) that posts to `POST /imports/ui/{job_id}/confirm`, which calls the exact same `ImportService.confirm_job()` the JSON API uses — posting through the unchanged `AccountingService`. A separate Cancel button posts to `POST /imports/ui/{job_id}/cancel`, calling `ImportService.cancel_job()` unchanged. Both routes re-render the same preview panel afterward (via `hx-swap="outerHTML"` on `#import-preview-panel`) showing the updated status and, on confirm, the exact imported/skipped counts. Errors from either action (e.g. "Import job is already completed", "No valid rows available to import") are shown as an inline alert without losing the current view.

---

## Account Picker Behavior

Every account `<select>` in the Excel form and the preview's confirm form is built from `FamilyAccountAccessService(db, tenant_id, user).list_visible_accounts()` — the exact same call already used by the dashboard's allowance payment form (`app/routers/dashboard.py::_dashboard_account_options`). This means:
- Private accounts owned by someone else never appear.
- Accounts belonging to another tenant never appear (queries are always tenant-scoped).
- If a request is crafted to submit an inaccessible account ID anyway, the existing `confirm_job` → `_create_journal_entry_for_row` → `can_use_account_for_posting` check (unchanged, from FAM-1301) still rejects it and skips the row — the UI layer adds no new trust boundary.

---

## HTMX Behavior

- Method-card buttons on the Import Center swap the matching upload form into `#import-workspace`.
- Each upload form posts via HTMX (multipart for CSV/Excel) and the response — the rendered preview partial — replaces `#import-workspace`'s contents directly, avoiding an extra round trip.
- The preview panel is a self-contained, re-postable unit (`#import-preview-panel`): both the dedicated preview page (which lazily loads it via `hx-trigger="load"`) and the post-upload inline view use the identical partial, and confirm/cancel always swap that same element `outerHTML`.
- No new JavaScript was written; all behavior uses the project's existing HTMX conventions.

---

## Error / Empty States

| Scenario | Behavior |
|---|---|
| No import jobs yet | Import Center shows a friendly empty-state message instead of an empty table. |
| No file selected | Blocked client-side by the HTML5 `required` attribute on the file input. |
| Unsupported file type (Excel `.xls`) | Safe inline `form_error`, 400, form re-rendered. |
| Invalid mapping JSON | Safe inline `form_error`, 400, form re-rendered. |
| Unknown Excel worksheet name | `ExcelParseError` → `ImportServiceError` → safe inline `form_error`, 400. |
| Corrupted Excel workbook | Same safe `form_error` path, never a 500. |
| Invalid/unparseable SMS text | Not an error — the job is created with the row marked `invalid` and its validation errors shown in the preview, matching the existing SMS parser behavior. |
| All rows invalid | Preview shows every row as `Invalid` with its reasons; the Confirm form is hidden (0 valid rows) and a "No valid rows are available to import" notice is shown instead. |
| Duplicate-only upload | Duplicate rows are shown with a `Duplicate` badge and are excluded from the default confirm (matching existing dedupe behavior). |
| Confirm with no valid rows | `ImportServiceError("No valid rows available to import")` is caught and shown as an inline `confirm_error`, 400, without losing the preview. |
| Unauthorized access | Every route requires `require_tenant_member`; anonymous requests get `401`/`403` before any handler code runs. |
| Cross-tenant job ID | `get_job()` is tenant-scoped, so a job ID from another tenant resolves to `None` and the route raises `404` — verified for the preview page, the preview partial, confirm, and cancel. |

---

## Read-Only Safety

- Every GET route (`/imports`, the three form partials, the preview page, the preview partial) performs no writes — verified by `test_opening_import_center_creates_no_financial_records` and `test_previewing_import_creates_no_journal_entries`, which assert `JournalEntry`/`Account`/`Budget`/`Goal` row counts are unchanged across those views.
- Uploading a file (`POST /imports/ui/*`) creates `ImportJob`/`ImportedRow` rows — that is the explicit, expected purpose of "preview" — but never a `JournalEntry`, `Account`, `Budget`, `Goal`, `Bill`, or `Subscription` row.
- `test_only_confirm_creates_journal_entries` confirms that the journal-entry count is unchanged immediately after upload and increases by exactly the number of valid rows only after an explicit confirm.

---

## RLS / Tenant Safety

- All 11 new routes use `get_db_with_tenant_context` + `require_tenant_member`, identical to every existing import/report route.
- `test_tenant_a_cannot_see_tenant_b_import_jobs` confirms Tenant B receives `404` for both the preview page and the preview partial of Tenant A's job.
- `test_tenant_a_cannot_confirm_or_cancel_tenant_b_jobs` confirms Tenant B receives `404` attempting to confirm or cancel Tenant A's job (the underlying `confirm_job`/`cancel_job` calls `get_job()`, which is tenant-scoped and returns `None` for a foreign job, matching the existing JSON API's isolation guarantee).
- `test_rls_active_on_import_and_journal_tables` re-verifies RLS + FORCE RLS on `import_jobs`, `imported_rows`, `journal_entries`, and `journal_lines`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **674 passed, 1 skipped** (up from the IMP-701 baseline of 645 passed, 1 skipped — 29 new tests, zero regressions)

`app/tests/integration/test_import_ui.py` (29 tests) covers:
- Import Center: auth required, method cards shown, empty state, history shows jobs.
- CSV UI: form renders, upload creates preview job, empty-file upload shows a safe error.
- Excel UI: form renders, upload creates preview job, `sheet_name` selects the right worksheet, unsupported `.xls` rejected, corrupted workbook rejected safely.
- SMS UI: form renders, valid paste creates a preview job, unparseable paste shows an invalid-row preview.
- Preview/confirm/cancel: preview page/partial require auth, preview shows valid/invalid/duplicate badges, confirm posts valid rows into journal entries, cancel cancels the job with zero journal entries, duplicate rows are excluded from a default confirm.
- Account visibility: the Excel form hides an inaccessible private account and a cross-tenant account; a non-elevated user's confirm attempt against a private account they don't own imports zero rows.
- Read-only safety: opening the Import Center, and previewing a job, create no financial records; only confirm does, and by exactly the valid row count.
- Tenant/RLS: cross-tenant preview/confirm/cancel all return `404`; RLS + FORCE RLS re-verified on `import_jobs`, `imported_rows`, `journal_entries`, `journal_lines`.

Regression: the full existing `test_imports.py` (CSV/SMS/Excel API, 49 tests), `test_reports_ui.py`, dashboard tests, and the complete project test suite all pass alongside the new tests.

---

## Known Limitations

- No visual column-mapping builder — the `mapping` field is a raw JSON textarea, matching the existing JSON API's `mapping` parameter shape exactly (not a new limitation introduced here).
- No client-side JavaScript beyond HTMX; all interactivity is server-rendered partials, consistent with the rest of the project.
- Very large files are still parsed synchronously within the request (unchanged limitation carried over from IMP-700/701); no background/async import job UI was added.
- The rows table caps at 200 rows per preview load (matching a sane default `limit`); there is no pagination UI for jobs with more rows than that.

---

## Recommended Next Card

**GOAL-1401B — Goal Contribution Reversal**

`PLAN_V2_CARD_STATUS.md` lists `GOAL-1400 to GOAL-1402` as **Done** for GOAL-1401A (goal-contribution accounting posting) but **Partial** for "remaining goal planning/reversal." The reversal pattern is already proven twice in this codebase — `ACC-503A` (`AccountingService.reverse_journal_entry`, used by bill/subscription reversal) and `DB-1107C` (Allowance Payment Reversal Dashboard Action) — so goal-contribution reversal is a small, well-scoped, low-risk next step: reuse the same reversal engine and the same dashboard-action-button UI pattern, applied to goal contributions instead of allowance payments.
