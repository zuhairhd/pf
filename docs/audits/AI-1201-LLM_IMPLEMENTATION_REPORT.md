# AI-1201-LLM — OpenAI LLM Client Integration Report

**Project:** PF AI Personal Finance SaaS  
**Card:** AI-1201-LLM  
**Date:** 2026-07-03  
**Planning Reference:** `PLAN_V2.md`

---

## Summary

Integrated an async OpenAI LLM client into the AI CFO layer. The integration is guarded by tenant-scoped cost control, safety filtering, and rule-based fallback logic. When `OPENAI_API_KEY` is configured, chat, insights, daily briefs, and what-if scenarios use the LLM; otherwise the existing rule-based engines continue to work unchanged.

No database schema changes were required because `AITokenUsage` already existed. RLS and FORCE RLS remain active on all tenant-scoped tables.

---

## Files Changed

- `requirements.txt` — added `openai>=1.0.0`
- `app/ai_cfo/__init__.py` (new)
- `app/ai_cfo/llm/__init__.py` (new)
- `app/ai_cfo/llm/client.py` (new)
- `app/ai_cfo/llm/prompts.py` (new)
- `app/ai_cfo/llm/cost_control.py` (new)
- `app/ai_cfo/llm/safety.py` (new)
- `app/services/ai_chat.py` — LLM path + fallback
- `app/services/ai_orchestrator.py` — LLM-augmented insights and daily brief
- `app/services/ai_forecast.py` — LLM-augmented what-if scenarios
- `app/routers/ai.py` — fixed missing `request` parameter, switched to `get_db_with_tenant_context`
- `app/middleware/tenant_scoping.py` — cast `tenant_id`/`user_id` to integers
- `app/tests/unit/test_llm_safety.py` (new)
- `app/tests/unit/test_llm_client.py` (new)
- `app/tests/integration/test_llm_integration.py` (new)
- `docs/audits/AI-1201-LLM_IMPLEMENTATION_REPORT.md` (this file)
- `docs/audits/PLAN_V2_CARD_STATUS.md`
- `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md`

---

## Data Model Changes

No Alembic migration was required.

- `AITokenUsage` (existing table) records per-tenant LLM usage.
- `AIInsight`, `AIReport`, `AIChatSession`, `AIChatMessage` are reused unchanged.

**Alembic revision:** N/A.

---

## LLM Module Architecture

### `app/ai_cfo/llm/client.py`

- Async OpenAI client wrapper (`LLMClient`).
- Configured from `OPENAI_API_KEY` / `OPENAI_MODEL` settings.
- Retries on timeout/rate-limit (exponential backoff).
- Structured response (`LLMResponse`) with token counts and estimated USD cost.
- Raises `LLMError` when not configured or on API failure.

### `app/ai_cfo/llm/prompts.py`

- System prompt establishes the AI as an educational financial coach.
- Prompt builders for:
  - `chat_prompt`
  - `insight_prompt`
  - `daily_brief_prompt`
  - `what_if_prompt`
- Default disclaimer included in outputs.

### `app/ai_cfo/llm/cost_control.py`

- `CostController` enforces per-tenant daily limits based on `Organization.plan`.
- Free-plan default: `AI_MAX_REQUESTS_PER_DAY_FREE`.
- Premium/Family/Professional default: `AI_MAX_REQUESTS_PER_DAY_PREMIUM`.
- Records usage to `AITokenUsage` with model, tokens, cost, and request type.

### `app/ai_cfo/llm/safety.py`

- `SafetyFilter` blocks/flags:
  - Requests for specific investment advice (stocks, crypto, forex).
  - Tax evasion, fraud, or guaranteed-return claims.
  - Output containing ticker recommendations.
- Injects the educational-disclaimer on every output.

---

## Integration Points

### AI Chat (`app/services/ai_chat.py`)

- Checks user input with `SafetyFilter`.
- Checks tenant daily limit with `CostController`.
- Calls `LLMClient.complete()` when configured and within quota.
- Records usage and stores the response in `AIChatMessage`.
- Falls back to keyword-based responses when LLM is unavailable, unconfigured, or over quota.

### AI Orchestrator (`app/services/ai_orchestrator.py`)

- `_generate_insights()` now tries LLM first, parses JSON list of insights, records usage, and falls back to rule-based insights.
- `_generate_daily_brief_content()` uses LLM when configured/allowed, otherwise uses the existing formatter.
- Added `_parse_llm_insights`, `_map_insight_type`, `_map_insight_priority`, and `_rule_based_insights` helpers.

### AI Forecast / What-If (`app/services/ai_forecast.py`)

- `simulate_scenario()` tries LLM first and falls back to existing rule-based simulators.
- Added `_gather_financial_data()` helper for prompt context.

---

## Bug Fixes Included

- `app/routers/ai.py`: added missing `request: Request` parameter to `chat_with_ai`; switched all AI routes to `get_db_with_tenant_context` so RLS tenant context is set for tenant-scoped writes.
- `app/middleware/tenant_scoping.py`: cast JWT `tenant_id` and `sub` claims to integers so they match the integer foreign-key columns (fixed `ai_chat_sessions` insert failures).

---

## Test Results

- **Baseline (before this card):** 74 passed, 1 skipped
- **After this card:** **89 passed, 1 skipped**
- **New LLM tests:** 15
  - 6 unit tests for safety filter
  - 3 unit tests for LLM client (mocked)
  - 6 integration tests for cost control, chat fallback, investment-advice rejection, insight generation, and what-if fallback

All verification commands passed:
- `python -m compileall app`
- `alembic current` → `9ee380da96d5 (head)`
- `alembic history`
- `alembic upgrade head`
- `python scripts/inspect_db.py` → 42 tables, 32 RLS-enabled, FORCE RLS active
- `python scripts/seed_default_data.py --dev`
- `python -m pytest -q` → exit code 0

---

## Configuration

Required environment variables:
- `OPENAI_API_KEY` — API key (optional; app works without it via fallback).
- `OPENAI_MODEL` — defaults to `gpt-4o-mini`.
- `OPENAI_MODEL_PREMIUM` — reserved for future premium routing.
- `AI_MAX_REQUESTS_PER_DAY_FREE` — defaults to 5.
- `AI_MAX_REQUESTS_PER_DAY_PREMIUM` — defaults to 50.

No secrets were committed. `.env` remains ignored.

---

## Known Limitations

- LLM insight generation relies on JSON output from the model; malformed JSON falls back to rule-based insights.
- No streaming responses yet.
- No prompt-versioning or A/B testing framework yet.
- Cost estimates use hardcoded pricing; update `LLMClient.PRICING` when OpenAI pricing changes.
- Category suggestion from SMS/CSV imports is still rule-based, not LLM-driven.

---

## Security and Safety Compliance

- ✅ RLS remains enabled on all tenant-scoped AI tables.
- ✅ FORCE ROW LEVEL SECURITY remains enabled.
- ✅ No universal admin bypass introduced.
- ✅ No real personal financial data used in tests.
- ✅ No secrets committed.
- ✅ Safety filter blocks investment advice requests and injects disclaimers.
- ✅ Per-tenant usage limits prevent runaway API costs.

---

## Recommended Next Card

**BILL-800 / SUB-900 — Build Bills and Subscriptions Routers**

With auth, RLS, imports, tests, and LLM integration in place, the next high-value feature is full CRUD routers for bills and subscriptions. These are core "Financial Life" features needed for the MVP and the models already exist.

After bills/subscriptions, priorities remain:
- **AUTH-305** — Tenant member invitation flow.
- **IMP-701-EXCEL** — Excel import parser.
- **NOTIF-1600** — SMTP-backed email notifications.
