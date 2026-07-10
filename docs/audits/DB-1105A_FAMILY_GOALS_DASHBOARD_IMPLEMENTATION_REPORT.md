# DB-1105A — Family Goals Dashboard Widget UI

## Summary

Implemented a permission-aware Family Goals dashboard widget for the Financial Life MVP.

The widget surfaces active family goals visible to the current user, shows progress bars and summary cards, supports HTMX-powered refresh and quick actions (add contribution, complete, cancel), and never exposes private goals to unauthorized family members or cross-tenant goals.

No database schema changes or Alembic migrations were required for this UI card; it reuses the existing `goals` / `goal_contributions` tables and `FamilyGoalService` from FAM-1302.

---

## Files Changed

| File | Change |
|------|--------|
| `app/routers/dashboard.py` | Added `_build_family_goals_dashboard`, `GET /dashboard/api/family-goals`, `GET /dashboard/partials/family-goals`, and `POST` partials for contributions, complete, and cancel. |
| `app/schemas/goal.py` | Added `DashboardFamilyGoalItem` and `FamilyGoalsDashboardResponse`. |
| `app/schemas/__init__.py` | Exported the new dashboard goal schemas. |
| `app/templates/dashboard/index.html` | Replaced the hardcoded "Active Goals" placeholder with `{% include "dashboard/partials/family_goals_widget.html" %}`. |
| `app/templates/dashboard/partials/family_goals_widget.html` | New main widget with summary cards, refresh button, and list partial inclusion. |
| `app/templates/dashboard/partials/family_goals_list.html` | New list/empty-state partial. |
| `app/templates/dashboard/partials/family_goal_card.html` | New per-goal card with progress bar, badges, and permission-aware quick actions. |
| `app/tests/integration/test_dashboard_widget.py` | Added 9 integration tests covering auth, rendering, role visibility, empty state, progress calculation, quick actions, tenant isolation, and RLS. |

---

## Routes Added

### JSON API

- `GET /dashboard/api/family-goals`  
  Returns `FamilyGoalsDashboardResponse` with visible goals, counts, totals, average progress, currency, and user permissions.

### Server-rendered partials (HTMX)

- `GET /dashboard/partials/family-goals`  
  Renders the full family goals widget partial.
- `POST /dashboard/partials/family-goals/{goal_id}/contributions`  
  Adds a contribution from the dashboard widget and refreshes the widget.
- `POST /dashboard/partials/family-goals/{goal_id}/complete`  
  Marks a goal completed from the dashboard widget and refreshes the widget.
- `POST /dashboard/partials/family-goals/{goal_id}/cancel`  
  Cancels a goal from the dashboard widget and refreshes the widget.

---

## API Behavior

`GET /dashboard/api/family-goals` returns UI-ready JSON including:

- `goals` — list of visible goals with `id`, `name`, `visibility`, `status`, `target_amount`, `current_amount`, `remaining_amount`, `progress_percent`, `target_date`, `owner_user_id`, `family_id`, and permission flags (`can_view`, `can_manage`, `can_contribute`).
- `active_goals_count` / `completed_goals_count`
- `total_target_amount` / `total_current_amount` / `total_remaining_amount`
- `average_progress_percent`
- `currency`
- `permissions.can_create_goal`

All endpoints require an authenticated tenant member and use `get_db_with_tenant_context`, so RLS tenant context is set before any query.

---

## HTMX Behavior

- The refresh button on the widget issues `hx-get="/dashboard/partials/family-goals"` and replaces the whole widget via `outerHTML`.
- The inline contribution form posts to `/dashboard/partials/family-goals/{goal_id}/contributions` and refreshes the widget.
- Complete/cancel buttons post to their respective partial routes with `hx-confirm` prompts and refresh the widget.
- Errors are surfaced inside the refreshed widget as an alert banner (`action_error`).

If HTMX is not loaded on the dashboard, the forms degrade to normal POST navigation and the partial still renders the widget correctly.

---

## Empty States

- **No goals at all:** shows a centered message with a "Create Goal" button for users who can create goals; otherwise shows "No goals are visible to you right now."
- **No visible goals for user:** same restricted-user message.
- **Widget action error:** rendered as an inline alert within the widget.
- **Unauthenticated user:** auth/RBAC dependencies return `401`/`403`.

---

## Permission Behavior

Permission checks are delegated to `FamilyGoalService`:

- `head` / `parent` see and manage all family goals.
- `adult` sees shared/family goals plus their own private goals, but not other adults' private goals.
- `teen` / `child` visibility follows existing `FamilyGoalService` rules.
- `viewer` sees shared/family goals read-only; quick-action buttons are hidden.

Each goal item includes `can_manage` and `can_contribute` flags so the template only renders the corresponding buttons when allowed.

---

## RLS / Tenant Safety

- All routes depend on `require_tenant_member` and `get_db_with_tenant_context`.
- `FamilyGoalService` builds queries within the tenant RLS context and applies family visibility rules.
- Goal contributions via the dashboard reuse `FamilyGoalService.add_contribution`, which validates the goal belongs to the tenant and optionally checks account access.
- Family goals from Tenant A never appear in Tenant B's dashboard or API.

---

## Test Results

Full verification run:

- `python -m compileall app` — OK
- `alembic current` — `951f42580bfd` (head)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -v --tb=short --disable-warnings` — **213 passed, 1 skipped**

---

## Known Limitations

- Goal contributions do not yet create accounting entries (deferred to `GOAL-1401A`).
- Dashboard contributions do not select a payment/source account; if/when account-linking is required, the inline form can be extended or redirect to the full goal page.
- Quick actions assume the user has HTMX available; non-HTMX clients still work but trigger a full page refresh.

---

## Recommended Next Card

**GOAL-1401A — Goal Contributions Through Accounting Engine**

When a family goal contribution is added, optionally post a balanced journal entry through `AccountingService` so savings toward goals are reflected in the chart of accounts and net-worth calculations.
