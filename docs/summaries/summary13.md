> **Note:** Summary files are incrementally appended. If this file is empty, the previous summary did not reach the final stage. This entry covers the work completed for **Card 20: REP-2000 — Basic Financial Reports**.

# Summary 13 — Card 20: REP-2000 Basic Financial Reports

## What Was Done

Implemented tenant-scoped, RLS-safe basic financial reports that read from posted journal entries.

## Key Changes

- Created `app/reports/` module with schemas, service layer, and per-report generators:
  - Income Statement
  - Balance Sheet
  - Cash Flow Summary
  - Net Worth Summary
  - Expense Analysis
- Extended `AccountingService` to support optional `exclude_reversed` and `as_of_date` parameters without changing existing callers.
- Added `/reports/*` JSON endpoints:
  - `GET /reports/income-statement`
  - `GET /reports/balance-sheet`
  - `GET /reports/cash-flow`
  - `GET /reports/net-worth`
  - `GET /reports/expense-analysis`
- Registered the reports router in `app/main.py`.
- Added 10 integration tests in `app/tests/integration/test_reports.py` covering calculations, date filtering, reversals, auth, tenant isolation, and RLS.
- No Alembic migration was required.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `33f87e4863be`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest --tb=no --disable-warnings` — **236 passed, 1 skipped**

## Next Recommended Card

**DOC-2100 — Document OCR / Document Management Enhancement**
