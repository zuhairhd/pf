# FAM-1301 — Family Account Visibility and Shared/Private Data Rules

## Summary

Implemented account-level visibility controls and family role-based access rules for the Financial Life MVP. Accounts now support `private`, `shared`, and `family` visibility, an optional `owner_user_id`, and an optional `family_id`. A new `FamilyAccountAccessService` enforces who can view, manage, and post transactions against each account. Bill, subscription, and import confirmation flows now reject payment/bank/expense accounts the user is not allowed to use. All changes preserve RLS + FORCE RLS and tenant isolation.

## Files Changed

- `app/models/accounting.py` — added `AccountVisibility` enum, `visibility`, `owner_user_id`, `family_id` columns, indexes, and relationships.
- `app/schemas/accounting.py` — added visibility/owner fields to `AccountCreate`/`AccountUpdate`, plus `AccountVisibilityUpdate`, `AccountOwnerUpdate`, and `AccountResponse`.
- `app/services/family_account_access_service.py` — new service with role-based view/manage/post rules.
- `app/services/accounting_service.py` — `create_account` now stores visibility/owner/family fields.
- `app/routers/accounts.py` — filtered list/detail by visibility, added `GET /accounts/{id}`, `PATCH /accounts/{id}`, `PATCH /accounts/{id}/visibility`, `PATCH /accounts/{id}/owner`.
- `app/routers/family.py` — added `GET /family/accounts/visible`, `POST /family/accounts/{id}/share`, `POST /family/accounts/{id}/make-private`.
- `app/services/bill_subscription_service.py` — `mark_paid` now validates account access for bills and subscriptions.
- `app/routers/bills.py`, `app/routers/subscriptions.py`, `app/routers/dashboard.py` — pass current user to `mark_paid`.
- `app/imports/services.py` — `confirm_job` and `_create_journal_entry_for_row` now validate that the user can use the selected bank and category accounts; fixed JSONB mutation persistence for skipped-row errors.
- `app/imports/routes.py` — pass user to `confirm_job`.
- `app/ai_cfo/llm/cost_control.py` — use UTC date for daily usage window (pre-existing timezone fix).
- `app/tests/helpers.py` — added `create_test_account` and `create_test_family_member` helpers.
- `app/tests/integration/test_family_account_visibility.py` — new 16-test suite covering visibility rules, management permissions, posting/import safety, tenant isolation, and RLS.
- `alembic/versions/00255deeb189_add_account_visibility_and_ownership_.py` — migration.

## Data Model Changes

Added to `accounts`:

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `visibility` | `String(20)` | No | `private` | `private` / `shared` / `family` |
| `owner_user_id` | `Integer` (FK → users.id) | Yes | — | Owner for private accounts |
| `family_id` | `Integer` (FK → families.id) | Yes | — | Optional family grouping |

Indexes added:
- `ix_accounts_visibility`
- `ix_accounts_owner_user_id`
- `ix_accounts_family_id`
- `ix_accounts_tenant_visibility`
- `ix_accounts_tenant_owner`

Existing rows were migrated with `visibility = 'private'`.

## Alembic Revision

`00255deeb189` — add account visibility and ownership columns.

Down revision: `417e4cf19e63`.

## Family Account Visibility Rules

| Visibility | Meaning |
|------------|---------|
| `private` | Visible to the owner, head, parent, and tenant admins/owners only. |
| `shared` | Visible to all active family members. Manageable by head/parent/adult. |
| `family` | Visible to all active family members (stronger semantic; same access as `shared` in this iteration). |

## Role Permission Matrix for Accounts

| Role | View | Manage / Post |
|------|------|---------------|
| `head` | All accounts | All accounts |
| `parent` | All accounts | All accounts |
| `adult` | Shared/family + own private | Shared/family + own private |
| `teen` | Shared/family + own private | Own private only (no management of shared/family) |
| `child` | Shared/family + own private | Own private only |
| `viewer` | Shared/family | Read-only; cannot manage or post |
| Tenant owner/admin (no family record) | All accounts | All accounts |

## Routes Added/Updated

### Accounts router (`/accounts/*`)

- `GET /accounts/` — HTML list filtered by visibility.
- `POST /accounts/` — create account with optional visibility/owner.
- `GET /accounts/{account_id}` — detail if viewable.
- `PATCH /accounts/{account_id}` — update basic fields if manageable.
- `PATCH /accounts/{account_id}/visibility` — change visibility.
- `PATCH /accounts/{account_id}/owner` — change owner.
- `POST /accounts/journal-entries/{journal_entry_id}/reverse` — unchanged.

### Family router (`/family/*`)

- `GET /family/accounts/visible` — JSON list of accounts the current user can see.
- `POST /family/accounts/{account_id}/share` — set visibility to `shared`.
- `POST /family/accounts/{account_id}/make-private` — set visibility to `private`; assigns current user as owner if unset.

## Posting / Import Account-Access Behavior

- `POST /bills/{id}/mark-paid` rejects payment or expense accounts the user cannot use.
- `POST /subscriptions/{id}/mark-paid` rejects payment or expense accounts the user cannot use.
- `POST /imports/{job_id}/confirm` skips rows that reference accounts the user cannot use and records a permission error on the row.
- Dashboard `POST /dashboard/partials/bills/{id}/mark-paid` uses the same safe service path.

## RLS / Tenant Safety

- RLS and FORCE RLS remain enabled on `accounts` and all other tenant tables.
- The migration only alters `accounts`; no table drops or recreations.
- Cross-tenant access is blocked by RLS plus explicit tenant filtering in services.
- Family visibility rules never allow one tenant's members to see another tenant's accounts.

## Test Results

```
python -m pytest -q
184 passed, 1 skipped
```

New tests added in `app/tests/integration/test_family_account_visibility.py`:

- Head and parent can see all family accounts.
- Adult sees shared/family + own private only.
- Adult cannot see another adult's private account.
- Teen/child/viewer visibility boundaries.
- Account detail rejects unauthorized private account.
- Sharing / making private requires manage permission.
- Unauthorized member cannot change visibility.
- Bill mark-paid rejects inaccessible payment account.
- Subscription mark-paid rejects inaccessible payment account.
- CSV import confirm skips rows referencing inaccessible bank account.
- Tenant A cannot see Tenant B accounts.
- RLS active on `accounts`.

## Known Limitations

- `family` visibility is treated the same as `shared` in this iteration; a future card may differentiate them (e.g., family-wide mandatory visibility vs. opt-in shared).
- Transaction-level privacy is not implemented; visibility is account-level only.
- Family member invitation and activation still require a manual `PATCH /family/members/{id}` to set `is_active=true`.
- Allowance and chore tracking are not part of this card.

## Recommended Next Card

**FAM-1302 — Family Goals**

Family visibility rules are now enforced on accounts. The next logical step is to extend family scoping to goals so family members can collaborate on shared savings/goals while keeping private goals isolated.
