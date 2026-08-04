# IMP-701 — Excel Import Implementation Report

**Project:** PF AI Personal Finance SaaS
**Card:** IMP-701 — Excel Import
**Date:** 2026-08-04
**Planning Reference:** `PLAN_V2.md`, PF-008 (Import Strategy)

---

## Summary

Added a `.xlsx` Excel parser and upload route to the existing import module (`app/imports/`), reusing the exact same `ImportJob`/`ImportedRow` architecture, tenant scoping, RLS, validation, duplicate detection, and confirm-to-journal-entry flow already built for CSV (IMP-700) and SMS (IMP-702) imports. No report/report-calculation code, no CSV parser code, and no confirm/posting logic was rebuilt — `ExcelParser` only produces the same row shape (`parsed_data`, `validation_errors`, `duplicate_key`, `status`) the rest of the pipeline already understands, and `ImportService.confirm_job` posts Excel rows through the unchanged `AccountingService.create_journal_entry` path exactly like CSV and SMS rows.

`openpyxl` (already listed in `requirements.txt`) is used in `read_only=True, data_only=True` mode, so workbook formulas and macros are never executed — only cached cell values are read, and the uploaded file is parsed entirely in memory and never written to disk. Only `.xlsx` is supported; legacy `.xls` is explicitly rejected with a clear error.

No database schema changes were required. `ImportJob.import_type` is already a free-form `String(20)` column (as used for `"sms"`), so `import_type = "excel"` needed no migration. Alembic head remains `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `app/imports/parsers/excel_parser.py` — `ExcelParser`, `ParsedExcelRow`, `ExcelParseError`, `parse_excel_import`, `compute_excel_hash`.
- `docs/audits/IMP-701_EXCEL_IMPORT_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/imports/parsers/__init__.py` — exported `ExcelParser`/`parse_excel_import` alongside the existing CSV exports.
- `app/imports/services.py` — added `ImportService.create_excel_job` (mirrors `create_job`/`create_sms_job`); extended `_resolve_category_account` with one additional, backward-compatible fallback step (a per-row `default_account_id`, populated only for Excel rows that supplied one at upload time and have no account/category column value — CSV/SMS rows are unaffected since that key is never set for them).
- `app/imports/routes.py` — added `POST /imports/excel/upload`; all other routes (`GET /imports/{job_id}`, `GET /imports/{job_id}/rows`, `POST /imports/{job_id}/confirm`, `POST /imports/{job_id}/cancel`) are unchanged and work identically for Excel jobs.
- `app/tests/integration/test_imports.py` — 21 new tests (parser unit tests + upload/confirm/tenant-isolation/account-visibility integration tests) appended to the existing CSV/SMS test file.
- `docs/audits/PLAN_V2_CARD_STATUS.md`, `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md`, `docs/summaries/summary33.md` — status/documentation updates.

`app/imports/models.py`, `app/imports/parsers/csv_parser.py`, `app/imports/parsers/sms_parser.py`, and the confirm/cancel/get-job routes and services were **not modified** in behavior — Excel jobs flow through the exact same `ImportJob`/`ImportedRow` tables and confirm logic.

---

## Dependency Added

None. `openpyxl` was already present in `requirements.txt` (line 28) and already installed (`3.1.5`) — it was added in an earlier card for document/report tooling but had not yet been used for import parsing. No new package was added.

---

## Routes Added

| Method | Route | Description |
|---|---|---|
| POST | `/imports/excel/upload` | *(new)* Upload and preview an `.xlsx` workbook. Multipart form: `file` (required), `sheet_name` (optional), `mapping` (optional JSON string), `default_account_id` (optional int), `default_currency` (optional string). Returns the same `ImportPreviewResponse` shape as CSV/SMS upload. |
| GET | `/imports/{job_id}` | *(unchanged)* Works identically for Excel jobs. |
| GET | `/imports/{job_id}/rows` | *(unchanged)* Works identically for Excel jobs. |
| POST | `/imports/{job_id}/confirm` | *(unchanged)* Posts valid, non-duplicate Excel rows as journal entries exactly like CSV/SMS rows. |
| POST | `/imports/{job_id}/cancel` | *(unchanged)* Works identically for Excel jobs. |

All routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other import route.

---

## Excel Formats Supported

- **`.xlsx` only** (Office Open XML). The upload route rejects any filename that does not end in `.xlsx` with a `400` and a clear message.
- **Legacy `.xls` (old binary format) is explicitly not supported** — documented as a known limitation below, matching the card's instruction to only support it "if easy and safe," which it is not (it requires a separate dependency, e.g. `xlrd`, with its own parsing/security surface).
- Macro-enabled workbooks are not treated specially — `.xlsm` files are simply rejected by the `.xlsx`-only extension check before any parsing is attempted.
- A file that has a `.xlsx` name but is not a valid Office Open XML zip archive (corrupted, truncated, or not actually an Excel file) is caught and returns a safe `400` error, never a `500`.

---

## Sheet / Header Behavior

- **Worksheet selection:** defaults to the **first worksheet** in the workbook (`workbook.worksheets[0]`). An optional `sheet_name` form field selects a specific worksheet by name; if the name does not exist, a `400` error lists the available worksheet names.
- **Header row detection:** the parser scans rows from the top and treats the **first row containing at least one non-blank cell** as the header row (so a worksheet with a blank title row or two before the real header still parses correctly). Blank header cells are given a placeholder name (`Column 1`, `Column 2`, ...).
- **Blank row skipping:** any fully blank data row (all cells `None` or whitespace-only) between data rows is silently skipped — it is not counted as a row and never appears as invalid.
- Row numbers reported in the preview reflect the worksheet's actual row position (header = row 1, first data row = row 2, etc.), matching the CSV parser's convention.

---

## Mapping Behavior

Column-to-field mapping reuses the **exact same alias table and detection function** as the CSV parser (`COLUMN_ALIASES` / `_detect_mapping` in `app/imports/parsers/csv_parser.py`, imported directly rather than duplicated), so a worksheet with headers like `Date`, `Narration`, `Debit`, `Credit`, `Reference`, `Category` auto-maps identically to how the same headers would map in a CSV file. An optional `mapping` form field (JSON string matching `ColumnMapping`) can override auto-detection, exactly like the CSV upload's `mapping` field.

---

## Validation Behavior

Each row is validated identically to CSV/SMS rows:

- `date` is required — native Excel date/datetime cells are read directly (no string round-trip needed); text-formatted date cells fall back to the same date-format list the CSV parser uses.
- `description` is required and non-empty.
- A valid non-zero amount must be resolvable from a single `amount` column, or `debit`/`credit` columns (numeric cells are read directly; text-formatted numbers are parsed the same way the CSV parser handles comma-formatted strings). Rows with both debit and credit populated are ambiguous and marked invalid.
- `currency` defaults to `OMR` (or the `default_currency` form field, if supplied) whenever the row has no currency column value.
- Validation errors are stored in `imported_rows.validation_errors` and returned in the preview response, identically to CSV/SMS.

---

## Duplicate Detection Behavior

Uses the **same deterministic duplicate-key function** as CSV (`_build_duplicate_key`, imported directly, not duplicated):

```
{date}|{amount}|{normalized description}|{reference}
```

The first occurrence of a key within the workbook is `valid`; subsequent occurrences are `duplicate` and linked via `duplicate_of_row_id`, exactly like CSV import.

---

## Confirm-to-Accounting Behavior

**Unchanged and fully reused.** `POST /imports/{job_id}/confirm` calls the same `ImportService.confirm_job` → `AccountingService.create_journal_entry` path used by CSV and SMS jobs — no new posting logic was written for Excel. Expense rows debit the resolved category/expense account and credit the bank account; income rows debit the bank account and credit the resolved income account; `AccountingService` enforces debits = credits before committing, and the entry's `source` is set to `"import"`.

One small, additive, backward-compatible change was made to the shared `_resolve_category_account` helper: after the existing account/category-column lookup and before the confirm-time `default_income_account_id`/`default_expense_account_id` fallback, it now also checks a per-row `default_account_id` (only ever populated for Excel rows that supplied the optional `default_account_id` upload parameter **and** had no account/category column value of their own). This lets a spreadsheet with no per-transaction category column still resolve to a sensible account without inventing new confirm-time semantics — CSV and SMS rows never set this key, so their resolution order is completely unaffected.

---

## RLS / Tenant Safety

- `POST /imports/excel/upload` uses `get_db_with_tenant_context` + `require_tenant_member`, identical to every other import route.
- `ImportJob`/`ImportedRow` rows created from Excel uploads carry the same `tenant_id` column and are protected by the same RLS + FORCE RLS policies already verified for CSV/SMS jobs (`import_jobs`, `imported_rows`).
- `test_tenant_cannot_see_other_tenant_excel_job` confirms Tenant B receives a `404` when requesting Tenant A's Excel import job by ID.
- `test_rls_active_on_import_tables_for_excel_jobs` re-confirms RLS + FORCE RLS remain enabled on both import tables.
- `test_excel_import_account_visibility_enforced` confirms that a non-elevated family member cannot post an Excel-imported row against another member's private bank account — the existing `FamilyAccountAccessService.can_use_account_for_posting` check (already used by CSV/SMS confirm) applies unchanged to Excel rows.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **645 passed, 1 skipped** (up from the REP-2001 baseline of 624 passed, 1 skipped — 21 new tests, zero regressions)

`app/tests/integration/test_imports.py` Excel section covers:
- Parser unit tests: basic `.xlsx` parsing, native date-cell parsing, debit/credit columns, negative single-amount column, blank-row skipping, invalid-row capture, duplicate detection, unknown-sheet-name rejection, non-workbook-bytes rejection, named-sheet selection.
- Upload/auth: unauthenticated upload rejected; authenticated upload creates a job and preview rows; `sheet_name` + `mapping` form fields honored; duplicate rows detected via the upload endpoint; unsupported extension (`.xls`) rejected; corrupted `.xlsx`-named file rejected safely (`400`, not `500`).
- Tenant/RLS: Tenant B cannot see Tenant A's Excel job; RLS/FORCE RLS re-verified on `import_jobs`/`imported_rows`.
- Confirm-to-accounting: valid Excel rows post as journal entries; invalid and duplicate rows are skipped; account-visibility rules block posting against a private account the uploader does not own.

Regression: the full existing CSV (`IMP-700`) and SMS (`IMP-702`) test suites in the same file, plus the complete project test suite, all pass unchanged.

---

## Known Limitations

- **Legacy `.xls` is not supported** — only Office Open XML `.xlsx` workbooks are accepted. Users with old `.xls` files must re-save as `.xlsx` (standard in any modern spreadsheet application) before uploading.
- **Formula cells:** `data_only=True` reads a formula cell's last-cached value as saved by the spreadsheet application. If a workbook was generated programmatically and never opened/saved in Excel/LibreOffice/Google Sheets, formula cells may have no cached value and will read as blank. Static value cells (the overwhelming majority of bank/budget exports) are unaffected.
- **Single default worksheet unless specified:** if a workbook has multiple sheets and the caller does not pass `sheet_name`, only the first sheet is parsed. There is no "parse all sheets" mode in this card.
- **No column-mapping UI:** like CSV import, the upload endpoint accepts a `mapping` JSON parameter, but no frontend form was added for building it interactively (tracked the same way as the CSV import UI gap — see IMP-703 below).
- **`default_account_id` is a best-effort, per-row fallback**, not a replacement for the confirm-time `default_income_account_id`/`default_expense_account_id` parameters — it only applies when a row has no account/category column value of its own.
- **Bulk/background imports:** as with CSV, large workbooks are parsed synchronously within the request. Very large files should move to a background task in a future card.

---

## Recommended Next Card

**IMP-703 — Import UI**

`PLAN_V2_CARD_STATUS.md` lists `IMP-703` (Import UI Refinements) as **Missing**. CSV (IMP-700), SMS (IMP-702), and now Excel (IMP-701) import are all fully functional at the API level, but there is still no user-facing page to upload a file, review the preview/validation/duplicate results, adjust column mapping, and confirm the import — users can currently only drive the import pipeline via direct API calls. Building a Report-Center-style UI (`GET /imports`, HTMX preview/confirm partials, following the exact pattern established by REP-2001) on top of the now-complete three-format import pipeline is the natural next step and does not require touching any parser or posting logic.
