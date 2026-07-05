# Summary 06 - Card 13: BILL-801A Payment Posting Through Accounting Engine

## What was implemented

- Bill mark-paid now posts a balanced journal entry through `AccountingService`.
- Subscription mark-paid now posts a balanced journal entry through `AccountingService`.
- Added nullable payment posting columns on bills and subscriptions:
  - `payment_account_id`
  - `expense_account_id`
  - `payment_journal_entry_id`
- Added tenant-aware deterministic journal references:
  - `BILL-{tenant_id}-{bill_id}`
  - `SUB-{tenant_id}-{subscription_id}`
- Mark-paid validates tenant ownership and account types.
- Mark-paid is idempotent and repeated calls do not duplicate journal entries.
- Mark-unpaid is blocked after posting because reversal support is not implemented.
- Dashboard bill mark-paid uses the same safe service path and returns a clear missing-account warning.

## Migration

`89f59125ee5e` - add payment posting columns to bills and subscriptions.

## Tests

Added and updated bill, subscription, dashboard, tenant-isolation, account-validation, idempotency, and safe mark-unpaid tests.

Focused checks:

- Bills/subscriptions: 33 passed.
- Dashboard widget: 14 passed.

Final verification:

- `python -m compileall app` passed.
- `alembic current` returned `89f59125ee5e (head)`.
- `alembic upgrade head` passed.
- `python scripts/inspect_db.py` passed.
- `python scripts/seed_default_data.py --dev` passed.
- Full pytest run passed: 156 passed, 1 skipped.

## Known limitations

- No journal-entry reversal yet.
- Subscription payment history is limited to one stored payment journal entry.

## Next recommended card

**ACC-503A - Journal Entry Reversal Support**
