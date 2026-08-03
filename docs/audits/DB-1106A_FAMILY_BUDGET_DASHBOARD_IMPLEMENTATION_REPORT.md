# DB-1106A — Family Budget Dashboard Widget UI Implementation Report

## Summary

Added a Family Budgets widget to the AI-centric dashboard (AI-1223), following the same pattern established by the commitments and family-goals widgets: a JSON API for programmatic clients, an HTMX-refreshable server-rendered partial for the dashboard page, and a permission-aware quick action (archive). The widget shows every budget the current user is allowed to see (per `FamilyBudgetService`'s private/shared/family visibility rules), each with planned/actual/remaining totals, percent-used, and over-budget/near-limit badges, plus an expandable read-only category breakdown. No new budget calculation logic was written — everything is composed from `FamilyBudgetService.list_visible_budgets_for_user()` and `calculate_budget_summary()`, exactly as FAM-1303 anticipated.

No database schema changes were needed. Alembic head remains `07c75f53dbf6`.

---

## Files Changed

**New:**
- `app/templates/dashboard/partials/family_budgets_widget.html` — widget wrapper (summary cards, over-budget/near-limit badges, list, footer).
- `app/templates/dashboard/partials/family_budgets_list.html` — budget list / empty state.
- `app/templates/dashboard/partials/family_budget_card.html` — single budget card (progress bar, badges, quick actions).
- `app/templates/dashboard/partials/family_budget_categories.html` — expandable read-only category breakdown table.
- `app/tests/integration/test_dashboard_family_budgets.py` — 19 new tests.

**Modified:**
- `app/routers/dashboard.py` — added `_build_family_budgets_dashboard()`, `GET /api/family-budgets`, `GET /partials/family-budgets`, `POST /partials/family-budgets/{id}/archive`, `GET /partials/family-budgets/{id}/categories`; main `/` route now also builds and passes `family_budgets` context.
- `app/templates/dashboard/index.html` — added the family budgets widget include, directly after the family goals widget; no existing section was removed.
- `app/schemas/budget.py` — added dashboard-specific schemas: `DashboardBudgetCategoryItem`, `DashboardBudgetItem`, `FamilyBudgetsDashboardResponse` (kept separate from the FAM-1303 `BudgetCategoryResponse`/`FamilyBudgetResponse` so the existing `/family/budgets/*` API contract is untouched).
- `app/services/family_budget_service.py` — added two small public helpers used by the dashboard: `get_role()` (public wrapper around the existing role resolution) and `can_create_budget(visibility)` (reuses the existing `_can_create` permission logic). No budget-vs-actual calculation logic was duplicated or changed.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/dashboard/api/family-budgets` | *(new)* UI-ready JSON: visible budgets (with categories), active-budget totals, over-budget/near-limit counts, permissions. |
| GET | `/dashboard/partials/family-budgets` | *(new)* HTMX partial rendering the widget for the current user/tenant. |
| POST | `/dashboard/partials/family-budgets/{budget_id}/archive` | *(new)* Permission-checked quick action; archives the budget (status/is_active only) and returns the refreshed widget. |
| GET | `/dashboard/partials/family-budgets/{budget_id}/categories` | *(new)* HTMX partial for the read-only, expandable category breakdown of one budget. |
| GET | `/dashboard/` | *(updated)* Main dashboard page now also builds and renders `family_budgets`. |

All routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other dashboard route.

---

## Templates Added / Updated

See "Files Changed." `index.html` keeps its existing `ai_today.html`, `commitments_widget.html`, and `family_goals_widget.html` includes exactly as before — the new widget was appended, not substituted.

---

## Dashboard Widget Sections

1. **Summary cards** — Active Budgets count, Planned total, Actual total, Avg % Used (across active budgets only).
2. **Over-budget / near-limit badges** — shown only when counts are non-zero.
3. **Budget list** — one card per visible budget: name, visibility badge (private/shared/family), status badge (active/archived/closed), period dates, progress bar (color-coded: red if over budget, yellow if near limit, primary otherwise), remaining amount, and quick actions.
4. **Category breakdown (expandable)** — clicking "Categories (N)" on a card fetches a read-only table (planned/actual/remaining/percent, over/near-limit badges) via HTMX without navigating away.
5. **Footer** — total remaining across active budgets.
6. **Empty state** — "No budgets yet" with a create link (if the user can create) or "No budgets are visible to you" (if not).
7. **Error state** — if the widget's data fails to build for any reason, a safe "Budgets are temporarily unavailable" message renders instead of a 500 error.

---

## HTMX Behavior

- **Refresh**: the widget's refresh button (`hx-get="/dashboard/partials/family-budgets"`, `hx-target="#family-budgets-widget"`, `hx-swap="outerHTML"`) re-fetches and swaps the whole widget in place, matching the commitments/family-goals widgets exactly.
- **Category expand**: each budget card's "Categories" button (`hx-get=".../categories"`, `hx-target="#budget-categories-{id}"`, `hx-swap="innerHTML"`) loads the breakdown into a per-card placeholder div without touching the rest of the widget.
- **Archive quick action**: included as safe, since it only mutates `Budget.status`/`is_active` (no transactions, journal entries, or account balances), is gated by `require_tenant_member` + `FamilyBudgetService.can_user_manage_budget()`, and mirrors the precedent already set by the family-goals widget's complete/cancel quick actions. The button only renders when `budget.can_manage` is true and `budget.status == "active"`, and the action requires an `hx-confirm` prompt.
- Editing budget categories was intentionally **not** added inline — cards link to `/family/budgets` for full editing, per the card's explicit "prefer linking to the full budget page" instruction.

---

## Empty States

- **No family profile**: `FamilyBudgetService` already works without a `Family` row (role resolution falls back to tenant OWNER/ADMIN → HEAD, else VIEWER), so the widget renders normally — private budgets remain usable, shared/family-visibility budgets simply have no family members to be visible to yet.
- **Family exists but no budgets**: "No budgets yet. Create a private, shared, or family budget to start tracking spending." (with a create link, if permitted).
- **User has no visible budgets**: "No budgets are visible to you right now." (no create link if the role can't create).
- **No budget categories**: the "Categories (N)" button is only shown when `N > 0`; the categories partial itself shows "No categories on this budget yet." if reached with zero categories.
- **Service/API error**: `_build_family_budgets_dashboard()` is wrapped in `try/except` at both the page and HTMX-partial call sites; on failure, `family_budgets` is `None` and the widget renders "Budgets are temporarily unavailable" instead of raising.
- **Unauthenticated user**: `GET /dashboard/api/family-budgets` and `GET /dashboard/partials/family-budgets` both return 401/403 via `require_tenant_member`.

---

## Permission Behavior

Reuses `FamilyBudgetService` unchanged (no new permission logic):
- **HEAD/PARENT** see and can manage every budget in the tenant.
- **ADULT** sees shared/family budgets plus their own private budgets; cannot see another adult's private budget; can manage shared/family budgets and their own private ones.
- **TEEN** sees shared/family budgets (view-only) plus their own private budgets (manageable); cannot manage shared/family budgets.
- **CHILD** sees family-tier budgets and their own private budgets only, with no manage rights at all (budgets are stricter than goals here, per FAM-1303's design).
- **VIEWER** sees shared/family budgets read-only; the archive button never renders for a viewer (`can_manage` is always `False`), and the API's `permissions.can_create_budget` is `False`.
- Verified by `test_head_sees_all_family_budgets`, `test_adult_sees_shared_family_and_own_private_only`, `test_viewer_sees_read_only_budget_no_manage_action`, and `test_manage_action_appears_only_when_can_manage`.

---

## Budget-vs-Actual Behavior

Identical to FAM-1303 — the dashboard adds no new calculation:
- `calculate_budget_summary()` computes `actual_amount` per category as the sum of posted `JournalLine.debit` for the linked expense account, filtered to the budget's `start_date`–`end_date` range and the current tenant.
- `remaining_amount = planned - actual`; `percent_used` safely returns `0` (not an error) when `planned_amount == 0` and there's no actual spend, or `100` if there's any spend against a zero-planned category.
- `is_over_budget` = `percent_used >= 100`; `is_near_limit` = category's own `alert_threshold <= percent_used < 100`.
- All of this is computed fresh on every dashboard request and **never written back to the database** — verified by `test_dashboard_widget_does_not_mutate_budget_actual_field`, which posts a journal entry, renders the widget (which computes `actual=30` in memory), then confirms `Budget.total_actual` in the database is still `0` (the legacy, separately-updated field FAM-1303 documented as untouched by the new read-only path).

---

## Read-Only Safety

- `test_dashboard_widget_creates_no_financial_records` confirms Account/Goal/JournalEntry/Budget/Notification row counts are unchanged after loading the dashboard page, the JSON API, the HTMX widget, and the category-expand partial.
- The archive quick action is the only mutating route added in this card, and it only ever changes `Budget.status`/`Budget.is_active` — never a transaction, journal entry, or account balance.

---

## RLS / Tenant Safety

- No schema changes; all reads go through the already-RLS-protected `budgets` (direct RLS) and `budget_categories` (child-table RLS via `budgets.tenant_id`) tables, unchanged from FAM-1303.
- All new routes use `get_db_with_tenant_context` + `require_tenant_member`.
- `test_tenant_a_cannot_see_tenant_b_budgets_on_dashboard` confirms Tenant B's dashboard API/page never contain Tenant A's budget data.
- `test_rls_active_on_budget_tables_via_dashboard` re-confirms RLS + FORCE RLS remain enabled on `budgets`/`budget_categories`.
- `test_inaccessible_account_name_not_leaked_in_dashboard` confirms that when a shared budget's category links to another family member's private expense account, that account's real name never appears in the dashboard HTML — `calculate_budget_actuals()` already resolves the account name through `FamilyAccountAccessService.can_view_account()` and returns `None` for accounts the requester can't see, and the dashboard widget passes that straight through (`"—"` is shown instead of the name).

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `07c75f53dbf6` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 44 tables, RLS active on 35
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **470 passed, 1 skipped** (up from the FAM-1303 baseline of 451 passed, 1 skipped — 19 new tests, zero regressions)

`app/tests/integration/test_dashboard_family_budgets.py` covers:
- API: auth required, expected sections present, empty state, planned/actual/remaining/percent values match posted journal activity.
- Partial: auth required, widget renders on the full dashboard page alongside the existing commitments/family-goals sections, empty state, progress bar + over-budget/near-limit badges appear, category breakdown partial renders.
- Permissions: head sees all budgets; adult sees shared/family + own private only; viewer sees budgets read-only with no manage action; manage action appears only when `can_manage`.
- Safety: no financial records or notifications created by any dashboard view; `Budget.total_actual` is never mutated by rendering; a private account name is never leaked through a shared budget's category display.
- Tenant/RLS: cross-tenant budget isolation on both the API and the rendered page; RLS status on `budgets`/`budget_categories`.

Regression: `test_dashboard_widget.py`, `test_dashboard_ai.py`, `test_family_budgets.py`, `test_family_goals.py`, `test_family.py`, and `test_family_account_visibility.py` all still pass in full.

---

## Known Limitations

- Budget category creation/editing remains on the full `/family/budgets` page (no dedicated HTML page exists yet for that either, matching the same gap already documented for What-If/Debt/Savings/Goal Planner in AI-1223) — the dashboard only links there.
- The archive quick action has no "unarchive" counterpart in the widget (matches `FamilyBudgetService`, which doesn't expose one either); reactivating a budget requires `PATCH /family/budgets/{id}` with `status=active`.
- No AI budget advisor or forecasting was added, per this card's explicit scope limits.
- `average_percent_used` is a simple mean across active budgets' overall percent-used, not weighted by budget size; acceptable for a summary card but worth revisiting if budgets vary widely in scale.

---

## Recommended Next Card

**FAM-1304 — Allowance and Chore Tracking**

With family budgets now modeled, permissioned, and visible on the dashboard, the next item in the Family Finance epic (per `PLAN_V2.md`) is allowance and chore tracking for children — a natural extension of the family-role permission system already built across FAM-1300 through FAM-1303 and DB-1106A.
