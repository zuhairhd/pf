# FAM-1302 — Family Goals Implementation Report

## Summary

Implemented family-scoped goals with shared/private visibility, role-based access control, contributions, and progress tracking. Goals can be owned by a family member, shared with the whole family, or kept private. Contributions update goal progress and can optionally reference an account, with account access validated through the existing family account visibility service. All data remains tenant-scoped and RLS-enforced.

---

## Files Changed

### Models
- `app/models/goal.py`
  - Added `GoalVisibility` enum (`private` / `shared` / `family`).
  - Added `visibility`, `owner_user_id`, and `family_id` columns to `goals`.
  - Added `tenant_id`, `contributed_by_user_id`, and `account_id` to `goal_contributions`.
  - Added relationships (`owner`, `family`, `contributor`, `account`).
- `app/models/__init__.py`
  - Exported `GoalVisibility`.

### Schemas
- `app/schemas/goal.py`
  - Added `FamilyGoalCreate`, `FamilyGoalUpdate`.
  - Added `GoalResponse`, `GoalContributionResponse`, `GoalProgressResponse`.
  - Extended `GoalContributionCreate` with optional `account_id`.
- `app/schemas/__init__.py`
  - Exported new goal schemas.

### Service
- `app/services/family_goal_service.py` (new)
  - `FamilyGoalService` with role-based permission helpers.
  - Goal CRUD, cancel/complete, contributions, progress, and dashboard summary.
- `app/services/__init__.py`
  - Exported `FamilyGoalService`.

### Routes
- `app/routers/family.py`
  - Added `/family/goals` (POST, GET).
  - Added `/family/goals/{goal_id}` (GET, PATCH).
  - Added `/family/goals/{goal_id}/cancel` (POST).
  - Added `/family/goals/{goal_id}/complete` (POST).
  - Added `/family/goals/{goal_id}/contributions` (POST, GET).
  - Added `/family/goals/{goal_id}/progress` (GET).

### Migration
- `alembic/versions/951f42580bfd_add_family_goal_visibility_and_.py`
  - Added `visibility`, `owner_user_id`, `family_id` to `goals`.
  - Added `tenant_id`, `contributed_by_user_id`, `account_id` to `goal_contributions`.
  - Created indexes and foreign keys.
  - Backfilled `tenant_id` from parent goals.

### Tests
- `app/tests/integration/test_family_goals.py` (new)
  - 17 integration tests covering auth, creation, visibility rules, role permissions, contributions, progress, account-access checks, tenant isolation, and RLS.
- `app/tests/integration/test_rls_child_tables.py`
  - Updated raw `INSERT` statements for `goals` and `goal_contributions` to include new required columns.

---

## Data Model Changes

| Table | Change |
|-------|--------|
| `goals` | Added `visibility` (string, not null, default `private`), `owner_user_id` (FK → users, nullable), `family_id` (FK → families, nullable). |
| `goal_contributions` | Added `tenant_id` (not null), `contributed_by_user_id` (FK → users, nullable), `account_id` (FK → accounts, nullable). |

Existing rows were migrated safely: `goals.visibility` defaulted to `private`; `goal_contributions.tenant_id` was backfilled from the parent goal.

---

## Alembic Revision ID

`951f42580bfd` — `add family goal visibility and contribution ownership`

---

## Goal Visibility Rules

| Visibility | Meaning |
|------------|---------|
| `private` | Visible only to the owner, head, and parent. |
| `shared` | Visible to all active family members. |
| `family` | Visible to all active family members (semantic alias for shared; can be refined later). |

All goals are still scoped to a single tenant and family. Cross-tenant access is blocked by service filters and PostgreSQL RLS.

---

## Role Permission Matrix

| Role | View | Manage | Contribute |
|------|------|--------|------------|
| `head` | All goals | All goals | All goals |
| `parent` | All goals | All goals | All goals |
| `adult` | Shared/family + own private | Shared/family + own private | Shared/family + own private |
| `teen` | Shared/family | No | Shared/family |
| `child` | Family + own private | Own private only | Own private only |
| `viewer` | Shared/family | No | No |

Tenant owners/admins without a family member record are treated as `head`.

---

## Routes Added

All routes require authentication and tenant membership via `require_tenant_member` and `get_db_with_tenant_context`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/family/goals` | Create a family goal. |
| GET | `/family/goals` | List goals visible to the current user. |
| GET | `/family/goals/{goal_id}` | Get a single goal. |
| PATCH | `/family/goals/{goal_id}` | Update a goal. |
| POST | `/family/goals/{goal_id}/cancel` | Cancel a goal. |
| POST | `/family/goals/{goal_id}/complete` | Mark a goal completed. |
| POST | `/family/goals/{goal_id}/contributions` | Add a contribution. |
| GET | `/family/goals/{goal_id}/contributions` | List contributions. |
| GET | `/family/goals/{goal_id}/progress` | Get progress details. |

---

## Contribution Behavior

- Contributions increase `goal.current_amount`.
- When `current_amount >= target_amount`, status is set to `completed` automatically.
- Optional `account_id` is validated: the account must exist in the tenant and the user must be able to view it.
- Contribution records store `contributed_by_user_id` and `tenant_id`.
- No accounting entries are created from contributions in this card.

---

## Account-Access Checks

`FamilyAccountAccessService.can_view_account` is reused to validate the optional `account_id` on contributions. A user cannot link a contribution to a private account they cannot see.

---

## RLS / Tenant Safety

- `goals` already had `tenant_id` and RLS; the migration only added columns/indexes/FKs.
- `goal_contributions` already had child-table RLS via the parent `goals` relationship; the migration added `tenant_id` for consistency.
- Service-level filters ensure users only see goals allowed by family visibility rules.
- Tests verify `assert_rls_enabled(db, "goals")` and `assert_rls_enabled(db, "goal_contributions")`.

---

## Test Results

```text
app/tests/integration/test_family_goals.py: 17 passed
Full suite: 200 passed, 1 skipped
```

Coverage includes:
- Auth requirements
- Head/parent/adult/teen/child/viewer role behavior
- Private goal isolation between adults
- Shared/family visibility
- Contribution progress and auto-completion
- Inaccessible account rejection
- Tenant isolation
- RLS active on goal tables

---

## Known Limitations

- Goal contributions do not yet create accounting entries (deferred to GOAL-1401A).
- `family` visibility is currently treated equivalently to `shared`; refined semantics can be added later.
- Family member activation currently requires a separate PATCH; invitation flow is still deferred to AUTH-305.
- No dedicated family goals dashboard widget UI yet (deferred to DB-1105A).

---

## Recommended Next Card

**DB-1105A — Family Goals Dashboard Widget UI**

Surface active family goals, progress percentages, and upcoming target dates on the main dashboard. Reuse the `/family/goals` API and existing dashboard partial/HTMX patterns.
