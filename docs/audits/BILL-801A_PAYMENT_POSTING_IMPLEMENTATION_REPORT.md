# BILL-801A Payment Posting Implementation Report

## Summary

Implemented bill and subscription mark-paid posting through the existing `AccountingService`. Mark-paid now creates balanced double-entry journal entries, validates tenant-owned payment and expense accounts, stores `payment_journal_entry_id`, and prevents duplicate postings on repeated API or dashboard clicks.

## Files Changed

- `app/models/subscription.py`
- `app/schemas/accounting.py`
- `app/schemas/bill_subscription.py`
- `app/services/accounting_service.py`
- `app/services/bill_subscription_service.py`
- `app/routers/bills.py`
- `app/routers/subscriptions.py`
- `app/routers/dashboard.py`
- `app/templates/dashboard/partials/commitments_widget.html`
- `app/tests/integration/test_bills_subscriptions.py`
- `app/tests/integration/test_dashboard_widget.py`
- `alembic/versions/89f59125ee5e_add_payment_posting_columns_to_bills_.py`

## Payment Posting Rules

- Bills debit an Expense account and credit an Asset payment account.
- Subscriptions debit an Expense account and credit an Asset payment account.
- Both accounts must belong to the current tenant.
- Payment accounts must have `account_type == "Asset"`.
- Expense accounts must have `account_type == "Expense"`.
- Missing accounts are rejected with a clear `400` response.
- Journal entries are created only through `AccountingService.create_journal_entry`.
- References are deterministic and tenant-aware:
  - Bills: `BILL-{tenant_id}-{bill_id}`
  - Subscriptions: `SUB-{tenant_id}-{subscription_id}`

## API Changes

`POST /bills/{bill_id}/mark-paid` and `POST /subscriptions/{subscription_id}/mark-paid` accept:

- `payment_date`
- `payment_account_id`
- `expense_account_id`
- `notes`

Responses now include payment posting fields:

- `payment_journal_entry_id`
- `journal_entry_id`
- `debit_account_id`
- `credit_account_id`
- `payment_amount`
- `currency`

`POST /subscriptions/{subscription_id}/mark-unpaid` was added to safely block reversal attempts when a payment journal entry exists.

## Alembic Revision

- Revision ID: `89f59125ee5e`
- Purpose: add nullable payment posting columns to `bills` and `subscriptions`.

## payment_journal_entry_id

Added to both `bills` and `subscriptions` as nullable foreign keys to `journal_entries`.

Also added:

- `payment_account_id`
- `expense_account_id`

## Idempotency Behavior

If `payment_journal_entry_id` is already set, mark-paid returns the existing payment info and does not create another journal entry. Subscription mark-paid also avoids advancing `next_billing_date` again on repeated calls.

## Mark-Unpaid / Reversal Behavior

Bills and subscriptions with posted payment journal entries cannot be marked unpaid because journal-entry reversal support does not exist yet. The operation returns a clear `400` error and does not delete or alter the posted journal entry.

Follow-up: `ACC-503A - Journal Entry Reversal Support`.

## Dashboard Integration

The dashboard bill quick action uses the same `BillService.mark_paid` path. If a bill has configured payment and expense accounts, the widget refreshes after posting. If accounts are missing, the widget returns a clear warning telling the user to choose payment and expense accounts before marking paid. Repeated dashboard clicks do not duplicate journal entries.

## RLS / Tenant Safety

All routes continue to require authenticated tenant membership and use `get_db_with_tenant_context`. Services verify the bill/subscription and account rows belong to the current tenant before posting. Cross-tenant bill/subscription payment attempts return `404`; cross-tenant account IDs return `400` without posting.

RLS and FORCE RLS remain active.

## Test Results

Focused verification:

- `python -m pytest app/tests/integration/test_bills_subscriptions.py -q` - 33 passed
- `python -m pytest app/tests/integration/test_dashboard_widget.py -q` - 14 passed

Final verification:

- `python -m compileall app` - passed
- `alembic current` - `89f59125ee5e (head)`
- `alembic history` - linear through `89f59125ee5e`
- `alembic upgrade head` - passed
- `python scripts/inspect_db.py` - passed, 42 tables, 32 RLS-enabled, current revision `89f59125ee5e`
- `python scripts/seed_default_data.py --dev` - passed, idempotent
- `python -m pytest -q` - passed
- `python -m pytest --collect-only -q` - 157 tests collected

Result: 156 passed, 1 skipped.

## Known Limitations

- Journal-entry reversal is not implemented.
- Each subscription currently stores one `payment_journal_entry_id`; recurring multi-period payment history needs a future payment ledger or renewal-instance model.
- The dashboard quick action can only post when payment and expense accounts are already configured on the bill.

## Recommended Next Card

`ACC-503A - Journal Entry Reversal Support`
