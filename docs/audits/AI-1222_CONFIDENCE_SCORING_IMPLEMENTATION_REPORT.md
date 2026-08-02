# AI-1222 — AI Confidence Scoring Implementation Report

## Summary

Added a shared confidence-scoring utility and wired it into every AI CFO engine (What-If Simulator, Debt Optimizer, Savings Optimizer, Goal Planner, Proactive Alerts) plus the AI Chat service. Every AI-generated or AI-assisted response now carries a numeric `confidence_score` (0.0–1.0), a `confidence_label` (`high` / `medium` / `low`), a list of named `confidence_factors` with per-factor impact and explanation, and a human-readable `confidence_explanation`. The feature is read-only, additive to existing schemas, and does not touch financial records or the database schema — no Alembic migration was needed.

---

## Files Changed

- `app/ai_cfo/confidence.py` — new confidence scoring utility (core of this card).
- `app/ai_cfo/engines/whatif_simulator.py` — confidence factors wired into `_assemble_result`.
- `app/ai_cfo/engines/debt_optimizer.py` — confidence factors wired into `optimize()`.
- `app/ai_cfo/engines/savings_optimizer.py` — `_confidence` replaced by `_confidence_score` (kept as a thin backward-compatible wrapper) across all 5 modes.
- `app/ai_cfo/engines/goal_planner.py` — `_confidence` replaced by `_confidence_score` across all 5 modes; per-goal `incomplete_goal_data` factor added where a target date is missing.
- `app/ai_cfo/engines/proactive_alerts.py` — `ProactiveAlertCandidate` extended with confidence fields; every detection method now scores its candidates.
- `app/services/ai_chat.py` — memory commands, LLM success path, and rule-based fallback path each compute and attach a `ConfidenceScore`.
- `app/schemas/ai.py` — new `ConfidenceFactorSchema` / `ConfidenceFields` mixin; mixed into `ChatResponse`, all What-If/Debt/Savings/Goal Planner result schemas, `GoalPlanItem`, `ProactiveAlertCandidateSchema`; new `ConfidenceRulesResponse` schema.
- `app/routers/ai.py` — new `GET /ai/confidence/rules` route; `proactive_alerts_preview` now returns confidence fields per candidate.
- `app/tests/integration/test_confidence.py` — new test suite (24 tests) for the utility, all five engines, the new route, and safety/read-only guarantees.

No files were deleted. No existing response fields were removed or renamed.

---

## Model/Schema Changes

**No database schema changes.** Confidence scores are computed at request time and are not persisted. Alembic head remains `360b89eed134` (unchanged from AI-1221).

`app/schemas/ai.py` gained:
- `ConfidenceFactorSchema { name, impact, explanation }`
- `ConfidenceFields { confidence_score, confidence_label, confidence_factors, confidence_explanation }` — all fields `Optional`, default `None`.
- `ConfidenceRulesResponse { score_range, thresholds, base_score, labels, positive_factors, negative_factors }`

Every result schema that previously extended `BaseModel` directly now extends `ConfidenceFields` instead (which itself extends `BaseModel`), so all prior fields are unchanged and the new fields are additive and optional — existing clients that ignore them are unaffected.

---

## Confidence Scoring Rules

Implemented in `app/ai_cfo/confidence.py`:

- **Score range:** `0.0` – `1.0`, always clamped.
- **Base score:** `0.60` before any factors are applied (an unscored result defaults to "medium," never implying unwarranted certainty).
- **Label thresholds:**
  - `high`: score `>= 0.75`
  - `medium`: score `>= 0.45` and `< 0.75`
  - `low`: score `< 0.45`

Core building blocks:
- `ConfidenceLabel` — `high` / `medium` / `low` enum.
- `ConfidenceFactor` — `(name, impact, explanation)`.
- `ConfidenceScore` — `(score, label, factors, explanation)` with `.to_dict()` producing the exact field names used by the response schemas.
- `ConfidenceScorer` — fluent builder: `.add(name)`, `.add_if(condition, name)`, `.build()`.
- `calculate_confidence_score(factor_names, base_score=...)` / `confidence_from_factors(...)` — functional entry points.
- `label_from_score(score)`, `explain_confidence(factors, score, label)`.
- `confidence_rules()` — serializes thresholds/labels/factor library for the API route.

Unknown factor names are silently ignored rather than raising, so call sites can pass conditional factor names without extra branching.

---

## Factors Implemented

**Positive factors:** `deterministic_calculation`, `sufficient_history`, `recent_data`, `complete_required_inputs`, `direct_accounting_data`, `user_confirmed_memory`, `no_llm_dependency`.

**Negative factors:** `missing_interest_rate`, `missing_minimum_payment`, `low_transaction_history`, `stale_data`, `many_assumptions`, `forecast_long_horizon`, `llm_fallback`, `llm_unavailable`, `user_input_only`, `private_data_filtered`, `incomplete_goal_data`.

Each factor is a static, fixed record (name/impact/explanation) — engines only ever select *which* factors apply; the explanation text itself is never derived from user, memory, or transaction content, so confidence output cannot leak sensitive data (verified by `test_confidence_factor_explanations_match_registry`).

---

## AI Engines Updated

| Engine | Behavior |
|---|---|
| **What-If Simulator** | `deterministic_calculation` always applies. Both income and expense history present → `sufficient_history` + `direct_accounting_data` (high). One missing → `low_transaction_history` (medium). Both missing → `low_transaction_history` + `many_assumptions` (low). `forecast_long_horizon` added when `months > 36`. |
| **Debt Optimizer** | `deterministic_calculation` always applies. No assumed rates/minimums → `complete_required_inputs` + `direct_accounting_data` (high). Any assumed rate/minimum → corresponding negative factor. `forecast_long_horizon` if the payoff projection hits the 600-month cap; `many_assumptions` if risk warnings were raised. |
| **Savings Optimizer** | Same income/expense presence pattern as What-If, applied uniformly across all 5 modes (emergency fund, savings capacity, goal allocation, reduce spending, compare strategies). |
| **Goal Planner** | Same income/expense presence pattern, plus `incomplete_goal_data` whenever a goal (or any goal in a multi-goal/family plan) has no target date. Populated at both the top-level result and the per-goal `GoalPlanItem` level. |
| **Proactive Alerts** | Bill due/overdue and subscription renewal (direct source-table lookups) → high. Spending anomaly (30-day vs. 60-day baseline, ~2 months of data) → medium via `low_transaction_history`. Cash-flow risk → high if 90-day income history exists, else medium. Emergency fund risk → medium via `many_assumptions` (no category-level breakdown). Goal deadline already passed → high (direct fact); at-risk projection → medium (`many_assumptions`, linear extrapolation). Debt pressure → high when backed by structured `Loan` records, medium when falling back to liability accounts with an assumed 2% minimum payment. |

---

## LLM / Fallback Behavior

Per the card's safety rule ("LLM narrative should not increase numeric confidence by itself"):
- A successful LLM chat response does **not** get a `deterministic_calculation` or other positive-boost factor purely for succeeding — its score sits at the `0.60` base (medium) unless durable memory context was used, which adds a small `user_confirmed_memory` boost.
- When the LLM is unconfigured or a call fails and the chat service falls back to `_rule_based_response`, the response is scored with `no_llm_dependency` (it is deterministic code) **and** `llm_fallback` (a negative factor, since the LLM was the intended path and was unavailable). Net score is lower than an unboosted LLM-success response.
- Structured-output engines (What-If, Debt, Savings, Goal Planner) never let their optional LLM *narrative* affect the numeric confidence at all — confidence is computed entirely from the deterministic calculation inputs before the narrative is generated.

---

## Memory Behavior

- An explicit `remember that ...` / `forget ...` / `what do you remember?` chat command is a deterministic memory operation: scored with `deterministic_calculation` + `no_llm_dependency` (+ `user_confirmed_memory` for remember/query), landing at `high` confidence.
- When durable memory context is successfully injected into a free-form LLM chat prompt, `user_confirmed_memory` gives a small personalization boost — but only because the user explicitly confirmed that memory (via `remember that ...`), not because an LLM inferred it.
- Sensitive/filtered memory is never included in the prompt context in the first place (enforced by `AIMemoryService.get_prompt_context()`, unchanged from AI-1221), so no sensitive value ever reaches a confidence factor or explanation. Confidence factor explanations are static registry text, not derived from memory content — verified by test.

---

## Alert Behavior

See the Proactive Alerts row in the engine table above. Matches the three worked examples from the card spec:
- Overdue bill (direct table) → **high**.
- Spending anomaly from ~2 months of data → **medium**.
- Emergency fund estimate without category-level data → **medium** (within the requested "low/medium" band).

---

## Route Added

`GET /ai/confidence/rules` — requires authenticated tenant membership (`require_tenant_member`). Returns score range, high/medium/low thresholds, base score, labels, and the full positive/negative factor library (name, impact, explanation) so clients can render confidence consistently without hardcoding thresholds.

---

## Backward Compatibility

- All new fields are `Optional` and default to `None`; no existing field was renamed, removed, or repurposed.
- Each engine's legacy `confidence: str` field (`"high"|"medium"|"low"`) is preserved and is now derived from the same `ConfidenceScore.label` that produces the new `confidence_label` field, so the two are always consistent.
- `ChatResponse.confidence` (the existing `0-100` int field) is untouched; the new `confidence_score` (float `0.0-1.0`) and `confidence_label` fields sit alongside it.
- Existing hard assertion in `test_debt_optimizer.py::test_missing_interest_low_confidence` (`data["confidence"] in ("low", "medium")`) still passes.

---

## RLS / Tenant Safety

- No new database tables or columns were added, so no new RLS policies were required.
- Confidence computation reads only data already loaded by each engine under existing tenant-scoped queries; it does not issue any additional queries or bypass RLS.
- `test_confidence_endpoints_do_not_modify_financial_records` confirms account/goal/journal-entry counts are unchanged after calling the confidence route, What-If simulate, and proactive-alerts preview.
- Full suite (including all existing RLS tests) passes, confirming RLS/FORCE RLS remain intact.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `360b89eed134` (unchanged)
- `alembic upgrade head` — OK (no-op, already at head)
- `python scripts/inspect_db.py` — OK, 44 tables, RLS enabled on 35
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **406 passed, 1 skipped** (up from the AI-1221 baseline of 382 passed, 1 skipped — 24 new confidence tests, zero regressions)

`app/tests/integration/test_confidence.py` covers:
- Utility: label thresholds, score clamping, additive factor combination, unknown-factor tolerance, explanation generation, `ConfidenceScorer` builder, `confidence_rules()` shape.
- `/ai/confidence/rules`: requires auth, returns expected thresholds/factors.
- What-If: confidence fields present and internally consistent; no-history scenario is low confidence with `low_transaction_history`.
- Debt Optimizer: missing rate/minimum lowers confidence (low/medium); fully-specified loan is high confidence (`>= 0.75`).
- Savings Optimizer: no history is low confidence; full income/expense history is high confidence.
- Goal Planner: missing target date triggers `incomplete_goal_data` at both the result and per-goal level.
- Proactive Alerts: overdue bill is high confidence (`>= 0.75`); spending anomaly (when triggered) is medium with `low_transaction_history`.
- AI Chat: explicit `remember` command is high confidence with `no_llm_dependency`; free-form fallback response includes `llm_fallback`.
- Safety: confidence factor explanations always match the static registry (no leakage); confidence-related endpoints create/modify zero accounts, goals, or journal entries.

---

## Known Limitations

- Confidence scores are computed per-request and not persisted or logged for later analysis (PLAN_V2's "log confidence scores for analysis" and "adjust confidence thresholds based on user feedback" acceptance criteria are out of scope for this card and deferred).
- Historical-accuracy-based confidence adjustment (comparing past projections to actual outcomes) is not implemented; confidence currently reflects input/data quality and calculation method only, not track record.
- Per-goal confidence in multi-goal/family plans reuses the same snapshot-level factors as the top-level result rather than being fully independent per goal (only `incomplete_goal_data` is goal-specific).
- The `/ai/confidence/rules` route is read-only reference data; there is no UI surface built in this card to visually render confidence badges (left to the frontend).

---

## Recommended Next Card

**AI-1223 — Dashboard v2 (AI-Centric)**

With insights, chat, memory, and now confidence scoring in place, the next step is redesigning the dashboard around AI-generated insights, recommendations, and the health score — surfacing confidence badges alongside those insights using the `/ai/confidence/rules` contract established here.
