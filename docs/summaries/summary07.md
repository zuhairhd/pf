# Summary 07 - Card 14: ACC-503A Journal Entry Reversal Support

## What was implemented

- Added journal-entry reversal support to `AccountingService`.
- Reversals create new balanced journal entries and never delete or edit original posted lines.
- Added deterministic reversal references: `REV-{tenant_id}-{original_journal_entry_id}`.
- Added reversal metadata on `journal_entries`:
  - `reversed_entry_id`
  - `reversal_entry_id`
  - `reversed_at`
  - `reversal_reason`
- Added bill/subscription reversal links:
  - `payment_reversal_journal_entry_id`
- Bill mark-unpaid now creates a reversal entry after payment posting.
- Subscription mark-unpaid and `reverse-payment` now create a reversal entry after payment posting.
- Direct reversal API added:
  - `POST /accounts/journal-entries/{journal_entry_id}/reverse`
- Reversal calls are idempotent and repeated calls return the existing reversal entry.
- Dashboard mark-paid remains on the safe payment-posting path; no dashboard mark-unpaid action exists.

## Migration

`a7c9d2e4f601` - add journal entry reversal support.

## Tests

Added and updated accounting reversal, bill reversal, subscription reversal, API auth/error, tenant-isolation, and RLS tests.

Focused checks:

- Bills/subscriptions: 36 passed.
- Dashboard widget: 14 passed.

Final verification:

- `python -m compileall app` passed.
- `alembic current` returned `a7c9d2e4f601 (head)`.
- `alembic upgrade head` passed.
- `python scripts/inspect_db.py` passed.
- `python scripts/seed_default_data.py --dev` passed with the known passlib bcrypt version warning after successful seed.
- Full pytest run passed: 159 passed, 1 skipped.

## Known limitations

- Reversal supports full journal-entry reversal only.
- Bill/subscription payment history stores one payment journal entry and one reversal journal entry.

## Next recommended card

**FAM-1300 - Family Finance Module**
