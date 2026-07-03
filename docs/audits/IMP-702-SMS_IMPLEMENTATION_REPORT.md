# IMP-702-SMS — SMS Bank Alert Parser Implementation Report

**Project:** PF AI Personal Finance SaaS  
**Card:** IMP-702-SMS  
**Date:** 2026-07-03  
**Planning Reference:** `PLAN_V2.md`

---

## Summary

Implemented a rule-based SMS bank-alert parser for the Oman market. The parser reuses the existing `ImportJob` / `ImportedRow` workflow created in IMP-700-CSV, so preview, duplicate detection, and confirm-to-transaction posting work identically for SMS imports. No new database tables or Alembic migrations were required because `import_type` is stored as a free-form `String(20)` column.

All existing safety rules were respected: RLS remains enabled and forced, no universal admin bypass was introduced, no real financial data was used in tests, and no secrets were committed.

---

## Files Changed

- `app/imports/parsers/sms_parser.py` (new)
- `app/imports/schemas.py` — added `SMSParseRequest`
- `app/imports/services.py` — added `ImportService.create_sms_job`
- `app/imports/routes.py` — added `POST /imports/sms/parse`
- `app/tests/fixtures/imports/sample_sms_bank_muscat.txt` (new)
- `app/tests/fixtures/imports/sample_sms_bankdhofar.txt` (new)
- `app/tests/fixtures/imports/sample_sms_oab.txt` (new)
- `app/tests/fixtures/imports/sample_sms_invalid.txt` (new)
- `app/tests/integration/test_imports.py` — SMS parser and endpoint tests
- `docs/audits/IMP-702-SMS_IMPLEMENTATION_REPORT.md` (this file)
- `docs/audits/PLAN_V2_CARD_STATUS.md`
- `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md`

---

## Data Model Changes

No schema changes were required.

- `ImportJob.import_type` already supports arbitrary strings up to 20 characters.
- SMS jobs use `import_type = "sms"`.
- `ImportedRow` stores the raw SMS text in `raw_data["message"]` and normalized parsed values in `parsed_data`.
- Existing RLS policies on `import_jobs` and `imported_rows` automatically protect SMS import data.

**Alembic revision:** N/A (no migration created).

---

## Supported Bank Patterns

The parser uses bank-specific regex patterns for the following Omani banks, plus a generic fallback for unrecognized messages:

| Bank | Status | Example Extracted Fields |
|------|--------|--------------------------|
| Bank Muscat | Supported | amount, date, account mask, balance, reference/merchant |
| BankDhofar | Supported | amount, date, account mask, reference/merchant |
| Oman Arab Bank (OAB) | Supported | amount, merchant, date, account mask, balance |
| Alizz Islamic Bank | Supported | amount, date, account mask, balance |
| Sohar International | Pattern included | amount, date, account mask (when present) |
| National Bank of Oman (NBO) | Pattern included | amount, date, account mask (when present) |
| Generic fallback | Supported | amount, date, currency, balance, account mask from any text |

Patterns were validated against fake SMS messages only. No real customer data was used.

---

## Parser Behavior

- **Whitespace normalization** and **Arabic-to-Western digit translation** are applied before parsing.
- **Amount parsing** supports commas as thousands separators and 3-decimal OMR values (e.g., `OMR 1,234.567`).
- **Date parsing** supports:
  - `DD/MM/YYYY`
  - `DD-MM-YYYY`
  - `DD-MMM-YYYY` (e.g., `01-JUL-2026`)
  - `YYYY-MM-DD`
- **Debit/credit inference** uses keywords:
  - Debit/expense: debited, debit, purchase, withdrawn, charges, fee, paid, payment, spent
  - Credit/income: credited, credit, deposit, salary, received, transfer in
- **Time** is extracted if present (`HH:MM` or `HH:MM:SS`).
- **Available balance** is extracted from phrases like "Available balance", "Avl Bal", "Balance".
- **Masked account** is extracted from patterns like `****1234` or `XXXX1234`.
- **Reference / merchant** is extracted from `Ref:` or `at <merchant>` patterns.
- **Confidence score**: `high` when a bank-specific pattern matches, `low` for the generic fallback.
- **Validation errors** are returned for messages missing bank identity, amount, date, or description.

---

## Validation Behavior

Each parsed SMS is validated independently:

- Missing bank identification and generic parsing → error
- Missing or zero amount → error
- Missing date → error
- Missing description → error

Invalid messages still create `ImportedRow` records with `status = "invalid"` so the preview UI can show what went wrong.

---

## Duplicate Detection Behavior

Duplicate detection uses the same deterministic key used by CSV rows, extended with the account mask when available:

```
{date}|{amount}|{normalized_description}|{reference}|{account_mask}
```

Duplicates are detected within a single pasted SMS batch. The first valid occurrence is kept; subsequent matches are marked `duplicate` with `duplicate_of_row_id` pointing to the original.

---

## Routes Added

| Method | Path | Description |
|--------|------|-------------|
| POST | `/imports/sms/parse` | Parse pasted SMS text and return a preview job |
| GET | `/imports/{job_id}` | Reused from CSV card; returns SMS job summary |
| GET | `/imports/{job_id}/rows` | Reused from CSV card; returns parsed SMS rows |
| POST | `/imports/{job_id}/confirm` | Reused from CSV card; posts valid SMS rows as journal entries |
| POST | `/imports/{job_id}/cancel` | Reused from CSV card; cancels the SMS job |

All routes require an authenticated tenant member and set RLS tenant context via `get_db_with_tenant_context`.

---

## Confirm-to-Transaction

Confirmed SMS rows are posted through the existing `AccountingService.create_journal_entry` double-entry flow:

- Debit-type SMS → debit expense category account, credit bank account
- Credit-type SMS → debit bank account, credit income category account
- Invalid and duplicate rows are skipped
- Imported rows store `journal_entry_id` in `parsed_data`

---

## Test Results

- **Baseline (before this card):** 59 passed, 1 skipped
- **After this card:** 74 passed, 1 skipped
- **New SMS tests:** 15
- **All verification commands passed:**
  - `python -m compileall app`
  - `alembic current` → `9ee380da96d5 (head)`
  - `alembic history`
  - `alembic upgrade head`
  - `python scripts/inspect_db.py` → 42 tables, 32 RLS-enabled, FORCE RLS active
  - `python scripts/seed_default_data.py --dev` (idempotent)
  - `python -m pytest -q` → 74 passed, 1 skipped

---

## Known Limitations

- The parser is rule-based, not AI-driven. It will not adapt to new bank message templates unless a new regex pattern is added.
- Merchant/description extraction from generic messages can be imperfect for unusual phrasing.
- Category suggestion is not implemented; the confirm endpoint relies on the existing default income/expense account mapping or CSV-style account lookup.
- No learning/correction feedback loop is implemented yet.
- Sohar International and NBO patterns are included but were only validated syntactically because no fake sample fixtures were required for this card.

---

## Security and Safety Compliance

- ✅ RLS remains enabled on `import_jobs` and `imported_rows`.
- ✅ FORCE ROW LEVEL SECURITY remains enabled.
- ✅ No universal admin bypass was introduced.
- ✅ No real personal financial data was imported or stored in fixtures.
- ✅ No secrets were committed; `.env` remains ignored.
- ✅ No Excel import, bank API, or AI/LLM integration was added.
- ✅ No modular monolith refactor beyond the SMS/import module work.

---

## Recommended Next Card

**AI-1201-LLM — Integrate OpenAI LLM Client**

With CSV and SMS import complete, the highest-value next step is LLM integration. The AI CFO engines (`AIOrchestrator`, health score, insights, chat) currently operate with rule-based logic. Adding an OpenAI client wrapper with prompt management, cost tracking, tenant limits, and safety filtering will provide the core intelligence differentiator described in `PLAN_V2.md`.

After AI-1201, the next priorities remain:
- **IMP-701-EXCEL** — Excel import parser (lower priority than SMS for Oman).
- **BILL-800 / SUB-900** — Bills and subscriptions routers.
- **AUTH-305** — Tenant member invitation flow.
