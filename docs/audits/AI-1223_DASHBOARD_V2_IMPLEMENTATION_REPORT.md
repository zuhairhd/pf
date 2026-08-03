# AI-1223 — Dashboard v2 (AI-Centric) Implementation Report

## Summary

Rebuilt the dashboard landing page around a single AI-centric "Today" payload composed from existing, already-read-only AI CFO engines and services (Health Score, Proactive Alerts preview, Savings Optimizer, Debt Optimizer, Family Goals, Commitments). The dashboard now leads with an AI brief, a financial health snapshot, top alerts, AI recommendation cards, and optimizer shortcuts — while the existing bills/subscriptions commitments widget and family goals widget are preserved unchanged. All new functionality is strictly read-only: no transactions, journal entries, accounts, goals, bills, or notifications are created or modified by viewing the dashboard.

A pre-existing privacy defect in the Proactive Alerts engine was discovered and fixed during this work (see "Security Fix" below): `_detect_goal_risks()` did not apply family goal visibility rules, so it could describe another family member's private goal in an alert. This had been latent since AI-1219 because no UI previously rendered alert candidate text; it is fixed as part of safely surfacing alerts on the dashboard.

No database schema changes were needed. Alembic head remains `360b89eed134`.

---

## Files Changed

**New:**
- `app/services/dashboard_ai_service.py` — `DashboardAIService`, composes the "Today" payload.
- `app/schemas/dashboard.py` — `DashboardToday` and supporting response schemas.
- `app/templates/dashboard/partials/ai_today.html` — outer HTMX-refreshable wrapper.
- `app/templates/dashboard/partials/ai_today_brief.html` — greeting/summary/confidence banner.
- `app/templates/dashboard/partials/ai_health_snapshot.html` — health score dimensions + quick stats.
- `app/templates/dashboard/partials/ai_alerts.html` — top proactive alert candidates.
- `app/templates/dashboard/partials/ai_insights.html` — savings/debt quick-insight cards + suggested actions.
- `app/templates/dashboard/partials/ai_quick_actions.html` — optimizer shortcuts + suggested chat questions.
- `app/tests/integration/test_dashboard_ai.py` — 19 new tests.

**Modified:**
- `app/routers/dashboard.py` — added `/api/today` and `/partials/ai-today`; main `/` route now also builds the AI payload; removed the now-unused `latest_insights` query.
- `app/templates/dashboard/index.html` — replaced the static placeholder banner/stat-cards/insights/quick-actions block with `{% include "dashboard/partials/ai_today.html" %}`; commitments and family-goals widget includes are unchanged.
- `app/templates/ai/chat.html` — added a small, additive script that pre-fills (never auto-sends) the chat input from a `?q=` query param, so dashboard quick-action links can deep-link a suggested question.
- `app/ai_cfo/llm/prompts.py` — added `dashboard_brief_prompt()`, following the existing structured-prompt pattern (aggregated summary only, no raw records).
- `app/ai_cfo/engines/proactive_alerts.py` — **security fix**: `_detect_goal_risks()` now filters goals through `FamilyGoalService.can_view_goal()` when a user is provided, matching the pattern already used in every other engine (What-If, Debt, Savings, Goal Planner).

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/dashboard/` | *(updated)* Main dashboard page; now also renders the AI-centric sections via `ai_today`. |
| GET | `/dashboard/api/today` | *(new)* UI-ready JSON: greeting, summary, health score, alerts, commitments, goals, insights, suggested actions/questions, quick actions, confidence fields. Optional `?include_narrative=true` to attempt an LLM-enhanced summary. |
| GET | `/dashboard/partials/ai-today` | *(new)* HTMX partial that refreshes the entire AI "Today" block (`#ai-today-widget`) without a full page reload. |

All three require `require_tenant_member` (or equivalent auth dependency) and use `get_db_with_tenant_context`, so RLS tenant context is always set.

---

## Templates Added / Updated

See "Files Changed" above. `index.html` keeps its existing `{% include "dashboard/partials/commitments_widget.html" %}` and `{% include "dashboard/partials/family_goals_widget.html" %}` blocks exactly as before — neither existing widget was removed or restructured.

---

## Dashboard v2 Sections

1. **"Today" / AI brief header** — greeting, deterministic (or optionally LLM-enhanced) summary sentence, confidence badge, health-score circle.
2. **Financial Health Snapshot** — per-dimension scores from the existing `HealthScoreService`, plus overdue-bills/active-goals/goal-progress quick stats.
3. **Top Alerts** — up to 5 highest-severity candidates from `ProactiveAlertsEngine.preview()` (critical > warning > info), each with a severity badge, confidence label, and a safe "Review" link to the relevant existing page (bills/subscriptions/goals) — no new alert or notification is created.
4. **AI Recommendations / Insights** — quick-insight cards from `SavingsOptimizer` (emergency fund mode) and `DebtOptimizer` (avalanche strategy), each carrying its own confidence label and a deep link to AI Chat; plus a deterministic "Suggested Actions" list.
5. **Commitments widget** — unchanged (`commitments_widget.html`).
6. **Family Goals widget** — unchanged (`family_goals_widget.html`).
7. **Optimizer shortcuts** — What-If Simulator, Debt Optimizer, Savings Optimizer, Goal Planner, and AI Chat quick-action cards. Since only AI Chat and AI Insights have dedicated HTML pages today, the other four link into AI Chat with a pre-filled relevant question (via the new `?q=` param) — a deliberately small, additive integration rather than building four new full pages (out of scope for this card).

---

## AI/LLM Behavior

- The dashboard **prefers deterministic summaries** by default: `build_today()` always computes a deterministic sentence from health score, commitments, and goals — no LLM call is made on a normal page view or default `/dashboard/api/today` call, which keeps every dashboard load free and fast.
- An optional `?include_narrative=true` query param on `/dashboard/api/today` attempts an LLM-enhanced brief via the existing `CostController` + `LLMClient` + `SafetyFilter` stack (same pattern as the other engines), using a new structured prompt (`dashboard_brief_prompt`) that sends **only an aggregated summary** (health score number, top alert title, bill/goal counts) — never raw transactions, account numbers, or PII.
- If the LLM is unconfigured, over the tenant's daily budget, or the call fails, the deterministic summary is used instead — verified by `test_dashboard_today_works_without_openai_key`, which asserts the endpoint succeeds with `include_narrative=true` in the default test environment (no `OPENAI_API_KEY`).

---

## Confidence Display Behavior

- `/dashboard/api/today` and the dashboard page both surface `confidence_score`, `confidence_label`, `confidence_factors`, and `confidence_explanation` (AI-1222 fields) for the overall "Today" summary.
- Confidence factors: always `deterministic_calculation`; `direct_accounting_data` when a health score was computable, else `low_transaction_history`; `sufficient_history` when any commitments/goals data exists; `user_confirmed_memory` when the user has active AI memories; `llm_fallback` when `include_narrative=true` was requested but the LLM was unavailable/failed (never added when narrative wasn't requested, and an LLM success never boosts the score by itself — consistent with the AI-1222 rule).
- Each alert candidate and each quick-insight card carries its own `confidence_score`/`confidence_label` (already computed by the underlying engines from AI-1222), rendered as a small badge so users can see which recommendations are well-supported vs. based on limited/assumed data.
- The dashboard never claims certainty it doesn't have: with no financial history, confidence naturally lands at `low`/`medium` and the summary text says so plainly ("Add accounts and transactions to unlock your health score.").

---

## Proactive Alerts Integration (Read-Only)

- The dashboard calls `ProactiveAlertsEngine(db, tenant_id, user=user).preview()` — the existing preview-only method that detects candidates without persisting notifications (unchanged from AI-1219/AI-1222).
- Alerts are sorted by severity (critical → warning → info) and the top 5 shown.
- Viewing the dashboard, calling `/dashboard/api/today`, or refreshing `/dashboard/partials/ai-today` never creates a `Notification` row — verified by `test_dashboard_view_creates_no_notifications` and `test_ai_today_partial_refresh_does_not_modify_records`. Notifications are only ever created via the pre-existing, explicit `POST /ai/proactive-alerts/run` endpoint, which this card does not call.

### Security fix: goal-alert visibility leak

While building this, `test_dashboard_adult_does_not_see_other_adult_private` (an existing family-goals test) started failing: `ProactiveAlertsEngine._detect_goal_risks()` queried **all** active goals in the tenant with no family-visibility filtering, so a "goal may miss deadline" alert could describe another family member's `private` goal by name. Every other engine (What-If, Debt Optimizer, Savings Optimizer, Goal Planner) already filters goals through `FamilyGoalService.can_view_goal()`; Proactive Alerts had been missed. Fixed by applying the same check in `_detect_goal_risks()` when a `user` is provided. This closes a real (if previously unexercised) data-exposure gap, not just a test failure.

---

## Empty / Error States

- **No health score data** (new tenant, no accounts/transactions): `health_score` is `null`; the brief and snapshot sections show a clear "Add accounts and transactions to unlock..." message instead of erroring.
- **No alerts**: the alerts card shows a "You're all caught up" success state.
- **No bills/subscriptions**: the unchanged commitments widget shows its existing empty-state copy.
- **No goals**: the unchanged family goals widget shows its existing empty-state copy; the AI insights section suggests "Set a savings goal."
- **No debts**: `DebtOptimizer.optimize()` raises `DebtOptimizerError` (404, no active debts); caught and simply omits the debt insight card rather than erroring.
- **AI/service failure**: `DashboardAIService.build_today()` is wrapped in `try/except` at both dashboard-page and HTMX-partial call sites; on any exception the page renders a safe fallback banner ("AI-powered insights are temporarily unavailable. Your account data is safe and unchanged.") instead of a 500 error.
- **LLM disabled/unavailable**: covered under "AI/LLM Behavior" above.

---

## Read-Only Safety

`DashboardAIService` only ever calls read methods: `HealthScoreService.calculate_score()`, `CommitmentService.summary()`, `FamilyGoalService.get_active_family_goals_summary()`, `ProactiveAlertsEngine.preview()`, `SavingsOptimizer.optimize()`, `DebtOptimizer.optimize()` — all pre-existing read-only methods reused as-is, with zero new writes introduced. Verified by:
- `test_dashboard_view_creates_no_financial_records` — Account/Goal/JournalEntry/Bill/Subscription counts unchanged after loading the page and API twice.
- `test_dashboard_view_creates_no_notifications` — Notification count unchanged across page, API, and partial calls.
- `test_ai_today_partial_refresh_does_not_modify_records` — same guarantee specifically for the HTMX refresh path, called twice.

---

## RLS / Tenant Safety

- No schema changes, so no new RLS policies were needed; all reads go through already-RLS-protected tables (`bills`, `subscriptions`, `goals`, `accounts`, etc.) via tenant-scoped services.
- `/dashboard/api/today`, `/dashboard/partials/ai-today`, and `/dashboard/` all use `get_db_with_tenant_context` + `require_tenant_member`, matching the existing pattern.
- `test_dashboard_today_tenant_isolation` confirms Tenant B's `/dashboard/api/today` and dashboard HTML never contain Tenant A's overdue bill data.
- `test_rls_still_active_on_dashboard_dependencies` re-confirms RLS + FORCE RLS remain enabled on `bills`, `subscriptions`, `goals`, and `accounts`.
- The pre-existing family-goal-visibility fix (above) closes a same-tenant, cross-family-member leak that the RLS layer alone cannot address (RLS operates at the tenant boundary, not per-user goal visibility).

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `360b89eed134` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 44 tables, RLS active on 35
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **425 passed, 1 skipped** (up from the AI-1222 baseline of 406 passed, 1 skipped — 19 new dashboard tests, zero regressions)

`app/tests/integration/test_dashboard_ai.py` covers:
- API: auth required, expected sections present, confidence fields present, safe health-score fallback, empty state, overdue-bill alert with correct confidence.
- Page: AI brief/health snapshot/alerts/recommendations sections render; optimizer quick-action links present; existing commitments/family-goals widgets still render (regression guard); empty state renders.
- HTMX: partial requires auth, renders `#ai-today-widget`, repeated refresh creates no records.
- Safety: no financial records or notifications created by any dashboard view; endpoint works without an OpenAI key and reports `llm_fallback` when narrative was requested; a distinctive account code never appears in the JSON response.
- Tenant isolation: Tenant B cannot see Tenant A's overdue bill via API or page; RLS remains active on `bills`, `subscriptions`, `goals`, `accounts`.

Regression: `app/tests/integration/test_dashboard_widget.py` (28 tests, including the family-goal-visibility test that surfaced the security fix) and `app/tests/integration/test_proactive_alerts.py` (16 tests) both still pass in full.

---

## Known Limitations

- What-If Simulator, Debt Optimizer, Savings Optimizer, and Goal Planner still have no dedicated HTML pages (they are API-only, as before this card); dashboard "quick access" to them is via a pre-filled AI Chat question rather than a purpose-built UI. Building four new full pages was judged out of scope for this card ("do not build a full SPA rewrite").
- The optional LLM-enhanced narrative (`?include_narrative=true`) is not exposed in the default page UI (the page always uses the deterministic summary) to avoid burning LLM budget on every dashboard view; it's available for future use by API clients.
- Quick-insight cards currently cover Savings (emergency fund) and Debt (avalanche); a What-If or Goal Planner-derived card was not added because those engines require scenario-specific or contribution-specific inputs that aren't naturally available without user selection.
- The `?q=` chat pre-fill is display-only (populates the input box); it does not auto-submit, by design, to keep the dashboard read-only and avoid surprising LLM calls from a single click.

---

## Recommended Next Card

**FAM-1303 — Family Budgets**

With the full AI-1200 epic (AI-1201 through AI-1223) now complete, the next gap per `docs/audits/PLAN_V2_CARD_STATUS.md` is in the Family Finance epic: FAM-1300–1302 (foundation, account visibility, family goals) are done, and FAM-1303 (Family Budgets) is the next partial/missing item, continuing the family-finance track alongside the now AI-centric dashboard.
