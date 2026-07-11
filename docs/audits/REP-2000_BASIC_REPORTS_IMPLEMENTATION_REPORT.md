> **Card:** REP-2000 — Basic Financial Reports
> **Status:** ✅ DONE
> **Alembic Head:** `33f87e4863be` (no new migration required)

# REP-2000 Basic Financial Reports Implementation Report

## Summary

Implemented tenant-scoped, RLS-safe basic financial reports using posted journal entries. Reports are served as JSON via `/reports/*` and reuse the existing double-entry accounting data. No PDF/Excel export, BI charts, tax reports, or AI explanations were added.

## Files Changed

- `app/services/accounting_service.py`
  - Extended `get_account_balance`, `get_income_statement`, and `get_balance_sheet` to support optional `exclude_reversed` and `as_of_date` parameters while preserving existing behavior.
- `app/reports/__init__.py`
- `app/reports/schemas.py`
- `app/reports/services.py`
- `app/reports/generators/income_statement.py`
- `app/reports/generators/balance_sheet.py`
- `app/reports/generators/cash_flow.py`
- `app/reports/generators/net_worth.py`
- `app/reports/generators/expense_analysis.py`
- `app/routers/reports.py`
- `app/main.py` — registered `/reports` router
- `app/tests/integration/test_reports.py`

## Model/Schema Changes

No new database tables or migrations were required. Reports are derived from existing `accounts`, `journal_entries`, and `journal_lines`. New Pydantic response schemas were added in `app/reports/schemas.py`:

- `IncomeStatementResponse`
- `BalanceSheetResponse`
- `CashFlowResponse`
- `NetWorthResponse`
- `ExpenseAnalysisResponse`

## Routes Added

- `GET /reports/income-statement?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /reports/balance-sheet?as_of_date=YYYY-MM-DD`
- `GET /reports/cash-flow?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /reports/net-worth?as_of_date=YYYY-MM-DD`
- `GET /reports/expense-analysis?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

All routes require authentication, tenant membership, and use `get_db_with_tenant_context` so RLS remains enforced. Date-range endpoints validate that `start_date <= end_date`.

## Report Calculation Rules

### Income Statement
- Aggregates `Income` accounts on the credit side and `Expense` accounts on the debit side.
- `net_income = income_total - expense_total`.
- Date range filters journal entries by `JournalEntry.date`.

### Balance Sheet
- Aggregates `Asset`, `Liability`, and `Equity` accounts.
- `net_worth = assets_total - liabilities_total`.
- `balance_check = assets_total == liabilities_total + equity_total`.
- `as_of_date` filters balances up to that date.

### Cash Flow Summary
- Uses cash/bank asset accounts (`is_bank_account` or `is_cash_account`).
- Falls back to all asset accounts if no accounts are explicitly flagged as bank/cash.
- `cash_inflow` = total debits to cash accounts.
- `cash_outflow` = total credits to cash accounts.
- `net_cash_flow = cash_inflow - cash_outflow`.
- Returns per-account breakdown.

### Net Worth Summary
- Aggregates `Asset` and `Liability` accounts.
- `net_worth = total_assets - total_liabilities`.
- `as_of_date` filters balances up to that date.

### Expense Analysis
- Aggregates `Expense` accounts by balance within the date range.
- Computes `percent_of_total` for each expense account.
- Returns sorted `expenses_by_account` and `top_expense_accounts`.

## Reversal Handling

Both the original journal entry and its reversing entry are included in report totals. Because reversals flip debits and credits, they naturally offset the original entry and prevent report inflation. This matches double-entry semantics and keeps the ledger auditable.

## Date Filtering

- Period reports (`income-statement`, `cash-flow`, `expense-analysis`) require `start_date` and `end_date` and use `start_date <= JournalEntry.date <= end_date`.
- As-of reports (`balance-sheet`, `net-worth`) require `as_of_date` and use `JournalEntry.date <= as_of_date`.
- Invalid date ranges return `400 Bad Request`.

## Permission Behavior

- All report endpoints require `require_tenant_member`.
- Reports use the user's `currency` preference, defaulting to `OMR`.
- No cross-tenant data is exposed; RLS tenant context is set from the JWT before querying.

## RLS/Tenant Safety

- Routes use `get_db_with_tenant_context`, which calls `SET LOCAL app.current_tenant_id` from the JWT.
- Report queries only touch accounts and journal lines visible to the current tenant.
- Integration tests verify that Tenant B cannot see Tenant A report data.
- RLS remains enabled on `journal_entries` and `journal_lines`.

## Test Results

- Added 10 integration tests in `app/tests/integration/test_reports.py`:
  - Income statement totals, net income, and date filtering.
  - Balance sheet totals, net worth, as-of filtering, and balance check.
  - Cash flow inflow/outflow/net by account.
  - Net worth assets/liabilities/net calculation.
  - Expense analysis totals, percentages, and top accounts.
  - Reversal offset behavior.
  - Unauthenticated rejection.
  - Invalid date range rejection.
  - Tenant isolation.
  - RLS status on journal tables.
- Full suite: **236 passed, 1 skipped**.

## Known Limitations

- Reports are JSON-only; PDF/Excel export is deferred.
- Cash-flow classification relies on `is_bank_account` / `is_cash_account` flags; unclassified asset accounts are used as a fallback.
- Family-level report permissions are not yet implemented; any tenant member can request reports.
- Advanced BI charts and AI explanations are deferred.

## Recommended Next Card

**DOC-2100 — Document OCR / Document Management Enhancement**
