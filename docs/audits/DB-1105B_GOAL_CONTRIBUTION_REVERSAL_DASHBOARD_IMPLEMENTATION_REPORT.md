# DB-1105B — Family Goal Contribution Reversal Dashboard Action Implementation Report

## Summary

Added a permission-aware "Recent Contributions" list to the Family Goals dashboard widget, and a "Reverse" action that lets HEAD/PARENT (or a managing ADULT) reverse an eligible posted contribution directly from the dashboard. The reversal action is a thin HTMX wrapper around the exact same `FamilyGoalService.reverse_contribution()` — and, transitively, `AccountingService.reverse_journal_entry()` — already shipped and tested by GOAL-1401B. No reversal logic was rebuilt: this card only adds a read-only contribution list and a route that calls the existing service method and re-renders the widget.

Prior to this card, no per-contribution history existed anywhere in the dashboard, so there was nothing to attach a reversal action to (this exact gap was called out as a known limitation in GOAL-1401B's own report). No full goal-management page was built — only a small "recent contributions" list per goal card, matching the card's explicit scope.

No database schema changes or Alembic migration were needed. Alembic head remains `a4c9e1f7b2d3`.

---

## Files Changed

**New:**
- `app/templates/dashboard/partials/family_goal_contributions.html` — per-goal contribution list partial.
- `app/tests/integration/test_dashboard_family_goals_reversal.py` — 18 new tests.
- `docs/audits/DB-1105B_GOAL_CONTRIBUTION_REVERSAL_DASHBOARD_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/schemas/goal.py` — added `DashboardGoalContributionItem`; added `recent_contributions: List[DashboardGoalContributionItem]` to `DashboardFamilyGoalItem` (default `[]`, so existing JSON consumers are unaffected).
- `app/schemas/__init__.py` — exported `DashboardGoalContributionItem`, matching the existing re-export convention for dashboard schemas.
- `app/routers/dashboard.py` — `_build_family_goals_dashboard()` now also loads each goal's recent contributions (via the unchanged `FamilyGoalService.list_contributions()`) and computes `can_reverse` per contribution; added `POST /dashboard/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse`.
- `app/templates/dashboard/partials/family_goal_card.html` — includes the new contributions partial at the bottom of each goal card.

`app/services/family_goal_service.py` (`reverse_contribution`, `list_contributions`) and `app/services/accounting_service.py` (`reverse_journal_entry`) were **not modified** — both are reused exactly as shipped by GOAL-1401B/ACC-503A.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| POST | `/dashboard/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse` | *(new)* Reverses a posted contribution via `FamilyGoalService.reverse_contribution()`, then re-renders the whole `#family-goals-widget`. |
| GET | `/dashboard/partials/family-goals`, `GET /dashboard/api/family-goals`, `POST .../contributions`, `POST .../complete`, `POST .../cancel` | *(unchanged)* All existing DB-1105A routes; only their shared builder (`_build_family_goals_dashboard`) gained the new `recent_contributions` data. |

The new route requires `require_tenant_member` and uses `get_db_with_tenant_context`, identical to every other family-goals dashboard route.

---

## Templates Added / Updated

- `family_goal_contributions.html` *(new)* — renders each goal's `recent_contributions` as a small list: date, amount, contributor name (if known), a status badge (Posted / Reversed / Failed / Progress Only), and a Reverse button when `contribution.can_reverse` is true.
- `family_goal_card.html` *(modified)* — includes the new partial directly below the existing progress bar / quick-action row, so it inherits the card's existing `currency` context automatically (no new context plumbing needed).
- `family_goals_widget.html` / `family_goals_list.html` — unchanged; the new content flows through the existing per-goal card include.

---

## Contribution History Display Behavior

- Each goal card shows up to 5 of its most recent contributions (newest first, reusing `FamilyGoalService.list_contributions()`'s existing date-descending order), regardless of `posting_status` — progress-only, posted, reversed, and failed contributions are all shown, distinguished only by badge.
- Because the dashboard already only ever iterates over `FamilyGoalService.list_visible_goals()` (DB-1105A's existing visibility filter), contribution history for a goal a user cannot view is never fetched or rendered — no new visibility check was needed.
- Contributor names are resolved with a single batched `User` query per goal (`_dashboard_contributor_names`), avoiding N+1 queries and avoiding async lazy-loading pitfalls on the `GoalContribution.contributor` relationship.

---

## Reversal Dashboard Behavior

`POST /dashboard/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse`:

1. Calls `FamilyGoalService(db, tenant_id, user).reverse_contribution(goal_id, contribution_id)` — identical tenant scoping, permission gate (`require_manage`), and posting-eligibility checks as the GOAL-1401B API route.
2. On success, rebuilds and returns the full `family_goals_widget.html` partial (`hx-target="#family-goals-widget"`, `hx-swap="outerHTML"`), matching the exact pattern already used by the add-contribution/complete/cancel actions.
3. On `FamilyGoalServiceError` (not found, wrong goal, cross-tenant, unauthorized, not-postable, etc.), the widget is still rebuilt and returned with `action_error` set and a `400` status — the same safe-inline-error pattern already used by `family_goals_add_contribution_partial`. No financial mutation occurs on any error path, since `reverse_contribution()` raises before any commit.

---

## Confirmation Behavior

The Reverse button uses the project's existing `hx-confirm` pattern (already used for the goal complete/cancel buttons):

```html
hx-confirm="Reverse this goal contribution? This creates a reversing journal entry and cannot be undone."
```

No separate confirmation route or modal was added — this matches the existing dashboard convention exactly and needed no new UI pattern.

---

## Idempotency Behavior

- The dashboard route performs no idempotency logic of its own; it delegates entirely to `FamilyGoalService.reverse_contribution()`, which already returns the existing reversal unchanged on a repeated call (GOAL-1401B).
- Verified by `test_repeated_dashboard_reverse_is_idempotent`: two dashboard POSTs against the same contribution leave exactly one `JournalEntry` with `reversed_entry_id` pointing at the original.

---

## Permission Behavior

- The Reverse button's visibility (`contribution.can_reverse`) is computed dashboard-side from the same `can_manage_goal()` result already used for the goal's other quick actions, plus the contribution's own posting state (`journal_entry_id` set, `reversal_journal_entry_id` unset, `posting_status == "posted"`, `amount > 0`).
- This is a **display-only** convenience check — the actual authorization decision is made (and re-checked) inside `FamilyGoalService.reverse_contribution()` itself via `require_manage()`, so even a hand-crafted POST to the reverse route from an unauthorized session is rejected server-side with the same `400`/`action_error` path.
- Verified by `test_eligible_posted_contribution_shows_reverse_button_for_head`, `test_viewer_does_not_see_reverse_button`, `test_unauthorized_viewer_cannot_reverse` (button hidden **and** a direct POST attempt is still rejected server-side with zero journal entries created).

---

## Progress Behavior

Goal progress after a dashboard reversal is handled entirely by the underlying, unchanged `FamilyGoalService.reverse_contribution()` (GOAL-1401B): `goal.current_amount` is decremented by the reversed contribution's amount, and `status` reverts from `completed` to `active` if it drops back below target. Verified by `test_goal_progress_reduced_after_dashboard_reverse`.

---

## RLS / Tenant Safety

- The new route requires `require_tenant_member` and uses `get_db_with_tenant_context`, identical to every other family-goals dashboard route.
- `reverse_contribution()`'s existing tenant-scoped `get_contribution()`/`get_goal()` lookups mean a cross-tenant goal or contribution ID resolves to a service error, not a silent cross-tenant mutation — verified by `test_cross_tenant_dashboard_reverse_rejected` and `test_contribution_from_another_goal_rejected`.
- `test_tenant_a_cannot_see_tenant_b_contribution_on_dashboard` confirms Tenant B's dashboard never renders Tenant A's contribution amount or goal name.
- `goals`, `goal_contributions`, `journal_entries`, and `journal_lines` all retain RLS + FORCE RLS — verified by `test_rls_active_on_goal_and_journal_tables_via_dashboard`.

---

## Read-Only Dashboard Safety

- `test_dashboard_view_creates_no_journal_entries` and `test_loading_widget_partial_creates_no_journal_entries` confirm that loading the dashboard and the family-goals widget partial (including the new contribution history) create zero `JournalEntry` rows and leave `Account`, `Budget`, and `Bill` row counts unchanged.
- Only the explicit `POST .../reverse` action can create a reversal journal entry — confirmed by the reversal tests above, which show exactly one new `JournalEntry` appears only after that specific POST.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `a4c9e1f7b2d3` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **708 passed, 1 skipped** (up from the GOAL-1401B baseline of 690 passed, 1 skipped — 18 new tests, zero regressions)

`app/tests/integration/test_dashboard_family_goals_reversal.py` (18 tests) covers:
- Rendering/eligibility: recent posted contribution appears; progress-only contributions show no Reverse button; reversed contributions show a Reversed badge and no button; an eligible posted contribution shows the button for HEAD; a VIEWER never sees the button.
- Route/auth: the reverse route requires auth; an authorized user can reverse; an unauthorized VIEWER cannot (server-side rejection, zero journal entries created); a cross-tenant attempt is rejected; a contribution from a different goal (via the `goal_id` in the route) is rejected.
- Reversal: dashboard reversal creates a balanced reversing journal entry; the original contribution row and journal entry are unchanged; `posting_status` becomes `reversed`; goal progress is reduced; repeated dashboard reversal is idempotent.
- Read-only safety: viewing the dashboard and loading the widget partial create no journal entries and leave accounts/budgets/bills untouched.
- RLS: Tenant B never sees Tenant A's contribution on the dashboard; RLS/FORCE RLS re-verified on `goals`, `goal_contributions`, `journal_entries`, `journal_lines`.

Regression: `test_dashboard_widget.py` (including the existing DB-1105A family-goals-widget tests), `test_goal_contribution_reversal.py` (GOAL-1401B), `test_family_goals.py`, and `test_goal_contributions_accounting.py` all pass, alongside the complete project test suite.

---

## Known Limitations

- **No full/paginated contribution history.** Only the 5 most recent contributions per goal are shown on the dashboard — explicitly matching this card's "do not build a full goal-management page" constraint. A dedicated goal-detail page with full history/pagination would be a natural future card.
- **No edit-in-place.** Correcting a posted contribution's amount still requires reverse + re-add, unchanged from GOAL-1401B.
- **Reversal reason is not collected from the dashboard.** The dashboard reverse action calls `reverse_contribution()` without a `reason`, unlike the full API route which accepts one — a future iteration could add an optional reason prompt if needed.

---

## Recommended Next Card

**AUTH-305 — Tenant Member Invitation Flow**

This gap has been flagged as a known limitation in at least three prior reports this session (FAM-1301, FAM-1302, GOAL-1401A), and every test fixture in the codebase already works around it with the same two-step create-then-PATCH pattern. `PLAN_V2_CARD_STATUS.md` lists `AUTH-305` as **Partial**: `FamilyMember` already has invitation fields, but there is no invitation endpoint and no email sending. Closing it removes a long-standing rough edge from real onboarding.
