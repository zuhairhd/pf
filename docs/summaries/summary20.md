> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 27: AI-1219 — Proactive Alerts**.

# Summary 20 — Card 27: AI-1219 Proactive Alerts

## What Was Done

Built a read-only, tenant-scoped proactive alerts engine that detects financial conditions from existing data and creates safe in-app notifications through the existing notification service. Duplicate alerts are prevented per entity/type/day, and optional LLM wording falls back to deterministic text when the LLM is unavailable.

## Key Changes

- Created `app/ai_cfo/engines/proactive_alerts.py`:
  - `ProactiveAlertType` enum: `bill_due_soon`, `bill_overdue`, `subscription_renewal_soon`, `high_spending_anomaly`, `negative_cash_flow`, `low_emergency_fund`, `goal_deadline_risk`, `debt_pressure`
  - `ProactiveAlertSeverity` enum: `info`, `warning`, `critical`
  - `ProactiveAlertCandidate` dataclass and `ProactiveAlertsEngine`
  - `preview()` returns candidates without creating notifications
  - `run()` creates in-app notifications with duplicate prevention
  - Optional LLM wording via existing `LLMClient`, `CostController`, and `SafetyFilter`
  - Deterministic fallback wording when LLM is disabled or over budget
- Updated `app/ai_cfo/engines/__init__.py` to export the new engine and enums.
- Added `proactive_alert_structured_prompt` to `app/ai_cfo/llm/prompts.py`.
- Added structured schemas to `app/schemas/ai.py`:
  - `ProactiveAlertTypeMeta`, `ProactiveAlertCandidateSchema`
  - `ProactiveAlertRunRequest`, `ProactiveAlertRunResponse`, `ProactiveAlertPreviewResponse`
- Extended `app/routers/ai.py` with:
  - `GET /ai/proactive-alerts/types`
  - `POST /ai/proactive-alerts/preview`
  - `POST /ai/proactive-alerts/run`
- Added `run_proactive_alerts_task` Celery stub to `app/tasks/notifications.py`.
- Fixed missing `Decimal` import in `app/config.py`.
- Added `app/tests/integration/test_proactive_alerts.py` with 18 integration tests covering all alert types, deduplication, auth, tenant isolation, read-only safety, LLM fallback, and RLS.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q --tb=short` — **354 passed, 1 skipped**

## Next Recommended Card

**AI-1220 — AI Chat Interface**
