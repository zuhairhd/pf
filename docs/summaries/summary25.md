> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 32: FAM-1303 — Family Budgets**.

# Summary 25 — Card 32: FAM-1303 Family Budgets

## What Was Done

Implemented Family Budgets: tenant/family-scoped budgets with private/shared/family visibility and role-based permissions matching the existing account and goal visibility patterns, budget categories linked to expense accounts, and read-only budget-vs-actual calculation from posted journal entries. The prior `Budget`/`BudgetCategory` models and `/budgets` router existed only as an untested, broken stub (a `NameError` bug, no template) — this card hardens the model, adds a real permission-aware service, and fixes the legacy router.

## Key Changes

- Migration `07c75f53dbf6` adds `visibility`, `status`, `currency`, `owner_user_id`, `family_id`, `created_by_user_id` to `budgets` (existing rows preserved via backfilled defaults, RLS/FORCE RLS untouched since `budgets` and `budget_categories` already had coverage).
- Added `app/services/family_budget_service.py` (`FamilyBudgetService`):
  - Role resolution delegated to `FamilyAccountAccessService` (works with or without a Family profile, unlike the stricter goal service)
  - Permission matrix: HEAD/PARENT full access; ADULT manages shared/family + own private; TEEN views shared/family + manages own private; CHILD view-only (family-tier + own private, no create/manage); VIEWER read-only
  - Budget categories validated against tenant, `account_type == "Expense"`, and account visibility (private accounts owned by other family members are rejected)
  - Budget-vs-actual computed fresh from posted `JournalLine`/`JournalEntry` data on every read — never persisted, unlike the pre-existing `BudgetService.get_budget_vs_actual` which mutates `total_actual` as a side effect
  - `get_active_family_budgets_summary()` added specifically for a future dashboard widget (DB-1106A)
- Added `/family/budgets/*` routes (create/list/get/update/archive/summary + category CRUD) in `app/routers/family.py`
- Rewrote `app/routers/budgets.py`: fixed the `NameError` bug, added auth/tenant guards, delegates to `FamilyBudgetService`
- Added `app/tests/integration/test_family_budgets.py` with 26 tests covering CRUD, categories, actuals, permissions, and tenant/RLS isolation
- **Found and fixed a regression**: `test_rls_child_tables.py`'s generic RLS fixture inserted a `budgets` row via raw SQL with an explicit column list that predated the new NOT NULL columns; updated the INSERT to include `visibility`/`status`/`currency`

## Verification

- `python -m compileall app` — OK
- `alembic current` — `07c75f53dbf6` (new head)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, RLS active on `budgets`/`budget_categories`
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **451 passed, 1 skipped**

## Next Recommended Card

**DB-1106A — Family Budget Dashboard Widget UI**
