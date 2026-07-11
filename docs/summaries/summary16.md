> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 23: AI-1214 — What-If Simulator**.

# Summary 16 — Card 23: AI-1214 What-If Simulator

## What Was Done

Built a read-only, tenant-scoped What-If Simulator that models financial scenarios using existing accounting data and returns deterministic projections with an optional LLM narrative.

## Key Changes

- Created `app/ai_cfo/engines/whatif_simulator.py`:
  - `WhatIfScenarioType` enum with seven supported scenarios
  - `FinancialSnapshot` and projection builder
  - `WhatIfSimulator` with handlers for savings, expense reduction, income increase, emergency expense, subscription cancellation, goal contribution increase, and new monthly payment scenarios
  - Account/subscription/goal validation using existing family permission services
  - Deterministic fallback narrative and optional LLM narrative via existing `LLMClient`, `CostController`, and `SafetyFilter`
- Added `what_if_structured_prompt` to `app/ai_cfo/llm/prompts.py`.
- Added structured schemas to `app/schemas/ai.py`:
  - `WhatIfScenarioRequest` discriminated union
  - `WhatIfResult`, `WhatIfSimulationResponse`, `WhatIfCompareRequest`, `WhatIfCompareResponse`
- Extended `app/routers/ai.py` with:
  - `GET /ai/what-if/scenarios`
  - `POST /ai/what-if/simulate`
  - `POST /ai/what-if/compare`
- Fixed `app/middleware/error_handling.py` to serialize `Decimal` values in validation-error responses via `jsonable_encoder`.
- Added `app/tests/integration/test_whatif.py` with 20 integration tests covering all scenarios, validation, auth, tenant isolation, read-only safety, and RLS.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `5e8169dd3017`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -v --tb=no` — **279 passed, 1 skipped**

## Next Recommended Card

**AI-1211 — Debt Optimizer**
