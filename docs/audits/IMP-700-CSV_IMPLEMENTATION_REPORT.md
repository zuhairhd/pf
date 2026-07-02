# IMP-700-CSV — Create Import Module with CSV Parser

**Date:** 2026-07-02  
**Project:** PF (AI Personal Finance SaaS)  
**PLAN_V2 Reference:** PF-008 (Import Strategy) + IMP-700 (CSV Import)  
**Alembic Revision:** `9ee380da96d5`  
**Status:** Complete

---

## Summary

Implemented a tenant-scoped CSV import module under `app/imports/`. The module provides upload, preview, row-level validation, duplicate detection, and confirmation into journal entries. Both import tables are protected by PostgreSQL Row-Level Security with `FORCE ROW LEVEL SECURITY`, and all endpoints require authentication and tenant membership.

During implementation, a few related issues were discovered and fixed so that the import flow could be verified end-to-end:

- `app/routers/accounts.py` was missing the `request` parameter in `create_account`, so it could not read the JWT-derived tenant context.
- `app/core/rls.py` only set tenant context once per session; after `commit()` the `SET LOCAL` context was lost, causing post-commit queries/refresh to fail under RLS. An `after_begin` event listener now re-applies the bound tenant context at the start of every transaction.
- `app/services/accounting_service.py` generated journal-entry references per-tenant but the `reference` column has a global unique constraint, causing collisions across tenants. References now include the tenant id.
- `requirements.txt` now pins `bcrypt<5.0` to keep `passlib[bcrypt]` working.
- `app/seeds/default_data.py` now truncates `DEV_SUPERUSER_PASSWORD` to bcrypt's 72-byte limit when a long env password is supplied.

---

## Files Changed / Added

### New import module

- `app/imports/__init__.py`
- `app/imports/models.py` — `ImportJob`, `ImportedRow`
- `app/imports/schemas.py` — `ColumnMapping`, `CSVUploadRequest`, `ParsedRow`, `ImportJobSummary`, `ImportPreviewResponse`, `ImportConfirmRequest`, `ImportConfirmResponse`
- `app/imports/services.py` — `ImportService` (create, get, confirm, cancel)
- `app/imports/routes.py` — `/imports/csv/upload`, `/imports/{job_id}`, `/imports/{job_id}/rows`, `/imports/{job_id}/confirm`, `/imports/{job_id}/cancel`
- `app/imports/parsers/__init__.py`
- `app/imports/parsers/csv_parser.py` — `CSVParser`, `parse_csv_import`, `compute_file_hash`

### Alembic migration

- `alembic/versions/9ee380da96d5_add_import_job_tables.py`

### Tests and fixtures

- `app/tests/integration/test_imports.py`
- `app/tests/fixtures/imports/sample_bank_statement.csv`
- `app/tests/fixtures/imports/sample_debit_credit.csv`
- `app/tests/fixtures/imports/sample_invalid_rows.csv`
- `app/tests/fixtures/imports/sample_duplicates.csv`

### Related fixes

- `app/main.py` — wired `imports_router` at `/imports`
- `app/models/__init__.py` — exported `ImportJob`, `ImportedRow`
- `app/routers/accounts.py` — added `request: Request` and switched `create_account` to `get_db_with_tenant_context`
- `app/core/rls.py` — added `after_begin` event listener and session-info tracking
- `app/services/accounting_service.py` — tenant-aware journal-entry reference generation
- `app/seeds/default_data.py` — bcrypt 72-byte password guard
- `requirements.txt` — pinned `bcrypt<5.0`

---

## Data Model

### `import_jobs`

| Column | Notes |
|--------|-------|
| `id` | Primary key |
| `tenant_id` | RLS filter column; indexed |
| `user_id` | FK → `users.id`; indexed |
| `import_type` | e.g. `csv` |
| `status` | `preview`, `completed`, `cancelled` |
| `original_filename` | Uploaded file name |
| `file_hash` | SHA-256 of content; indexed |
| `mapping` | JSONB column mapping CSV headers → app fields |
| `total_rows`, `valid_rows`, `invalid_rows`, `duplicate_rows`, `imported_rows` | Counters |
| `errors` | JSONB list of job-level errors |
| `completed_at`, `created_at`, `updated_at` | Timestamps |

### `imported_rows`

| Column | Notes |
|--------|-------|
| `id` | Primary key |
| `tenant_id` | RLS filter column; indexed |
| `import_job_id` | FK → `import_jobs.id` with `ON DELETE CASCADE`; indexed |
| `row_number` | Position in source CSV |
| `raw_data` | JSONB raw CSV values |
| `parsed_data` | JSONB normalized values (date ISO string, amount string, type, etc.) |
| `validation_errors` | JSONB list of per-row errors |
| `duplicate_key` | Deterministic key for duplicate detection; indexed |
| `duplicate_of_row_id` | Self-referencing FK when row is a duplicate |
| `status` | `valid`, `invalid`, `duplicate`, `imported`, `skipped` |
| `created_at`, `updated_at` | Timestamps |

---

## Alembic Migration

- **Revision ID:** `9ee380da96d5`
- **Down revision:** `542823443f9e`
- **Head:** yes
- Creates `import_jobs` and `imported_rows` tables with indexes.
- Enables RLS and `FORCE ROW LEVEL SECURITY` on both tables.
- Adds SELECT / INSERT / UPDATE / DELETE policies using `app.current_tenant_id`.

---

## RLS Policy Details

Both tables use the standard tenant-scoped policy expression:

```sql
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER)
```

RLS status after migration:

- Total tables: 42
- RLS enabled: 32
- FORCE RLS enabled: 32
- Tables intentionally without RLS: 10 (global/auth/system tables documented in previous cards)

---

## CSV Formats Supported

The parser (`app/imports/parsers/csv_parser.py`) supports:

- UTF-8 and UTF-8 with BOM
- Comma-delimited CSV
- Header detection
- Empty-line skipping
- Whitespace trimming
- Decimal parsing with comma thousands separators removed
- Date formats: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, `DD-MMM-YYYY`, `DD-MMMM-YYYY`
- Single amount column with positive/negative values
- Separate `Debit` and `Credit` columns
- Optional `Currency` column (defaults to OMR in UI)
- Optional `Reference`, `Description`, `Account`, `Category`, `Balance` columns

### Column aliases

| App field | Aliases detected |
|-----------|------------------|
| `date` | Date, Transaction Date, Posting Date, Txn Date, Value Date |
| `description` | Description, Narration, Details, Merchant, Payee, Counterparty, Transaction Details |
| `amount` | Amount, Value, Total, Transaction Amount |
| `debit` | Debit, Debit Amount, Money Out |
| `credit` | Credit, Credit Amount, Money In |
| `transaction_type` | Type, Transaction Type, Txn Type, Debit/Credit |
| `account` | Account, Account Name, Account Number, From Account |
| `category` | Category, Expense Category, Income Category |
| `reference` | Reference, Ref, Transaction ID, Txn ID, Reference Number |
| `currency` | Currency, Ccy |
| `balance` | Balance, Running Balance |

---

## Validation Behavior

Each row is validated and invalid rows are captured for preview:

- `date` is required and must be parseable.
- `description` is required and non-empty.
- A valid non-zero amount must be resolvable from `amount`, `debit`, `credit`, or negative `amount`.
- Rows with both debit and credit populated are treated as ambiguous/invalid.
- Validation errors are stored in `imported_rows.validation_errors` and returned in the preview response.

---

## Duplicate Detection

Duplicate detection is deterministic and tenant-scoped. The duplicate key is:

```
{date}|{amount}|{normalized description}|{reference}
```

- The first occurrence of a key in a file is marked `valid`.
- Subsequent occurrences in the same file are marked `duplicate` and linked to the first row via `duplicate_of_row_id`.
- Duplicate rows are **not** imported by default.

---

## Routes Added

All routes require `require_tenant_member` and use `get_db_with_tenant_context`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/imports/csv/upload` | Upload/preview CSV; returns job summary + rows |
| GET | `/imports/{job_id}` | Get job summary |
| GET | `/imports/{job_id}/rows` | List parsed rows with optional status filter |
| POST | `/imports/{job_id}/confirm` | Import valid non-duplicate rows as journal entries |
| POST | `/imports/{job_id}/cancel` | Cancel a preview job |

### Confirm payload

```json
{
  "bank_account_id": 1,
  "default_income_account_id": 2,
  "default_expense_account_id": 3,
  "import_duplicates": false
}
```

- Expenses debit the category/expense account and credit the bank account.
- Income debits the bank account and credits the income account.
- The journal entry `source` is set to `"import"`.

---

## Confirm-to-Transaction Status

**Implemented.** Valid, non-duplicate rows are posted through the existing `AccountingService.create_journal_entry` path, which validates that debits equal credits before committing. No journal entry is created for invalid or duplicate rows.

Rows are marked `imported` on success and the job status becomes `completed`.

---

## Test Results

Full test suite run after changes:

```
59 passed, 1 skipped in ~20s
```

New import tests cover:

- UTF-8 BOM handling
- Common date formats
- Debit/credit column resolution
- Negative amount column handling
- Invalid row capture
- Duplicate detection
- Anonymous upload rejection
- Authenticated upload creates job + rows
- Tenant isolation (Tenant B cannot see Tenant A's job)
- RLS active on `import_jobs` and `imported_rows`
- Confirm imports valid rows into journal entries
- Cancel job flow

---

## Verification Commands Run

```bash
python -m compileall app
alembic current
alembic history --indicate-current
python scripts/inspect_db.py
python scripts/seed_default_data.py --dev
python scripts/seed_default_data.py --dev   # idempotency check
python -m pytest -q
```

All commands completed successfully.

---

## Known Limitations / Deferred Items

- **Excel import:** Not built; deferred to **IMP-701-EXCEL**.
- **SMS import:** Not built; next card is **IMP-702-SMS**.
- **Column mapping UI:** The API accepts a `mapping` object; no frontend UI was added in this card.
- **Bulk/background imports:** Large files are parsed synchronously within the request. Very large imports should be moved to a Celery task in a future card.
- **Reference uniqueness:** The journal-entry reference now includes `tenant_id` so the global unique constraint is safe, but a future migration may want to make the constraint composite (`tenant_id`, `reference`).
- **No `ImportMapping` table:** Mappings are stored as JSONB on `import_jobs`. A reusable saved-mapping table can be added later if users need saved templates.

---

## Security Notes

- RLS and FORCE RLS remain enabled.
- No universal admin bypass was added.
- Import endpoints require a valid JWT with `tenant_id`.
- Tenant B cannot see Tenant A's import jobs or rows.
- Imported rows carry a direct `tenant_id` for simple, performant RLS policies.
- CSV content is passed as a string in the request body in this first version; a future iteration should accept multipart file uploads.

---

## Recommended Next Card

**IMP-702-SMS — Implement SMS Bank Alert Parser**

SMS alerts are the most reliable transaction source in Oman. The CSV import path is now stable and provides the same job/row/confirm pattern that SMS parsing can reuse.
