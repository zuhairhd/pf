# DB-1107A — Allowance and Chore Dashboard Widget UI Implementation Report

## Summary

Added a Chores & Allowance widget to the AI-centric dashboard (AI-1223), following the same pattern established by the commitments, family-goals, and family-budgets widgets: a JSON API for programmatic clients, an HTMX-refreshable server-rendered partial for the dashboard page, and permission-aware quick actions (submit completion, approve completion). The widget shows chores due soon, overdue chores, completions pending approval, and a role-scoped allowance summary (pending / approved this month / approved all-time / rejected, with a per-member breakdown where the viewer is allowed to see it). No new chore or allowance calculation logic was written in the router — everything is composed from `FamilyChoreService.list_visible_chores_for_user()` and `get_allowance_summary()`, plus two small new read-only helper methods added to the service itself (`list_pending_completions_for_user()`, `get_approved_allowance_this_month()`), exactly as FAM-1304 anticipated with `get_family_chore_summary()`.

No database schema changes were needed. Alembic head remains `356391296d35`.

---

## Files Changed

**New:**
- `app/templates/dashboard/partials/family_chores_widget.html` — widget wrapper (summary cards, overdue badge, chores list, pending approvals, allowance summary).
- `app/templates/dashboard/partials/family_chores_list.html` — assigned/overdue chore list / empty state.
- `app/templates/dashboard/partials/family_chore_card.html` — single chore card (badges, assignee, due date, allowance amount, quick actions).
- `app/templates/dashboard/partials/family_chore_pending_approvals.html` — pending-completion list with approve/reject actions.
- `app/templates/dashboard/partials/family_allowance_summary.html` — totals + per-member breakdown table.
- `app/tests/integration/test_dashboard_family_chores.py` — 25 new tests.

**Modified:**
- `app/routers/dashboard.py` — added `_build_family_chores_dashboard()`, `GET /api/family-chores`, `GET /partials/family-chores`, `POST /partials/family-chores/{chore_id}/complete`, `POST /partials/family-chore-completions/{completion_id}/approve`; main `/` route now also builds and passes `family_chores` context; new imports (`FamilyMember`, `ChoreStatus`, dashboard chore schemas, `FamilyChoreService`).
- `app/templates/dashboard/index.html` — added the family chores widget include, directly after the family budgets widget; no existing section was removed.
- `app/schemas/family_chore.py` — added dashboard-specific schemas: `DashboardChoreItem`, `DashboardCompletionItem`, `DashboardAllowanceMemberBreakdown`, `DashboardAllowanceSummary`, `FamilyChoresDashboardResponse` (kept separate from the FAM-1304 `ChoreResponse`/`ChoreCompletionResponse`/`AllowanceSummaryResponse` so the existing `/family/chores*` API contract is untouched).
- `app/services/family_chore_service.py` — added two small, read-only, role-scoped helper methods used by the dashboard: `list_pending_completions_for_user()` and `get_approved_allowance_this_month()`. No chore CRUD, completion, or allowance-summary logic was duplicated or changed.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/dashboard/api/family-chores` | *(new)* UI-ready JSON: assigned/overdue chores, pending approvals, allowance summary, counts, permissions. |
| GET | `/dashboard/partials/family-chores` | *(new)* HTMX partial rendering the widget for the current user/tenant. |
| POST | `/dashboard/partials/family-chores/{chore_id}/complete` | *(new)* Permission-checked quick action; submits a completion (status=submitted, `earned_amount=0`) for a chore assigned to the caller, returns the refreshed widget. |
| POST | `/dashboard/partials/family-chore-completions/{completion_id}/approve` | *(new)* Permission-checked quick action (HEAD/PARENT only); approves a completion at the chore's allowance amount, returns the refreshed widget. |
| GET | `/dashboard/` | *(updated)* Main dashboard page now also builds and renders `family_chores`. |

All routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other dashboard route.

---

## Templates Added / Updated

See "Files Changed." `index.html` keeps its existing `ai_today.html`, `commitments_widget.html`, `family_goals_widget.html`, and `family_budgets_widget.html` includes exactly as before — the new widget was appended, not substituted.

---

## Dashboard Widget Sections

1. **Summary cards** — Due Soon count, Overdue count, Pending Approval count, Earned This Month (currency-formatted).
2. **Overdue badge** — shown only when the overdue count is non-zero.
3. **Chores list** — one card per due-soon/overdue chore visible to the caller: title, overdue/due-soon badge, frequency badge, assignee name (or "Unassigned"), due date, allowance amount, and a "Mark Complete" quick action when the caller is the assigned member.
4. **Pending approvals** — one row per completion awaiting approval visible to the caller: chore title, submitter name, submitted date, notes, and Approve/Reject actions gated by role (Reject links to the full chore page — see Known Limitations).
5. **Allowance summary** — pending/approved(all-time)/rejected totals, plus a per-member breakdown table when `by_member` is non-empty.
6. **Empty state** — "No chores due soon or overdue" (with an assign link if the user can manage chores) and "No completions awaiting approval." when there is nothing pending.
7. **Error state** — if the widget's data fails to build for any reason, a safe "Chores are temporarily unavailable" message renders instead of a 500 error.

---

## HTMX Behavior

- **Refresh**: the widget's refresh button (`hx-get="/dashboard/partials/family-chores"`, `hx-target="#family-chores-widget"`, `hx-swap="outerHTML"`) re-fetches and swaps the whole widget in place, matching the commitments/family-goals/family-budgets widgets exactly.
- **Submit-completion quick action**: each due-soon/overdue chore card assigned to the caller shows a "Mark Complete" button (`hx-post=".../complete"`, `hx-target="#family-chores-widget"`, `hx-swap="outerHTML"`, `hx-confirm`). Server-side, this calls `FamilyChoreService.submit_completion()` unchanged — the permission check (`can_user_submit_completion`) lives entirely in the service, not the template, so a crafted request from an unauthorized member is rejected with a 400 and an `action_error` message, not just hidden from the UI.
- **Approve-completion quick action**: each pending-approval row visible to HEAD/PARENT shows an "Approve" button (`hx-post=".../approve"`, same target/swap pattern, `hx-confirm`). Calls `FamilyChoreService.approve_completion()` unchanged.
- **Reject was intentionally omitted** as a dashboard quick action — per the card's own explicit instruction ("If reject needs a reason and the dashboard form is too much, include approve only and link to the full chore page for reject"), since `reject_completion()` requires a non-empty `rejection_reason` that doesn't fit a one-click button. The pending-approvals partial instead renders a "Reject" link to `/family/chores` (see Known Limitations).

---

## Empty States

- **No family profile**: `FamilyChoreService` already works without a `Family` row (role resolution falls back to tenant OWNER/ADMIN → HEAD, else VIEWER via `FamilyAccountAccessService`); the composition helper's family-lookup methods (`get_allowance_summary`, `list_pending_completions_for_user`, `get_approved_allowance_this_month`) all short-circuit to zeroed/empty results when no `Family` row exists, so the widget renders normally with empty lists and zero totals.
- **Family exists but no chores**: "No chores due soon or overdue. Assign a chore to start tracking allowance." (with an assign link, if permitted) or "No chores due soon or overdue right now." (if not).
- **No chores assigned to current member**: TEEN/CHILD callers with no assigned chores simply see the same empty chores list — `list_visible_chores_for_user()` already returns `[]` for them when they have no `FamilyMember` record or no assigned chores.
- **No pending approvals**: "No completions awaiting approval." renders in the pending-approvals section regardless of role.
- **No allowance activity**: "No allowance activity yet." renders in place of the per-member table when `by_member` is empty; the three summary figures simply show `0.000`.
- **Service/API error**: `_build_family_chores_dashboard()` is wrapped in `try/except` at both the page and HTMX-partial call sites; on failure, `family_chores` is `None` and the widget renders "Chores are temporarily unavailable" instead of raising.
- **Unauthenticated user**: `GET /dashboard/api/family-chores` and `GET /dashboard/partials/family-chores` both return 401/403 via `require_tenant_member`; the main `/dashboard/` page itself also requires auth, so there is no unauthenticated-render path to test there.

---

## Permission Behavior

Reuses `FamilyChoreService` unchanged (no new permission logic):
- **HEAD/PARENT** see every chore and every pending completion in the family, the full allowance summary, and can approve any completion.
- **TEEN/CHILD** see and can act only on chores assigned to themselves; their pending-approvals list shows only their own submissions (so they can see "awaiting approval" status), never anyone else's; they cannot approve.
- **ADULT** (per FAM-1304's existing rules) has broad chore visibility like HEAD/PARENT/VIEWER but no create/manage/approve rights — the dashboard's `can_submit`/`can_manage`/`can_approve` flags all resolve to `False` for ADULT unless a chore happens to be self-assigned.
- **VIEWER** sees the same visible chores read-only; no "Mark Complete" or "Approve" buttons ever render (`can_submit`/`can_manage`/`can_approve` are always `False`).
- Verified by `test_head_and_parent_see_all_chores_and_approvals`, `test_teen_sees_only_own_assigned_chores`, `test_child_sees_only_own_assigned_chores`, `test_viewer_has_no_action_buttons`, `test_submit_action_only_for_assigned_member`, and `test_approve_action_only_for_head_parent`.

---

## Allowance Summary Behavior

- `pending_approval_amount` / `approved_earned_amount` / `rejected_amount` come straight from the unchanged `FamilyChoreService.get_allowance_summary()` (all-time, role-scoped).
- `approved_this_month_amount` is new: `get_approved_allowance_this_month()` sums `earned_amount` for completions with `status == approved` and `approved_at >= <first day of the current month>`, scoped identically to `get_allowance_summary()` (HEAD/PARENT see the whole family; everyone else sees only their own completions).
- The per-member breakdown (`by_member`) is passed through unchanged from `get_allowance_summary()`; it is empty for TEEN/CHILD/ADULT/VIEWER's own single-member view only in the sense that it contains at most their own entry (the service already filters completions to their own member before building the breakdown).
- Verified by `test_dashboard_family_chores_api_allowance_summary_reflects_approval` (checks both all-time and this-month totals after an approval) and `test_dashboard_family_chores_widget_shows_allowance_summary`.

---

## Read-Only Financial Safety

- `test_dashboard_widget_creates_no_financial_records` confirms Account/Goal/JournalEntry row counts are unchanged after loading the dashboard page, the JSON API, and the HTMX widget.
- The only two mutating routes added in this card are the submit-completion and approve-completion quick actions, and both only ever create/update a `FamilyChoreCompletion` row (`status`, `earned_amount`, `approved_by_user_id`, `approved_at`) — never a transaction, journal entry, or account balance, exactly as `FamilyChoreService` already guaranteed in FAM-1304.
- `test_repeated_dashboard_refresh_creates_no_completions` confirms that repeatedly refreshing the read-only widget/API (3x each) never creates a completion — only the explicit `POST .../complete` route does.
- `test_unauthorized_member_cannot_submit_another_members_chore_from_dashboard` and `test_unauthorized_member_cannot_approve_from_dashboard` confirm the dashboard quick-action routes return 400 (via the service's own permission checks, surfaced as `action_error`) and create no completion / leave the completion's status unchanged when attempted by a member without permission.

---

## RLS / Tenant Safety

- No schema changes; all reads go through the already-RLS-protected `family_chores` and `family_chore_completions` tables, unchanged from FAM-1304 (both created with RLS + FORCE RLS from their migration).
- All new routes use `get_db_with_tenant_context` + `require_tenant_member`.
- `test_tenant_a_cannot_see_tenant_b_chores_on_dashboard` confirms Tenant B's dashboard API/page never contain Tenant A's chore data.
- `test_rls_active_on_chore_tables_via_dashboard` re-confirms RLS + FORCE RLS remain enabled on `family_chores`/`family_chore_completions`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `356391296d35` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **524 passed, 1 skipped** (up from the FAM-1304 baseline of 499 passed, 1 skipped — 25 new tests, zero regressions)

`app/tests/integration/test_dashboard_family_chores.py` covers:
- API: auth required, expected sections present, assigned due-soon chore returned, overdue chore returned, pending approvals returned for HEAD/PARENT, allowance summary reflects an approval (all-time and this-month).
- Partial: auth required, widget renders on the full dashboard page alongside the existing commitments/family-goals/family-budgets sections, empty state, allowance summary renders, pending approvals render.
- Permissions: HEAD/PARENT see all chores and approvals; TEEN sees only own assigned chores; CHILD sees only own assigned chores; VIEWER has no action buttons; submit action only available to the assigned member; approve action only available to HEAD/PARENT.
- HTMX: submit-completion quick action creates a completion; approve-completion quick action approves and updates the allowance summary; repeated refresh creates no completions.
- Safety: no financial records (Account/Goal/JournalEntry) created by any dashboard view; an unauthorized member cannot submit another member's chore from the dashboard (400, no completion created); an unauthorized member cannot approve from the dashboard (400, completion unchanged).
- Tenant/RLS: cross-tenant chore isolation on both the API and the rendered page; RLS status on `family_chores`/`family_chore_completions`.

Regression: `test_dashboard_widget.py`, `test_dashboard_ai.py`, `test_dashboard_family_budgets.py`, and `test_family_chores.py` all still pass in full, alongside the complete suite.

---

## Known Limitations

- Reject is not available as a dashboard quick action, since `FamilyChoreService.reject_completion()` requires a non-empty `rejection_reason` that doesn't fit a one-click HTMX button; the widget links to `/family/chores` instead — the same "View"/"full page" precedent already used by the family-budgets widget's `family_budget_card.html`, even though `/family/chores` is currently a JSON-only API route with no dedicated HTML page (matching the same acknowledged gap from DB-1106A).
- Chore creation/management still lives on the full `/family/chores` API; the widget only links a "Manage Chores" action for HEAD/PARENT, it does not embed create/edit forms.
- No accounting posting for approved allowance — allowance amounts remain plain numeric fields (`FamilyChoreCompletion.earned_amount`), per this card's explicit scope limits (documented follow-up: FAM-1305).
- No recurring-chore auto-regeneration; `frequency` remains descriptive only, unchanged from FAM-1304.
- No mobile-specific UI was built, per this card's explicit scope limits.

---

## Recommended Next Card

**FAM-1305 — Allowance Payment Posting Through Accounting Engine**

With chores and allowance now modeled, permissioned, tracked, and visible on the dashboard end-to-end, the last deliberately deferred piece of the FAM-1304/DB-1107A pair is turning an *approved* completion's `earned_amount` into an actual posted transaction (crediting the assigned member's allowance/cash account through the existing accounting engine), gated so it never silently creates financial records for members without a linked account.
