# Summary 08 - Card 15: FAM-1300 Family Finance Module Foundation

## What was implemented

- Added a tenant-scoped family finance foundation.
- Created `Family` and `FamilyMember` models with roles: `head`, `parent`, `adult`, `teen`, `child`, `viewer`.
- Added `/family`, `/family/members`, and `/family/permissions` API endpoints.
- Family creator is automatically added as the `head` member.
- Added role-based permission matrix returned by `/family/permissions`.
- Migrated `family_members` from a user-scoped table to a tenant-scoped table with `tenant_id` and `family_id`.
- Added RLS + FORCE RLS policies for `families` and `family_members`.
- Updated `app/core/rls.py` registry to include the new tenant-scoped tables.

## Migration

`417e4cf19e63` — add family finance foundation.

## Tests

- Added 14 family-specific integration tests covering creation, updates, members, roles, permissions, tenant isolation, and RLS.
- Full verification: **173 passed, 1 skipped**.

## Known limitations

- Invitation tokens exist but no invitation delivery is implemented.
- Shared/private account visibility is expressed as permission flags but not yet enforced on account/transaction endpoints.
- Allowance and chore tracking are not implemented.

## Next recommended card

**FAM-1301 — Family Account Visibility and Shared/Private Data Rules**
