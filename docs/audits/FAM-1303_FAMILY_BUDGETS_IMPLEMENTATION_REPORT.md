# FAM-1303 — Family Budgets Implementation Report

## Summary

Implemented Family Budgets: tenant/family-scoped budgets with private/shared/family visibility, role-based permissions mirroring the existing account and goal visibility patterns, budget categories linked to expense accounts, and read-only budget-vs-actual calculation from posted journal entries. The prior `Budget`/`BudgetCategory` models and the legacy `/budgets` router existed only as an untested, broken stub (the POST route referenced an undefined `request` variable and had no template); this card hardens the model, adds a proper `FamilyBudgetService`, wires new `/family/budgets/*` routes, and fixes the legacy `/budgets` router to delegate to the same safe service.

A migration adds `visibility`, `status`, `currency`, `owner_user_id`, `family_id`, and `created_by_user_id` to `budgets`, preserving all existing rows and RLS/FORCE RLS coverage. No transactions, journal entries, or account balances are created or modified by this card — budget-vs-actual figures are computed fresh on every read and never written back to the database.

---

## Files Changed

**New:**
- `alembic/versions/07c75f53dbf6_add_family_budget_visibility_and_.py` — migration.
- `app/services/family_budget_service.py` — `FamilyBudgetService` (permissions + CRUD + actuals).
- `app/tests/integration/test_family_budgets.py` — 26 new tests.
- `docs/audits/FAM-1303_FAMILY_BUDGETS_IMPLEMENTATION_REPORT.md` — this report.

**Modified:**
- `app/models/budget.py` — added `BudgetVisibility`, `BudgetStatus` enums; added `visibility`, `status`, `currency`, `owner_user_id`, `family_id`, `created_by_user_id` columns and relationships to `Budget`; made `Budget.categories` eager-load (`lazy="selectin"`) so it's safe to access in async code (fixes a latent bug also present in the pre-existing `BudgetService.get_budget_vs_actual`).
- `app/models/__init__.py` — export `BudgetVisibility`, `BudgetStatus`.
- `app/schemas/budget.py` — added `FamilyBudgetCreate`, `FamilyBudgetUpdate`, `FamilyBudgetResponse`, `BudgetCategoryUpdate`, `BudgetCategoryResponse`, `BudgetSummaryResponse`, `FamilyBudgetsListResponse`, `ActiveFamilyBudgetsSummary`; kept the legacy `BudgetCreate`/`BudgetUpdate` for backward compatibility.
- `app/routers/family.py` — added the `/family/budgets/*` route group.
- `app/routers/budgets.py` — rewritten: the old stub had a `NameError` bug (referenced `request` without declaring it) and pointed at a non-existent Jinja2 template; now both routes require auth/tenant context and delegate to `FamilyBudgetService`, returning JSON.
- `app/tests/integration/test_rls_child_tables.py` — the generic child-table RLS fixture inserted a `budgets` row via raw SQL with an explicit column list; updated to include the new NOT NULL `visibility`/`status`/`currency` columns (this is what the migration's baseline verification caught — see "Known Limitations" for why the columns are NOT NULL with no server default post-backfill).

No files were deleted.

---

## Model/Schema Changes

**Alembic revision:** `07c75f53dbf6` (down_revision `360b89eed134`)

Added to `budgets`:
- `visibility` (String(20), NOT NULL, default `'private'`, indexed) — `private` / `shared` / `family`
- `status` (String(20), NOT NULL, default `'active'`, indexed) — `active` / `archived` / `closed`
- `currency` (String(3), NOT NULL, default `'OMR'`)
- `owner_user_id` (nullable FK → `users.id`, indexed)
- `family_id` (nullable FK → `families.id`, indexed)
- `created_by_user_id` (nullable FK → `users.id`, indexed)
- Composite index `ix_budgets_tenant_period` on `(tenant_id, start_date, end_date)`

Existing columns (`name`, `period`, `start_date`, `end_date`, `total_budgeted`, `total_actual`, `is_active`) are unchanged and reused as-is — `total_budgeted` already serves as the "total planned amount" the card asked for, and `BudgetCategory.budgeted_amount` already serves as the per-category "planned amount." Renaming them was avoided since `app/services/health_score_service.py`, `app/services/ai_orchestrator.py`, and `app/ai_cfo/llm/prompts.py` all read `total_budgeted`/`total_actual`/`is_active` directly.

`BudgetCategory` was **not** changed — `remaining_amount` and `percent_used` are computed at read time (never stored), per the card's instruction to keep actuals service-derived. `BudgetCategory` already has RLS via the existing join-based child-table policy (through `budgets.tenant_id`), so no new RLS work was needed there either.

The migration backfills existing rows via `server_default` (`private`/`active`/`OMR`), then drops the server default so the ORM's Python-level defaults govern all future inserts — following the exact pattern used by the prior goal-visibility migration (`951f42580bfd`).

---

## Budget Visibility Rules

- **`private`** — visible only to `owner_user_id` (plus HEAD/PARENT, who see everything).
- **`shared`** — visible to ADULT, TEEN, VIEWER (and HEAD/PARENT); manageable only by ADULT (or HEAD/PARENT).
- **`family`** — visible to ADULT, TEEN, CHILD, VIEWER (and HEAD/PARENT); manageable only by ADULT (or HEAD/PARENT).

A tenant does not need a `Family` profile to use private budgets — role resolution (`FamilyAccountAccessService.get_role()`) already falls back to HEAD for a tenant OWNER/ADMIN and VIEWER otherwise when no `FamilyMember` record exists, exactly like account visibility. This means solo/no-family tenants can still create and use budgets (satisfying the card's explicit `family_id nullable` / `owner_user_id nullable` schema guidance), while family-aware visibility activates automatically once a family and members exist.

---

## Role Permission Matrix

| Role | View private (own) | View private (other) | View shared | View family-tier | Manage shared/family | Manage private (own) | Create shared/family | Create private |
|---|---|---|---|---|---|---|---|---|
| **head** | ✅ (all) | ✅ (all) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **parent** | ✅ (all) | ✅ (all) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **adult** | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ (own only) | ✅ | ✅ |
| **teen** | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ (own only) | ❌ | ✅ |
| **child** | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **viewer** | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

Notes:
- HEAD/PARENT are treated as "elevated" (full access), matching `FamilyAccountAccessService`/`FamilyGoalService`.
- ADULT manage rights on shared/family budgets mirror `FamilyAccountAccessService.can_manage_account` exactly (only ADULT, not TEEN, manages shared resources).
- CHILD is intentionally view-only for budgets (no create/manage at all) — stricter than `FamilyGoalService`, which lets CHILD create private goals. The card's own role spec described CHILD as "limited view only if allowed" with no mention of create/manage, so budgets treat financial planning as more sensitive than goal tracking for children.
- VIEWER is read-only everywhere, consistent with `FamilyGoalService`.

`can_user_view_budget()` and `can_user_manage_budget()` on `FamilyBudgetService` implement this table directly and are also exposed as the schema-required method names.

---

## Budget Category Behavior

- Categories link to an `account_id` that must belong to the current tenant, must have `account_type == "Expense"`, and must pass `FamilyAccountAccessService.can_view_account()` — so a private expense account another family member can't see can't be used as a budget category either.
- `create_budget_category` / `update_budget_category` / `delete_budget_category` all require `can_user_manage_budget()` on the parent budget and keep `Budget.total_budgeted` in sync (increment/decrement/net-adjust) as categories are added, edited, or removed.
- Categories with no linked account (`account_id = None`) are allowed (a manual/unlinked planning line) — their actual is always `0`.

---

## Budget vs Actual Calculation Rules

For each category, computed fresh on every call to `calculate_budget_actuals` / `calculate_budget_summary` (never persisted):

- `actual_amount` = sum of `JournalLine.debit` for the linked expense account, joined to `JournalEntry`, filtered to the current tenant and `start_date <= JournalEntry.date <= end_date`.
- `remaining_amount` = `budgeted_amount - actual_amount`.
- `percent_used` = `actual_amount / budgeted_amount * 100`, rounded to 2 decimals; if `budgeted_amount == 0`, `percent_used` is `0` when actual is also `0`, else `100` (avoids division by zero while still flagging any spend against a zero-planned category).
- `is_over_budget` = `percent_used >= 100`.
- `is_near_limit` = `alert_threshold <= percent_used < 100` (category's own `alert_threshold`, default `80`).

Budget-level summary: `total_planned`, `total_actual`, `total_remaining` (sums across categories), overall `percent_used`, `over_budget_category_ids`, `near_limit_category_ids`.

This is intentionally a pure read: unlike the pre-existing `BudgetService.get_budget_vs_actual` (which mutates and commits `budget.total_actual` as a side effect of a "get"), the new `FamilyBudgetService` methods never write to the database when computing actuals — keeping `GET /family/budgets/{id}/summary` genuinely read-only. The legacy method is left untouched for backward compatibility with the health-score/AI-orchestrator code paths that already depend on `Budget.total_actual` being periodically refreshed.

---

## Account Visibility Integration

- Category account lookups are always scoped to `Account.tenant_id == tenant_id` — a cross-tenant `account_id` returns "Account not found in this tenant" (404), never leaking whether the account exists elsewhere.
- `FamilyAccountAccessService.can_view_account()` is reused unchanged, so a private expense account owned by another family member is rejected with "You do not have access to the selected account" (403) — the same rule already enforced for goal contributions.
- Budget summaries never expose another user's private account name: `_validate_category_account_silent()` (used when building the actuals list) returns `None` for an inaccessible account rather than raising, so a category whose account became inaccessible degrades to `account_name: null` instead of leaking the name.

---

## RLS / Tenant Safety

- `budgets` already had direct tenant-scoped RLS + FORCE RLS (from the initial RLS migration); adding columns did not require touching policies.
- `budget_categories` already had join-based child-table RLS through `budgets.tenant_id` (from the child-table RLS coverage migration); unchanged.
- Verified post-migration: `SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='budgets'` → `(True, True)`.
- All new routes use `get_db_with_tenant_context` + `require_tenant_member`.
- `test_tenant_a_cannot_see_tenant_b_budgets`, `test_tenant_a_cannot_use_tenant_b_account_in_budget`, and `test_rls_active_on_budget_tables` confirm isolation and RLS status directly.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `07c75f53dbf6` (new head)
- `alembic history` — chains cleanly from `360b89eed134`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, RLS active on 35 tables; `budgets`/`budget_categories` confirmed RLS+FORCE RLS
- `python scripts/seed_default_data.py --dev` — OK (seed's existing "Monthly Household Budget" row still creates successfully with the new NOT NULL columns via ORM defaults)
- `python -m pytest -q` — **451 passed, 1 skipped** (up from the AI-1223 baseline of 425 passed, 1 skipped — 26 new tests, zero regressions)

`app/tests/integration/test_family_budgets.py` covers:
- CRUD: auth required; head/parent/adult create; viewer and child rejected (403); visibility-filtered listing; unauthorized private-budget detail rejected (403); archive requires permission.
- Categories: expense-account linking; non-expense account rejected; cross-tenant account rejected (404); inaccessible private account rejected (403).
- Actuals: computed from posted journal entries; date-range filtering excludes out-of-period entries; percent-used and over-budget detection; near-limit detection.
- Permissions: head/parent manage family budgets; adult cannot manage another adult's private budget; teen can view shared but not manage it, can manage own private; viewer is read-only.
- Tenant/RLS: cross-tenant budget and account isolation; RLS status on `budgets`/`budget_categories`.
- Regression: the fixed legacy `/budgets` router (auth-gated, delegates to the safe service, creates a private budget by default).

**One pre-existing regression was found and fixed during this work**: `test_rls_child_tables.py`'s generic child-table RLS fixture inserted a `budgets` row via raw SQL with an explicit column list that predates this migration's new NOT NULL columns. Fixed by adding `visibility`, `status`, `currency` to that INSERT statement (see "Files Changed"). All other pre-existing tests (family, family goals, family account visibility, dashboard, dashboard AI) pass unchanged.

---

## Known Limitations

- No AI budget advisor and no budget forecasting were added in this card (explicitly out of scope); the pre-existing `BudgetService.forecast_remaining_budget` is left as-is and untouched.
- Dashboard UI was intentionally not built. `FamilyBudgetService.get_active_family_budgets_summary()` returns a lightweight aggregate (active budget count, totals, over-budget/near-limit counts) specifically for a future dashboard widget — documented as follow-up **DB-1106A — Family Budget Dashboard Widget UI**, matching the pattern already used for the commitments and family-goals widgets and the AI-1223 dashboard.
- `BudgetAlert` (the pre-existing alert-persistence model) is not used by the new service; over-budget/near-limit detection is computed on read, consistent with how Proactive Alerts already does preview-only detection without forced persistence.
- The legacy `/budgets` POST/GET routes now require authentication (they previously had none, and were non-functional). Since no template existed and the POST route had a `NameError` bug, there were no working prior clients to break.

---

## Recommended Next Card

**DB-1106A — Family Budget Dashboard Widget UI**

With family budgets now modeled, permissioned, and summarized via `get_active_family_budgets_summary()`, the natural next step is surfacing that summary on the AI-centric dashboard (AI-1223) alongside the existing commitments and family-goals widgets — showing active budget count, over-budget/near-limit alerts, and a quick link into `/family/budgets`.
