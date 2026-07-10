# GOAL-1401A — Goal Contributions Through Accounting Engine

## Summary

Implemented optional double-entry accounting posting for family goal contributions.

When a contribution is created with `post_to_accounting: true`, a source Asset account, and a destination Asset account, the system now creates a balanced journal entry through `AccountingService` rather than only updating goal progress. Progress-only contributions continue to work exactly as before.

All posting is tenant-scoped, respects family account visibility rules, prevents duplicate journal entries for the same contribution, and never bypasses the accounting engine.

---

## Files Changed

| File | Change |
|------|--------|
| `app/models/goal.py` | Added `source_account_id`, `destination_account_id`, `journal_entry_id`, and `posting_status` columns to `GoalContribution`. |
| `app/schemas/goal.py` | Extended `GoalContributionCreate` with `source_account_id`, `destination_account_id`, and `post_to_accounting`. Extended `GoalContributionResponse` with the new accounting fields. |
| `app/services/family_goal_service.py` | Refactored `add_contribution` to validate accounts and optionally post a transfer through `AccountingService`. Added `_get_account`, `_post_contribution_to_accounting`, `get_contribution`, and `post_contribution_to_accounting` helpers. |
| `app/routers/family.py` | Updated contribution response mapping; improved error status codes; added `GET /family/goals/{goal_id}/contributions/{contribution_id}` and `POST .../post`. |
| `app/tests/integration/test_goal_contributions_accounting.py` | New test suite with 13 tests covering progress-only mode, balanced JE creation, idempotency, account validation, tenant isolation, and RLS. |
| `app/tests/integration/test_rls_child_tables.py` | Updated raw `INSERT` into `goal_contributions` to include `posting_status`. |
| `alembic/versions/33f87e4863be_add_goal_contribution_accounting_columns.py` | New migration adding the four accounting columns, indexes, and foreign keys safely. |

---

## Model / Schema Changes

`GoalContribution` gained:

- `source_account_id` — nullable FK to `accounts`
- `destination_account_id` — nullable FK to `accounts`
- `journal_entry_id` — nullable FK to `journal_entries`
- `posting_status` — `progress_only` | `pending` | `posted` | `failed`

The legacy `account_id` column is retained for backward compatibility with progress-only links.

---

## Alembic Revision

- **Revision ID:** `33f87e4863be`
- **Down revision:** `951f42580bfd`
- **Name:** `add goal contribution accounting columns`

The migration preserves existing data, adds only the new columns/indexes/FKs, and does not drop or recreate any financial tables.

---

## Contribution Accounting Rules

1. **Progress-only** (`post_to_accounting: false` or omitted):
   - Creates a `GoalContribution` record.
   - Updates `goal.current_amount`.
   - No journal entry is created.
   - Optional legacy `account_id` is validated for view access.

2. **Posted contribution** (`post_to_accounting: true`):
   - Requires both `source_account_id` and `destination_account_id`.
   - Validates both accounts exist in the current tenant.
   - Validates both accounts are **Asset** accounts.
   - Validates the user can use both accounts for posting (via `FamilyAccountAccessService`).
   - Creates a transfer journal entry through `AccountingService`:
     - **Debit:** destination account
     - **Credit:** source account
     - **Amount:** contribution amount
     - **Date:** contribution date
     - **Narration:** `Goal contribution: {goal name}`
     - **Reference:** `GOAL-{tenant_id}-{goal_id}-{contribution_id}`
   - Stores `journal_entry_id` and sets `posting_status = "posted"`.

If posting fails after the contribution record is created, the contribution remains with `posting_status = "failed"` and the goal progress still reflects the amount.

---

## Account Validation

- Source and destination accounts must belong to the current tenant (enforced by service check and RLS).
- Both must be Asset accounts.
- User must have posting permission on both accounts via `FamilyAccountAccessService.can_use_account_for_posting`.
- Cross-tenant accounts are rejected with `404` (not found in tenant context).
- Inaccessible private accounts are rejected with `403`.
- Source and destination cannot be the same account.

---

## Idempotency

- A contribution stores `journal_entry_id` once posted.
- Calling `POST /family/goals/{goal_id}/contributions/{contribution_id}/post` on an already-posted contribution returns the existing journal entry without creating a new one.
- Journal references are deterministic: `GOAL-{tenant_id}-{goal_id}-{contribution_id}`.

---

## Reversal / Cancellation Behavior

This card does **not** implement contribution reversal or editing of posted contributions.

- Posted journal entries are never deleted or mutated.
- A follow-up card is recommended:
  - **GOAL-1401B — Goal Contribution Reversal and Edit Workflow**

---

## Dashboard Behavior

- The dashboard quick-contribution form remains progress-only.
- It does not silently select source/destination accounts.
- Users who want accounting-posted contributions can use the full `POST /family/goals/{goal_id}/contributions` API with account IDs.

---

## RLS / Tenant Safety

- All routes require authentication and tenant membership via `get_db_with_tenant_context`.
- Contributions are always created within the current tenant context.
- Account lookups are scoped to the tenant; cross-tenant accounts are invisible.
- `FamilyAccountAccessService` enforces shared/private/family visibility rules.
- `goal_contributions` retains RLS + FORCE RLS.

---

## API Routes

### Modified

- `POST /family/goals/{goal_id}/contributions`  
  Now accepts `source_account_id`, `destination_account_id`, and `post_to_accounting`.

### Added

- `GET /family/goals/{goal_id}/contributions/{contribution_id}`  
  Returns a single contribution.
- `POST /family/goals/{goal_id}/contributions/{contribution_id}/post`  
  Posts (or re-fetches) the accounting journal entry for an existing contribution.

---

## Test Results

Full verification run:

- `python -m compileall app` — OK
- `alembic current` — `33f87e4863be` (head)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -v --tb=short --disable-warnings` — **226 passed, 1 skipped**

---

## Known Limitations

- Editing or reversing a posted contribution is not implemented.
- The dashboard widget does not yet expose source/destination account selection for posted contributions.
- Non-family (`/goals`) legacy contribution endpoint does not post to accounting; family goals are the supported path.

---

## Recommended Next Card

**REP-2000 — Basic Financial Reports**

With imports, bills/subscriptions, and goal contributions now flowing through the accounting engine, the next logical step is to expose reports (balance sheet, income statement, trial balance, net worth) so users can see the financial picture the ledger now contains.
