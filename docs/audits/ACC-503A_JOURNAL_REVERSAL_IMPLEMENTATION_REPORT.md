# ACC-503A Journal Entry Reversal Implementation Report

## Summary

ACC-503A is complete. Posted journal entries are no longer deleted or edited to undo bill/subscription payments. The accounting engine now creates balanced reversing journal entries through `AccountingService.reverse_journal_entry()`.

## Files changed

- `app/models/accounting.py`
- `app/models/subscription.py`
- `app/schemas/accounting.py`
- `app/schemas/bill_subscription.py`
- `app/services/accounting_service.py`
- `app/services/bill_subscription_service.py`
- `app/routers/accounts.py`
- `app/routers/bills.py`
- `app/routers/subscriptions.py`
- `app/routers/dashboard.py`
- `app/tests/integration/test_bills_subscriptions.py`
- `alembic/versions/a7c9d2e4f601_add_journal_entry_reversal_support.py`

## Accounting reversal design

- Reversal is centralized in `AccountingService`.
- The original journal entry is loaded under the current tenant context.
- Each original debit becomes a credit.
- Each original credit becomes a debit.
- The reversal entry is created with `source = "reversal"`.
- The original entry is linked to the reversal entry.
- Original posted lines are not deleted or mutated.

## Alembic revision ID

`a7c9d2e4f601`

## Model fields added

`journal_entries`:

- `reversed_entry_id`
- `reversal_entry_id`
- `reversed_at`
- `reversal_reason`

`bills`:

- `payment_reversal_journal_entry_id`

`subscriptions`:

- `payment_reversal_journal_entry_id`

## Reversal reference format

`REV-{tenant_id}-{original_journal_entry_id}`

## Idempotency behavior

Reversing the same journal entry twice returns the existing reversal entry. Bill mark-unpaid and subscription reverse-payment/mark-unpaid store `payment_reversal_journal_entry_id`, so repeated user actions do not create duplicate journal entries.

## Bill mark-unpaid behavior

If a bill has a posted `payment_journal_entry_id`, mark-unpaid creates a reversing journal entry, sets `is_paid = false`, clears `paid_at`, and keeps the original payment journal entry link for auditability.

If an old bill has no posted payment journal entry, the legacy status-only mark-unpaid path remains.

## Subscription reversal behavior

Subscriptions support both:

- `POST /subscriptions/{subscription_id}/mark-unpaid`
- `POST /subscriptions/{subscription_id}/reverse-payment`

Both routes use the same reversal path. On the first reversal, the advanced `next_billing_date` is moved back by the subscription frequency interval. Repeated reversal calls return the same reversal link and do not move the date again.

## RLS/tenant safety

All reversal paths require authenticated tenant membership, use `get_db_with_tenant_context`, filter by tenant ID, and create reversal entries under the same tenant. Cross-tenant journal reversal attempts return not found.

RLS and FORCE RLS remain active for `journal_entries`, `journal_lines`, `bills`, and `subscriptions`.

## Test results

Focused tests:

- `python -m pytest app/tests/integration/test_bills_subscriptions.py -q`: 36 passed
- `python -m pytest app/tests/integration/test_dashboard_widget.py -q`: 14 passed

Final verification:

- `python -m compileall app`: passed
- `alembic current`: `a7c9d2e4f601 (head)`
- `alembic history`: linear through `a7c9d2e4f601`
- `alembic upgrade head`: passed
- `python scripts/inspect_db.py`: passed; 42 tables, 32 RLS-enabled tables, current revision `a7c9d2e4f601`
- `python scripts/seed_default_data.py --dev`: passed; emitted the known passlib bcrypt version warning after successful seed
- `python -m pytest -q`: passed, 159 passed and 1 skipped

## Known limitations

- Reversal is limited to full-entry reversal. Partial reversal and adjustment journals remain future work.
- Bill/subscription payment history still stores one payment journal entry and one reversal journal entry.

## Recommended next card

FAM-1300 - Family Finance Module
