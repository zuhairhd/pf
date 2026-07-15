# AI-1219 Proactive Alerts Implementation Report

## Summary

Implemented a tenant-scoped, read-only proactive alerts engine for the AI Personal CFO. The engine detects important financial conditions from existing accounting and planning data, creates safe in-app notifications through the existing `NotificationDeliveryService`, prevents duplicate alerts per entity/day, and optionally rewords alerts through the existing LLM client with deterministic fallback. No financial records are modified.

## Files Changed

- `app/ai_cfo/engines/proactive_alerts.py` — new alert detection engine.
- `app/ai_cfo/engines/__init__.py` — exported engine symbols.
- `app/ai_cfo/llm/prompts.py` — added `proactive_alert_structured_prompt`.
- `app/schemas/ai.py` — added proactive alert request/response schemas.
- `app/routers/ai.py` — added `/ai/proactive-alerts/*` routes.
- `app/tasks/notifications.py` — added `run_proactive_alerts_task` Celery stub.
- `app/config.py` — fixed missing `Decimal` import (proactive-alert defaults already present).
- `app/tests/integration/test_proactive_alerts.py` — new integration tests.

## Model/Schema Changes

No database migration was required. The implementation reuses the existing `Notification` model and its enum values (`BILL_DUE`, `BILL_OVERDUE`, `SUBSCRIPTION_RENEWAL`, `AI_INSIGHT`, `GOAL_MILESTONE`, `ANOMALY_DETECTED`).

New Pydantic schemas:

- `ProactiveAlertTypeMeta`
- `ProactiveAlertCandidateSchema`
- `ProactiveAlertRunRequest`
- `ProactiveAlertRunResponse`
- `ProactiveAlertPreviewResponse`

## Alert Types Implemented

| Alert Type | Trigger | Severity |
|------------|---------|----------|
| `bill_due_soon` | Unpaid bill due within `ALERT_BILL_DUE_DAYS` | warning/critical |
| `bill_overdue` | Unpaid bill past due date | warning/critical |
| `subscription_renewal_soon` | Active subscription renewing within `ALERT_SUBSCRIPTION_RENEWAL_DAYS` | info/warning |
| `high_spending_anomaly` | Last 30 days expenses > baseline + `ALERT_SPENDING_ANOMALY_PERCENT` | warning |
| `negative_cash_flow` | 90-day average net cash flow below `ALERT_LOW_CASHFLOW_THRESHOLD` | warning/critical |
| `low_emergency_fund` | Liquid assets cover fewer months than `ALERT_EMERGENCY_FUND_MONTHS` | warning/critical |
| `goal_deadline_risk` | Active goal cannot meet target date at current contribution | warning/critical |
| `debt_pressure` | Debt-to-minimum-income ratio exceeds threshold or payment does not cover interest | warning/critical |

## Configuration

Config variables (already present in `app/config.py` and `.env.example`):

- `PROACTIVE_ALERTS_ENABLED=true`
- `ALERT_BILL_DUE_DAYS=3`
- `ALERT_SUBSCRIPTION_RENEWAL_DAYS=7`
- `ALERT_SPENDING_ANOMALY_PERCENT=30`
- `ALERT_LOW_CASHFLOW_THRESHOLD=0`
- `ALERT_EMERGENCY_FUND_MONTHS=1`
- `ALERT_DEBT_TO_INCOME_THRESHOLD=0.36`

## Routes Added

- `GET /ai/proactive-alerts/types` — supported alert types and thresholds (tenant member).
- `POST /ai/proactive-alerts/preview` — return detected candidates without persisting notifications (tenant member).
- `POST /ai/proactive-alerts/run` — detect and create in-app notifications, deduplicated by day (tenant admin/owner).

## Duplicate Prevention

`run()` checks for an existing notification for the same `(tenant_id, user_id, notification_type, related_entity_type, related_entity_id)` created today before creating a new one. Repeated runs skip duplicates and report `skipped` count.

## LLM Wording / Fallback

When `include_llm_wording=true`, the engine calls the existing `LLMClient` through `proactive_alert_structured_prompt`. If the client is unconfigured, the cost budget is exhausted, or an `LLMError` occurs, the original deterministic message is used. Tests pass without an OpenAI API key.

## RLS / Tenant Safety

- All detection queries filter by `tenant_id`.
- Routes use `get_db_with_tenant_context` and `require_tenant_member` / `require_tenant_admin`.
- Cross-tenant preview/run is blocked by RLS and explicit tenant filtering.
- The integration test suite verifies RLS remains active on `notifications`.

## Read-Only Safety

- The engine never creates transactions, journal entries, account changes, goal changes, or bill/subscription changes.
- `run()` only creates `Notification` records.
- Tests assert journal-entry count is unchanged after a run.

## Test Results

- Proactive alert tests: **18 passed**.
- Full suite: **354 passed, 1 skipped**.

Tests cover:

- auth requirements
- alert type catalog
- preview without notification creation
- run creates notifications
- run requires admin/owner
- duplicate-run deduplication
- bill due/overdue alerts
- subscription renewal alert
- high-spending anomaly
- negative cash-flow alert
- low emergency fund alert
- goal deadline risk alert
- debt pressure alert
- read-only safety
- LLM fallback without API key
- cross-tenant isolation
- RLS enforcement

## Known Limitations

- Real-time push/email delivery is not implemented; only in-app notifications are created.
- Background scheduling relies on the Celery stub `run_proactive_alerts_task`.
- Spending baseline is rule-based (recent 60-day monthly average), not a statistical anomaly model.
- Debt pressure uses loan records and liability accounts with safe assumptions when minimum payment or interest rate is missing.
- Family visibility rules for goals are applied at query time by tenant filtering; deeper family-role scoping can be added when private goals should not alert family viewers.

## Recommended Next Card

**AI-1220 — AI Chat Interface** (next card in `PLAN_V2.md`, priority Critical).
