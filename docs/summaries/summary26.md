> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 33: DB-1106A — Family Budget Dashboard Widget UI**.

# Summary 26 — Card 33: DB-1106A Family Budget Dashboard Widget UI

## What Was Done

Added a Family Budgets widget to the AI-centric dashboard, following the exact pattern already established by the commitments and family-goals widgets (DB-1104A, DB-1105A): a JSON API, an HTMX-refreshable server-rendered partial, and a permission-aware quick action. The widget shows every budget the current user is allowed to see, each with planned/actual/remaining totals, percent-used progress bars, and over-budget/near-limit badges, plus an expandable read-only category breakdown. No new budget calculation logic was written — everything reuses `FamilyBudgetService.list_visible_budgets_for_user()` and `calculate_budget_summary()` from FAM-1303.

## Key Changes

- Added `GET /dashboard/api/family-budgets`, `GET /dashboard/partials/family-budgets`, `POST /dashboard/partials/family-budgets/{id}/archive`, `GET /dashboard/partials/family-budgets/{id}/categories` in `app/routers/dashboard.py`
- Added `_build_family_budgets_dashboard()` helper composing the widget data from `FamilyBudgetService`, mirroring `_build_family_goals_dashboard()`
- Added dashboard-specific schemas (`DashboardBudgetCategoryItem`, `DashboardBudgetItem`, `FamilyBudgetsDashboardResponse`) to `app/schemas/budget.py`, kept separate from the FAM-1303 API contract
- Added two small public helpers to `FamilyBudgetService` (`get_role()`, `can_create_budget()`) — no calculation logic duplicated
- New templates: `family_budgets_widget.html`, `family_budgets_list.html`, `family_budget_card.html`, `family_budget_categories.html`
- Integrated the widget into `dashboard/index.html` alongside the existing AI Today brief, commitments, and family-goals widgets — none removed
- Archive quick action included as safe (status/is_active only, permission-gated, mirrors the family-goals widget's complete/cancel precedent); category editing intentionally left on the full `/family/budgets` page
- Added `app/tests/integration/test_dashboard_family_budgets.py` with 19 tests covering the API, HTMX partial, permissions, read-only safety (including confirming `Budget.total_actual` is never mutated by rendering), private-account-name leak prevention, and tenant/RLS isolation

## Verification

- `python -m compileall app` — OK
- `alembic current` — `07c75f53dbf6` (unchanged; no migration needed)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 44 tables, RLS active on 35
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **470 passed, 1 skipped**

## Next Recommended Card

**FAM-1304 — Allowance and Chore Tracking**
