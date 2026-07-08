# FAM-1300 — Family Finance Module Foundation Implementation Report

## Summary

Implemented the foundation of the Family Finance module. Each tenant can now create one family profile, add family members with roles (head, parent, adult, teen, child, viewer), and retrieve permission flags based on those roles. All family data is tenant-scoped and protected by PostgreSQL Row-Level Security (RLS) with FORCE RLS.

## Files Changed

- `app/models/family.py` — new `Family` and `FamilyMember` models, `FamilyRole` enum.
- `app/models/user.py` — removed the old `FamilyMember` class (moved to `app/models/family.py`); kept the `family_members` relationship via string reference.
- `app/models/__init__.py` — updated imports to expose `Family`, `FamilyMember`, and `FamilyRole` from `app.models.family`.
- `app/schemas/family.py` — new Pydantic schemas for family, family members, and permissions.
- `app/services/family_service.py` — new `FamilyService` with CRUD, role-based permissions, and family-head auto-creation.
- `app/routers/family.py` — new `/family/*` API routes.
- `app/main.py` — registered the family router.
- `app/core/rls.py` — moved `family_members` from `GLOBAL_TABLES` to `TENANT_SCOPED_TABLES`; added `families` to `TENANT_SCOPED_TABLES`.
- `alembic/env.py` — updated model imports for autogenerate.
- `alembic/versions/417e4cf19e63_add_family_finance_foundation.py` — migration for new tables, columns, RLS policies.
- `app/tests/integration/test_family.py` — 14 new integration tests.

## Models Added

### `Family`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK |
| tenant_id | Integer | FK → organizations.id, unique (one family per tenant) |
| name | String(200) | Family/household name |
| currency | String(3) | Default OMR |

### `FamilyMember`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK |
| family_id | Integer | FK → families.id |
| tenant_id | Integer | FK → organizations.id |
| user_id | Integer | FK → users.id, nullable until invitation accepted |
| email | String(255) | Member email |
| first_name | String(100) | |
| last_name | String(100) | |
| relationship_type | String(50) | e.g. spouse, child, parent, self |
| role | String(20) | head, parent, adult, teen, child, viewer |
| invitation_token | String(255) | Optional invitation token |
| invitation_sent_at | DateTime | |
| invitation_accepted_at | DateTime | |
| is_active | Boolean | |

## Alembic Revision

`417e4cf19e63` — `add family finance foundation`

The migration:
- Creates the `families` table.
- Adds `family_id` and `tenant_id` to `family_members`.
- Makes `family_members.user_id` nullable.
- Converts `family_members.role` from the old `userrole` enum to a `String(20)`.
- Backfills `family_id`/`tenant_id` for any existing rows.
- Creates indexes and foreign keys.
- Enables RLS + FORCE RLS and adds tenant-scoped policies for both tables.

## Routes Added

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/family` | Create family profile |
| GET | `/family` | Get family profile |
| PATCH | `/family` | Update family profile (requires `can_edit_family`) |
| POST | `/family/members` | Add family member (requires `can_manage_members`) |
| GET | `/family/members` | List family members |
| PATCH | `/family/members/{member_id}` | Update family member (requires `can_manage_members`) |
| DELETE | `/family/members/{member_id}` | Remove family member (requires `can_manage_members`) |
| GET | `/family/permissions` | Return current user's role and permission flags |

## Family Roles and Permissions

Roles: `head`, `parent`, `adult`, `teen`, `child`, `viewer`.

Permission flags returned by `GET /family/permissions`:

- `can_view_family`
- `can_edit_family`
- `can_manage_members`
- `can_view_accounts`
- `can_edit_transactions`
- `can_view_reports`
- `can_approve_purchases`

Heads have all permissions. Parents can manage members and edit. Adults can view/edit transactions and reports. Teens can view accounts. Children can view the family. Viewers have read-only access to the family profile.

The creator of the family is automatically added as a member with role `head`.

## RLS / Tenant Isolation

- `families` and `family_members` are now in `TENANT_SCOPED_TABLES`.
- Both tables have `tenant_id` and RLS policies using `app.current_tenant_id`.
- FORCE RLS is enabled.
- Tests verify cross-tenant invisibility and that RLS is active on both tables.

## Test Results

- New family integration tests: 14 passed.
- Full suite: **173 passed, 1 skipped, 3 warnings**.

## Known Limitations

- Invitation tokens are stored but no email/SMS invitation delivery is implemented yet.
- Shared/private account visibility rules are expressed as permission flags but not yet enforced against account/transaction endpoints.
- Allowance, chore tracking, and mobile UI are not implemented.

## Recommended Next Card

**FAM-1301 — Family Account Visibility and Shared/Private Data Rules**

Wire the permission matrix into account and transaction reads so that teen/child/viewer scopes are enforced, and allow marking specific accounts as shared or private per family member.
