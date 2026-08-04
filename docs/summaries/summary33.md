> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 40: IMP-701 — Excel Import**.

# Summary 33 — Card 40: IMP-701 Excel Import

## What Was Done

Added `.xlsx` Excel import to the existing `app/imports/` module, reusing the exact same `ImportJob`/`ImportedRow` architecture, RLS/tenant scoping, validation, duplicate detection, and confirm-to-journal-entry flow already built for CSV (IMP-700) and SMS (IMP-702) imports — no CSV parser code, report logic, or posting logic was rebuilt. `openpyxl` (already a project dependency) is used in `read_only=True, data_only=True` mode so workbook formulas and macros are never executed; the uploaded file is parsed entirely in memory and is never written to disk. Only `.xlsx` is supported.

## Key Changes

- No schema changes; no Alembic migration (`import_type` is already a free-form `String(20)` column, as used for `"sms"`). Head unchanged at `bd89e4fcf4b9`.
- `app/imports/parsers/excel_parser.py` (new): `ExcelParser` reuses the CSV parser's column-alias detection (`_detect_mapping`) and duplicate-key logic (`_build_duplicate_key`) directly rather than duplicating them. Supports first-worksheet-by-default with optional `sheet_name`, header-row detection, blank-row skipping, native date cells, numeric debit/credit and single-amount columns, and safe per-row parsing errors.
- `app/imports/services.py`: added `ImportService.create_excel_job` (mirrors `create_job`/`create_sms_job`); extended `_resolve_category_account` with one small, additive, backward-compatible fallback (a per-row `default_account_id`, populated only for Excel rows that supplied one at upload time — CSV/SMS resolution is unaffected).
- `app/imports/routes.py`: added `POST /imports/excel/upload` (multipart: file, optional `sheet_name`, `mapping`, `default_account_id`, `default_currency`). All other import routes (get job, get rows, confirm, cancel) are unchanged and work identically for Excel jobs.
- `app/tests/integration/test_imports.py`: 21 new tests appended — Excel parser unit tests (date cells, debit/credit, negative amounts, blank-row skipping, invalid rows, duplicates, unknown sheet, corrupted workbook, named-sheet selection) and integration tests (auth, upload/preview, sheet/mapping form fields, tenant isolation, RLS, confirm posts valid rows, confirm skips invalid/duplicate rows, account-visibility enforcement, unsupported extension rejection).

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **645 passed, 1 skipped** (up from 624 passed, 1 skipped)

## Next Recommended Card

**IMP-703 — Import UI**
