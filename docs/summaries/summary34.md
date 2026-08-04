> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 41: IMP-703 — Import UI**.

# Summary 34 — Card 41: IMP-703 Import UI

## What Was Done

Built a browser-facing Import Center on top of the existing CSV/Excel/SMS import pipeline (`app/imports/`) — no parser, validation, duplicate-detection, or confirm/posting logic was rebuilt. A new `GET /imports` page shows CSV/Excel/SMS method cards, an upload workspace, and import history; upload forms post via HTMX to new `POST /imports/ui/*` routes that call the exact same `ImportService.create_job` / `create_excel_job` / `create_sms_job` methods the JSON API already uses. A shared preview partial shows job status, valid/invalid/duplicate/imported counts, and a rows table, with confirm/cancel forms that call the exact same `ImportService.confirm_job` / `cancel_job` methods — confirm still posts through the unchanged `AccountingService`.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `bd89e4fcf4b9`).
- `app/imports/routes.py`: added 11 new UI routes (Import Center, three form partials, three upload routes, preview page + partial, confirm + cancel). All five existing JSON routes are untouched.
- `app/imports/services.py`: added one new read-only method, `ImportService.list_jobs()`, for import history.
- New templates: `imports/index.html`, `imports/preview_page.html`, `imports/partials/{csv,excel,sms}_form.html`, `imports/partials/preview.html`.
- `app/templates/base.html`: added an "Imports" sidebar link.
- Account pickers reuse `FamilyAccountAccessService.list_visible_accounts()` unchanged (same pattern as the dashboard's allowance payment form) — inaccessible private accounts and cross-tenant accounts never appear in any import form.
- Added `app/tests/integration/test_import_ui.py` with 29 tests: Import Center, CSV/Excel/SMS UI, preview/confirm/cancel, account-picker visibility, read-only safety, and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **674 passed, 1 skipped** (up from 645 passed, 1 skipped)

## Next Recommended Card

**GOAL-1401B — Goal Contribution Reversal**
