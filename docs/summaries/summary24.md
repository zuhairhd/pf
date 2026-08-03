> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 31: AI-1223 — Dashboard v2 (AI-Centric)**.

# Summary 24 — Card 31: AI-1223 Dashboard v2 (AI-Centric)

## What Was Done

Rebuilt the dashboard landing page around a single AI-centric "Today" payload, composed entirely from existing read-only AI CFO services/engines. The dashboard now leads with an AI brief, financial health snapshot, top proactive alerts, confidence-aware AI recommendation cards, and optimizer shortcuts — while the existing bills/subscriptions commitments widget and family goals widget are preserved unchanged. All new sections are strictly read-only and degrade safely when AI data is unavailable.

## Key Changes

- Added `app/services/dashboard_ai_service.py` (`DashboardAIService`), composing:
  - `HealthScoreService.calculate_score()` (health snapshot)
  - `CommitmentService.summary()` (bills/subscriptions summary)
  - `FamilyGoalService.get_active_family_goals_summary()` (goals summary)
  - `ProactiveAlertsEngine.preview()` (top alerts, no notifications created)
  - `SavingsOptimizer` (emergency fund insight) and `DebtOptimizer` (avalanche insight), each with graceful fallback when data is missing
- Added `app/schemas/dashboard.py` (`DashboardToday` and friends), mixing in the AI-1222 `ConfidenceFields`
- Added `GET /dashboard/api/today` (JSON, optional `?include_narrative=true`) and `GET /dashboard/partials/ai-today` (HTMX refresh) in `app/routers/dashboard.py`
- Added 5 new dashboard partial templates (`ai_today.html` wrapper + brief/health-snapshot/alerts/insights/quick-actions) and rebuilt `app/templates/dashboard/index.html` around them, keeping the existing `commitments_widget.html` and `family_goals_widget.html` includes untouched
- Added `dashboard_brief_prompt()` to `app/ai_cfo/llm/prompts.py` (aggregated summary only, no raw records)
- Deterministic-first narrative: no LLM call on a normal page view; optional LLM enhancement falls back safely and works with no `OPENAI_API_KEY`
- Small additive JS in `app/templates/ai/chat.html` to pre-fill (never auto-send) the chat input from a `?q=` param, so dashboard quick-action cards can deep-link a relevant question
- **Security fix:** found and fixed a pre-existing privacy defect in `ProactiveAlertsEngine._detect_goal_risks()` — it queried all active goals in the tenant without applying family goal visibility, so a "goal may miss deadline" alert could describe another family member's *private* goal. Fixed by filtering through `FamilyGoalService.can_view_goal()`, matching the pattern already used by every other AI CFO engine.
- Added `app/tests/integration/test_dashboard_ai.py` with 19 tests covering the API, page sections, HTMX partial, read-only/notification safety, LLM fallback, and tenant isolation

## Verification

- `python -m compileall app` — OK
- `alembic current` — `360b89eed134` (unchanged; no migration needed)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 44 tables, RLS active on 35
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **425 passed, 1 skipped**

## Next Recommended Card

**FAM-1303 — Family Budgets**
