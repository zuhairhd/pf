# Summary 09 - Card 16: FAM-1301 Family Account Visibility and Shared/Private Data Rules

## What was implemented

- Extended the `Account` model with `visibility` (`private`/`shared`/`family`), `owner_user_id`, and `family_id`.
- Added Alembic migration `00255deeb189` to add the columns and indexes safely.
- Created `FamilyAccountAccessService` enforcing family role-based rules:
  - `head`/`parent` can view/manage all accounts.
  - `adult` can view/manage shared/family accounts and their own private accounts.
  - `teen`/`child` can view shared/family/own accounts; management limited to own private accounts.
  - `viewer` is read-only for shared/family accounts.
- Updated `/accounts/*` routes to filter list/detail by visibility and added visibility/owner endpoints.
- Added `/family/accounts/visible`, `/family/accounts/{id}/share`, and `/family/accounts/{id}/make-private`.
- Protected bill/subscription `mark_paid` and CSV import `confirm` against accounts the user cannot use.
- Fixed JSONB mutation persistence when import rows are skipped due to permission errors.
- Fixed UTC date handling in `CostController.get_daily_usage` to avoid timezone-related test flakiness.

## Migration

`00255deeb189` — add account visibility and ownership columns.

## Tests

- Added 11 family-account-visibility integration tests.
- Full verification: **184 passed, 1 skipped**.

## Known limitations

- `family` visibility is treated the same as `shared` in this iteration.
- Account visibility is account-level; transaction-level privacy is not implemented.
- Family member activation still requires a manual `PATCH`.

## Next recommended card

**FAM-1302 — Family Goals**
