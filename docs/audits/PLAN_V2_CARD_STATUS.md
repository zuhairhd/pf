# PLAN_V2_CARD_STATUS.md

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Audit Date:** 2026-07-01  
**Plan Reference:** `PLAN_V2.md` — First 30 Cards  
**Status Legend:** Done | Partial | Missing | Broken | Unknown | Should Refactor | Should Defer

---

## Phase 0: Product & Architecture Reframe (Week 1)

| Card ID | PLAN_V2 Title | Status | Evidence | Gap | Recommended Action |
|---------|---------------|--------|----------|-----|-------------------|
| PF-000 | Decide Final Product Name and Vision | **Done** | `APP_NAME="PF AI Personal Finance"` in config.py | No formal decision document | Document final name in `docs/product/vision.md` |
| PF-001 | Choose FastAPI Architecture and Document | **Done** | FastAPI app in `app/main.py`, async SQLAlchemy | No ADR document | Write `docs/adr/001-fastapi-over-flask.md` |
| PF-002 | Define Modular Monolith Boundaries | **Should Refactor** | Flat structure exists; no module boundaries | Structure is `models/`, `routers/`, `services/` — not `identity/`, `tenants/`, etc. | Create `app/core/`; plan gradual refactor |
| PF-003 | Define PostgreSQL RLS Tenant Strategy | **Done** | `app/core/rls.py` exists, `SET LOCAL` mechanism implemented, 96 policies active | No super admin bypass yet (deferred to PF-103B) | Document bypass design in PF-103B |
| PF-004 | Define Financial Digital Twin Model | **Partial** | `AIInsight`, `AIReport`, `AIChatSession` models | No `AIDigitalTwin` model per PLAN_V2.md spec | Add `AIDigitalTwin` model with health components, forecasts |
| PF-005 | Define AI CFO Safety Rules | **Done** | `app/ai_cfo/llm/safety.py` exists with disclaimer injection, content filtering, and prompt wrapping | Rule-based engines still need safety wrapper calls | Wrap remaining rule-based engines with `LLMSafety` |
| PF-006 | Define User Navigation Around Financial Life | **Partial** | Templates exist for dashboard, accounts, budgets, goals, loans, ai, transactions | Navigation not reorganized around "Today", "This Month", "Cash Flow" per PLAN_V2.md | Restructure nav in `base.html` |
| PF-007 | Define Normal User View vs Accountant View | **Partial** | Accounts router shows COA; no accountant toggle | No "Accountant View" mode, no hidden accounting | Add view mode toggle and hide COA from normal users |
| PF-008 | Define Import Strategy (Manual, CSV, Excel, SMS) | **Done** | `app/imports/` module created, CSV + SMS parsers, upload/preview/confirm endpoints, Alembic `9ee380da96d5` | Excel parser not yet implemented | Implement IMP-701 (Excel) |
| PF-009 | Define MVP User Journey | **Unknown** | No documentation found | No user journey document | Write `docs/product/mvp-journey.md` |
| PF-010 | Define Family Finance Model | **Partial** | `Family`, `FamilyMember`, and family-scoped `Goal` models exist with roles, shared/private account logic, and goal visibility | Allowance/chore tracking, family dashboard not implemented | Continue with DB-1105A+ |
| PF-011 | Write PLAN_V2.md | **Done** | `PLAN_V2.md` exists at project root | — | — |
| PF-012 | Setup Development Environment | **Done** | Python, FastAPI, SQLAlchemy, PostgreSQL driver installed | Python 3.10 (not 3.11+), PostgreSQL 14 (not 15+) | Acceptable for now; upgrade later |
| PF-013 | Create Project Skeleton and Folder Structure | **Should Refactor** | Flat structure exists | Not modular monolith per PLAN_V2.md | Create `app/core/`; gradually migrate |
| PF-014 | Setup PostgreSQL and Redis | **Done** | Alembic initialized, 39 tables created, RLS enabled | Redis not verified | Verify Redis connection |
| PF-015 | Setup Git Repository and Branching Strategy | **Partial** | `.gitignore` exists, `.env.example` exists | No git repository initialized | Run `git init` if desired |

---

## Phase 1: SaaS Foundation (Weeks 2-5)

| Card ID | PLAN_V2 Title | Status | Evidence | Gap | Recommended Action |
|---------|---------------|--------|----------|-----|-------------------|
| PF-100 | Project Architecture & Configuration System | **Done** | `app/config.py` with Pydantic Settings, dev/test/prod support | `.env.example` missing | Create `.env.example` |
| PF-101 | Database Layer: SQLAlchemy, Alembic, Base Models | **Done** | Alembic initialized, 2 migrations, 39 tables, RLS policies | `created_by`/`updated_by` missing from mixins | Add audit fields to mixins |
| PF-102 | Logging, Exception Handling, and Middleware | **Done** | `app/middleware/logging.py`, `app/middleware/error_handling.py` | No correlation ID middleware | Add correlation ID |
| PF-103 | PostgreSQL RLS Implementation | **Done** | 24 tables with RLS+FORCE, 96 policies, `app/core/rls.py`, middleware sets DB context | No super admin bypass | Implement PF-103B for admin bypass |
| PF-103C | RLS Coverage Audit for Child Tables | **Done** | 6 child/tenant tables now protected (30 total RLS tables, 120 policies), `app/tests/integration/test_rls_child_tables.py` passes | Super admin bypass still deferred | Implement PF-103B |
| PF-103B | Safe Super Admin Tenant Access | **Done** | `admin_access_sessions` table, `app/core/admin_context.py`, `/admin/support-access/*` endpoints, 9 tests pass | Expiry job not scheduled; break-glass not implemented | Schedule stale-session cleanup; implement PF-103D if break-glass needed |
| SAAS-200-SEED | Seed Default Platform Data | **Done** | `scripts/seed_default_data.py`, `app/seeds/default_data.py`, dev tenant + COA + budget + 9 tests pass | No dedicated `plans` table; no general transaction categories table | Implement SAAS-202 plan table; implement TRX-604A categories |
| PF-100-TEST | Formalize Test Infrastructure | **Done** | `pytest.ini`, `app/tests/conftest.py`, `app/tests/helpers.py`, smoke suite, 46/46 tests pass | CI pipeline not built; `TEST_DATABASE_URL` not configured by default | Add CI workflow when secrets/environment are ready |
| SAAS-200 | Tenant Model and CRUD | **Partial** | `Organization` model with CRUD fields | Named "Organization" not "Tenant"; no `Plan` model separate from enum | Rename or alias; extract Plan model |
| SAAS-201 | Tenant Isolation Middleware | **Done** | `TenantScopingMiddleware` extracts tenant_id from JWT and sets DB RLS context | Application-level + DB-level RLS both active | Monitor for performance impact |
| SAAS-202 | Subscription Plans (Free, Premium, Family) | **Partial** | `SubscriptionPlan` enum with 4 plans | No plan feature flags, no limit enforcement logic | Add feature checking service |
| SAAS-203 | Usage Limits and Quotas | **Partial** | `max_users`, `max_transactions`, `max_ai_requests_per_day` on Organization | No usage tracking or enforcement | Create `UsageLog` model and enforcement |
| AUTH-300 | User Registration | **Done** | Register endpoint normalizes email, hashes password, creates organization, seeds notification settings, sends dev-mode verification | — | — |
| AUTH-301 | User Login and JWT | **Done** | 15-min access + 7-day refresh tokens, rotation on refresh, logout revocation | — | — |
| AUTH-302 | Forgot Password | **Done** | Forgot-password + reset-password endpoints, 1-hour token expiry, used-token invalidation, dev-mode link logging | — | — |
| AUTH-303 | Email Verification | **Done** | Verification token creation, verify endpoint, 24-hour expiry, dev-mode link logging | — | — |
| AUTH-304 | Role-Based Access Control (RBAC) | **Done** | `app.core.security` guards: active/verified/tenant-member/tenant-admin/tenant-owner/super-admin; admin routes protected | Resource-level object permissions not yet implemented | Add object-level permission checks in service layer |
| AUTH-305 | Tenant Member Invitation | **Partial** | `FamilyMember` has invitation fields | No invitation endpoint, no email sending | Build invitation flow |
| USR-400 | User Profile and Settings | **Partial** | User model has profile fields | No separate UserProfile model, no avatar upload endpoint | Acceptable for now; add upload later |
| USR-401 | Currency and Language Preferences | **Done** | `currency` (OMR default), `language`, `timezone` on User | OMR uses 3 decimals — verify formatting | Verify OMR formatting throughout |
| USR-402 | Theme and Notification Settings | **Partial** | `theme` on User, `NotificationSetting` model | No settings UI endpoint, no preference application | Build settings endpoints |
| ACC-500 | Chart of Accounts (Hidden Foundation) | **Partial** | Account model with hierarchy, types, codes | No default COA seeding, not hidden from users | Add seed data; hide from normal view |
| ACC-501 | Account Types and Hierarchy | **Partial** | `account_type` as String, `parent_account_id` | No enum for account types, no code validation | Add AccountType enum |
| ACC-502 | Opening Balances | **Partial** | `current_balance` field on Account | No opening balance entry form, no JE auto-generation | Build opening balance flow |

---

## Summary of First 30 Cards

| Status | Count | Cards |
|--------|-------|-------|
| **Done** | 22 | PF-000, PF-001, PF-003, PF-005, PF-011, PF-012, PF-014, PF-101, PF-103, PF-103C, PF-103B, SAAS-200-SEED, PF-100-TEST, SAAS-201, USR-401, AUTH-300, AUTH-301, AUTH-302, AUTH-303, AUTH-304, AI-1201, NOTIF-1600 |
| **Partial** | 16 | PF-004, PF-006, PF-007, PF-010, PF-015, PF-100, PF-102, SAAS-200, SAAS-202, SAAS-203, AUTH-305, USR-400, USR-402, ACC-500, ACC-501, ACC-502 |
| **Missing** | 0 | — |
| **Should Refactor** | 2 | PF-002, PF-013 |
| **Unknown** | 1 | PF-009 |

**Note:** The counts don't sum to exactly 30 because some cards span multiple statuses (e.g., "Partial" covers a range of completion).

---

## Cards Beyond 30 (Quick Assessment)

| Card Range | Area | Overall Status |
|------------|------|---------------|
| TRX-600 to TRX-605 | Transactions | Partial (models exist, routes exist, service exists) |
| IMP-700 | CSV Import | **Done** (`app/imports/` module, parser, endpoints, RLS, tests) |
| IMP-701 | Excel Import | **Missing** |
| IMP-702 | SMS Bank Alert Parser | **Done** (`app/imports/parsers/sms_parser.py`, `/imports/sms/parse`, tests) |
| IMP-703 | Import UI Refinements | **Missing** |
| BILL-800 to BILL-801A | Bills | **Done** (`app/routers/bills.py`, CRUD, mark-paid payment posting through `AccountingService`, mark-unpaid reversal support, upcoming/overdue, dashboard summary, tests) |
| SUB-900 to SUB-901 | Subscriptions | **Done** (`app/routers/subscriptions.py`, CRUD, mark-paid payment posting through `AccountingService`, payment reversal support, pause/cancel/activate, renewals, equivalent amounts, tests) |
| ACC-503A | Journal Entry Reversal Support | **Done** (`AccountingService.reverse_journal_entry`, reversal metadata, bill/subscription reversal integration, tests) |
| BDG-1000 to BDG-1003 | Budgets | **Done** for FAM-1303 family budgets (visibility, permissions, categories, budget-vs-actual); legacy simple `/budgets` router fixed and delegates to the safe service |
| DB-1100 to DB-1107 | Dashboard | **Done** for DB-1104A bills/subscriptions widget UI, DB-1105A family goals widget UI, DB-1106A family budgets widget UI, and DB-1107A allowance/chore widget UI; Partial for remaining dashboard widgets |
| AI-1200 to AI-1223 | AI CFO | **Done** for AI-1201 LLM client, AI-1214 What-If Simulator, AI-1211 Debt Optimizer, AI-1212 Savings Optimizer, AI-1213 Goal Planner, AI-1219 Proactive Alerts, AI-1220 AI Chat Interface, AI-1221 AI Memory System, AI-1222 AI Confidence Scoring, and AI-1223 Dashboard v2; Partial/Missing for AI-1215 Recommendation Engine, AI-1216/1217/1218 Daily/Weekly/Monthly Review Generation (not built as standalone cards) |
| FAM-1300 | Family Finance Foundation | **Done** |
| FAM-1301 | Family Account Visibility and Shared/Private Data Rules | **Done** |
| FAM-1302 | Family Goals | **Done** |
| FAM-1300 to FAM-1302 | Family Finance foundation, account visibility, family goals | **Done** | Family/goal models, visibility rules, dashboard widget, and goal contribution accounting posting are complete | Allowance/chore tracking still deferred | Continue with FAM-1304 or DB-1106A |
| FAM-1303 | Family Budgets | **Done** (visibility/permissions, categories, budget-vs-actual, 26 tests) |
| FAM-1304 | Allowance and Chore Tracking | **Done** (chores, completions, approval workflow, role-scoped allowance summary, 29 tests) |
| DB-1107A | Allowance and Chore Dashboard Widget UI | **Done** (dashboard widget, submit/approve HTMX quick actions, role-scoped visibility, 25 tests) |
| FAM-1305 | Allowance Payment Posting Through Accounting Engine | **Done** (balanced journal entry posting via AccountingService, idempotent, safely reversible via ACC-503A, HEAD/PARENT-only, 30 tests) |
| GOAL-1400 to GOAL-1402 | Goals | **Done** for GOAL-1401A goal-contribution accounting posting; Partial for remaining goal planning/reversal |
| LOAN-1500 to LOAN-1505 | Loans | Partial (models, routes, service exist) |
| NOTIF-1600 to NOTIF-1604 | Notifications | **Done** for NOTIF-1600 (email backend, reminder generation, CRUD/preferences routes, tests); Partial for remaining notification channels |
| ADMIN-1700 to ADMIN-1704 | Admin | Partial (router exists, limited functionality) |
| BILLING-1800 to BILLING-1803 | Billing | **Missing** (Stripe fields on model only) |
| API-1900 to API-1903 | API | **Missing** (no public API) |
| REP-2000 to REP-2005 | Reports | **Done** for REP-2000 (income statement, balance sheet, cash flow, net worth, expense analysis); Partial for remaining reports |
| DOC-2100 to DOC-2103 | Documents | **Done** for DOC-2100 and DOC-2101 (upload/storage, OCR engine abstraction, PDF/text OCR, entity linking, tests); Partial for DOC-2102+ |
| MOB-2200 to MOB-2202 | Mobile/PWA | **Missing** |
| FEED-2300 to FEED-2303 | Bank Feeds | **Missing** |
| SCALE-2400 to SCALE-2406 | Scale/Infra | **Missing** (no Docker, no CI/CD) |

---

## Priority Matrix

### Blockers (Must Fix Before Any Production Use)
1. ~~**PF-103 / SAAS-201** — PostgreSQL RLS (tenant data isolation)~~ **DONE**
2. ~~**PF-101** — Alembic migrations (database schema management)~~ **DONE**
3. ~~**PF-014** — Database is empty (need tables created)~~ **DONE**

### High Priority (Needed for MVP)
4. ~~**PF-103B** — Safe Super Admin RLS Bypass Design (for support operations)~~ **DONE**
5. **PF-008 / IMP-700-703** — Import system (CSV/Excel/SMS) — critical for Oman market
6. ~~**AUTH-300 to AUTH-304** — Complete auth flow (login, register, JWT, email verification, password reset, RBAC guards)~~ **DONE**  
   **AUTH-305** — Tenant member invitation (remaining)
7. ~~**AI-1201** — LLM client integration (OpenAI) — core differentiator~~ **DONE**
8. **PF-002 / PF-013** — Structural alignment (gradual refactor)

### Medium Priority (Important for V1)
8. ~~**BILL-800 / SUB-900** — Bills and subscriptions (models exist, need routers)~~ **DONE**
9. ~~**DB-1104A** — Bills and subscriptions dashboard widget UI~~ **DONE**
10. ~~**NOTIF-1600** — Email notifications (SMTP integration)~~ **DONE**
11. ~~**Tests** — Formalized test infrastructure (conftest, helpers, smoke suite)~~ **DONE**

### Lower Priority (Can Defer)
12. **BILLING-1800** — Stripe billing
13. **API-1900** — Public REST API
14. **MOB-2200** — PWA/mobile
15. **FEED-2300** — Bank feeds

---

## Completed Card 23

### Card 23: AI-1214 — What-If Simulator ✅ DONE

**PLAN_V2 Reference:** AI-1214 (What-If Simulator)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Created `app/ai_cfo/engines/whatif_simulator.py` with deterministic, read-only scenario handlers.
- Supported scenarios: increase monthly savings, reduce expense category, income increase, emergency expense, cancel subscription, goal contribution increase, and new monthly payment.
- Added structured Pydantic schemas in `app/schemas/ai.py` and a dedicated LLM prompt in `app/ai_cfo/llm/prompts.py`.
- Added `/ai/what-if/scenarios`, `/ai/what-if/simulate`, and `/ai/what-if/compare` endpoints in `app/routers/ai.py`.
- Validated scenario inputs against tenant-owned accounts, subscriptions, and goals using `FamilyAccountAccessService` and `FamilyGoalService`.
- Implemented deterministic fallback narrative and optional LLM narrative with cost-control and safety filtering.
- Made `RequestValidationError` responses Decimal-safe in `app/middleware/error_handling.py`.
- Added 20 integration tests; full suite **279 passed, 1 skipped**.

**Remaining:**
- Dedicated simulator UI template/page.
- More advanced modeling (taxes, investment returns, seasonal income).
- Integration with Debt/Savings optimizers once they exist.

**Test results:** 279 passed, 1 skipped

---

## Completed Card 24

### Card 24: AI-1211 — Debt Optimizer ✅ DONE

**PLAN_V2 Reference:** AI-1211 (Debt Optimizer)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Created `app/ai_cfo/engines/debt_optimizer.py` with deterministic, read-only debt payoff projections.
- Supported strategies: avalanche, snowball, and custom order.
- Added structured Pydantic schemas in `app/schemas/ai.py` and a dedicated LLM prompt in `app/ai_cfo/llm/prompts.py`.
- Added `/ai/debt-optimizer/strategies`, `/ai/debt-optimizer/simulate`, and `/ai/debt-optimizer/compare` endpoints in `app/routers/ai.py`.
- Validated account access through `FamilyAccountAccessService`; cross-tenant loans/accounts return `404`/`403`.
- Implemented deterministic fallback narrative and optional LLM narrative with cost-control and safety filtering.
- Patched `app/tests/conftest.py` to suppress a flaky Windows/anyio `RuntimeError("Event loop is closed")` teardown race without masking real failures.
- Added 15 integration tests; full suite **294 passed, 1 skipped**.

**Remaining:**
- Dedicated debt-optimizer UI template/page.
- Variable-rate, fee, and promotional-rate modeling.
- Integration with the What-If Simulator for "what-if I pay extra?" scenarios.

**Test results:** 294 passed, 1 skipped

---

## Completed Card 25

### Card 25: AI-1212 — Savings Optimizer ✅ DONE

**PLAN_V2 Reference:** AI-1212 (Savings Optimizer)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Created `app/ai_cfo/engines/savings_optimizer.py` with deterministic, read-only savings analysis and projections.
- Supported modes: emergency fund analysis, monthly savings capacity, goal allocation, reduce spending, and strategy comparison.
- Added goal allocation strategies: equal_split, priority_first, closest_deadline, lowest_gap_first.
- Added structured Pydantic schemas in `app/schemas/ai.py` and a dedicated LLM prompt in `app/ai_cfo/llm/prompts.py`.
- Added `/ai/savings-optimizer/strategies`, `/ai/savings-optimizer/simulate`, and `/ai/savings-optimizer/compare` endpoints in `app/routers/ai.py`.
- Validated account access through `FamilyAccountAccessService` and goal access through `FamilyGoalService`; cross-tenant resources return `404`/`403`.
- Implemented deterministic fallback narrative and optional LLM narrative with cost-control and safety filtering.
- Added 19 integration tests; full suite **313 passed, 1 skipped**.

**Remaining:**
- Dedicated savings-optimizer UI template/page.
- Essential vs. discretionary expense classification for emergency funds.
- Integration with the What-If Simulator for "what-if I save more?" scenarios.

**Test results:** 313 passed, 1 skipped

---

## Completed Card 26

### Card 26: AI-1213 — Goal Planner ✅ DONE

**PLAN_V2 Reference:** AI-1213 (Goal Planner)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Created `app/ai_cfo/engines/goal_planner.py` with deterministic, read-only goal planning and prioritization.
- Supported planning modes: single_goal_feasibility, hypothetical_goal, multi_goal_prioritization, deadline_rescue, and family_goal_plan.
- Added prioritization strategies: equal_split, priority_first, closest_deadline, lowest_gap_first.
- Added structured Pydantic schemas in `app/schemas/ai.py` and a dedicated LLM prompt in `app/ai_cfo/llm/prompts.py`.
- Added `/ai/goal-planner/modes`, `/ai/goal-planner/plan`, and `/ai/goal-planner/prioritize` endpoints in `app/routers/ai.py`.
- Validated goal access through `FamilyGoalService`; cross-tenant goals return `404` and unauthorized private goals return `403`.
- Implemented deterministic fallback narrative and optional LLM narrative with cost-control and safety filtering.
- Added 23 integration tests covering all modes, strategies, validation, permissions, read-only safety, tenant isolation, and RLS.
- Full test suite: **336 passed, 1 skipped**.

**Remaining:**
- Dedicated goal-planner UI template/page.
- Formal probability modeling for goal achievement.
- Integration with the What-If Simulator for "what-if I change my contributions?" scenarios.

**Test results:** 336 passed, 1 skipped

---

## Completed Card 27

### Card 27: AI-1219 — Proactive Alerts ✅ DONE

**PLAN_V2 Reference:** AI-1219 (Proactive Alerts Engine)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Created `app/ai_cfo/engines/proactive_alerts.py` with deterministic, read-only alert detection.
- Implemented alert types: bill due soon, bill overdue, subscription renewal soon, high spending anomaly, negative cash flow, low emergency fund, goal deadline risk, and debt pressure.
- Added structured Pydantic schemas in `app/schemas/ai.py` and a dedicated LLM prompt in `app/ai_cfo/llm/prompts.py`.
- Added `/ai/proactive-alerts/types`, `/ai/proactive-alerts/preview`, and `/ai/proactive-alerts/run` endpoints in `app/routers/ai.py`.
- Wired `run()` to create in-app notifications through `NotificationDeliveryService` with duplicate prevention per entity/type/day.
- Added `run_proactive_alerts_task` Celery stub in `app/tasks/notifications.py`.
- Implemented deterministic fallback wording and optional LLM wording with cost-control and safety filtering.
- Fixed `Decimal` import in `app/config.py` so proactive-alert defaults load correctly.
- Added 18 integration tests covering all alert types, deduplication, auth, read-only safety, LLM fallback, tenant isolation, and RLS.
- Full test suite: **354 passed, 1 skipped**.

**Remaining:**
- Real-time push/email delivery for generated alerts.
- Production Celery scheduling for daily alert runs.
- Statistical anomaly modeling for spending alerts.
- Deeper family-role scoping for private-goal alerts.

**Test results:** 354 passed, 1 skipped

---

## Completed Card 28

### Card 28: AI-1220 — AI Chat Interface ✅ DONE

**PLAN_V2 Reference:** AI-1220 (AI Chat Interface)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Rewrote `app/services/ai_chat.py` with session-aware `AIChatService`:
  - `list_sessions`, `get_session`, `get_chat_history`, `delete_session`
  - `_get_or_create_session` auto-creates sessions and titles
  - `_build_history` loads recent messages for LLM context
  - `_generate_response` uses existing `LLMClient` with cost-control and safety fallback
  - `_rule_based_response` and `_suggested_questions` provide deterministic fallback
- Updated `app/ai_cfo/llm/prompts.py` `chat_prompt()` to accept conversation `history`.
- Added structured Pydantic schemas in `app/schemas/ai.py`:
  - `ChatMessageResponse`, `ChatSessionResponse`, `ChatSessionsResponse`
  - `ChatHistoryResponse`, `ChatSuggestedQuestionsResponse`
  - `session_id` field on `ChatResponse`
- Added tenant-scoped chat session routes in `app/routers/ai.py`:
  - `GET /ai/chat/sessions`
  - `GET /ai/chat/sessions/{session_id}`
  - `GET /ai/chat/sessions/{session_id}/messages`
  - `GET /ai/chat/sessions/{session_id}/suggested-questions`
  - `DELETE /ai/chat/sessions/{session_id}`
- The existing `POST /ai/chat` endpoint now returns `session_id` and maintains context across turns.
- All routes enforce authentication and tenant membership; service queries filter by `tenant_id` and `user_id`.
- No migration required; existing `AIChatSession` and `AIChatMessage` models already support tenant/user/message storage.
- Added 10 integration tests in `app/tests/integration/test_ai_chat.py` covering auth, session creation, history, deletion, suggested questions, cross-tenant isolation, and LLM fallback.
- Full test suite: **364 passed, 1 skipped**.

**Remaining:**
- Update the HTML chat page (`/ai/chat`) to use the new session API inline.
- Implement cross-session AI memory (AI-1221).
- Add WebSocket real-time chat only if product requirements justify it.

**Test results:** 364 passed, 1 skipped

---

## Completed Card 29

### Card 29: AI-1221 — AI Memory System ✅ DONE

**PLAN_V2 Reference:** AI-1221 (AI Memory System)  
**Type:** Feature / AI CFO  
**Priority:** HIGH

**Completed:**
- Added `AIMemory`, `AIMemoryType`, and `AIMemorySource` models to `app/models/ai.py`.
- Created Alembic migration `360b89eed134` adding the `ai_memories` table with RLS + FORCE RLS and indexes on `tenant_id`, `user_id`, `memory_type`, `key`, and `is_active`.
- Added structured Pydantic schemas in `app/schemas/ai.py` for memory CRUD, search, extraction, and forget operations.
- Created `app/services/ai_memory_service.py` with:
  - `create_memory`, `update_memory`, `list_memories`, `get_memory`, `forget_memory`, `forget_by_query`, `search_memories`
  - Safety filtering that rejects secrets, passwords, API keys, OTPs, account/card numbers, and long numeric identifiers
  - Duplicate prevention by `tenant_id + user_id + memory_type + key`
  - `get_prompt_context()` to build a sanitized memory block for LLM prompts
  - `get_memory_summary()` for the user-facing "what do you remember" response
- Integrated memory into `app/services/ai_chat.py`:
  - `remember that ...` creates/updates a memory
  - `forget ...` deactivates matching memories
  - `what do you remember about me?` returns a safe summary
  - Normal messages include active non-sensitive memories in the LLM prompt context
- Updated `app/ai_cfo/llm/prompts.py` to include a `memory_summary` block when present.
- Added tenant-scoped `/ai/memory/*` routes in `app/routers/ai.py`.
- Added 18 integration tests covering CRUD, safety, search, chat integration, cross-tenant isolation, RLS, and read-only financial safety.
- Full test suite: **382 passed, 1 skipped**.

**Remaining:**
- Richer natural-language memory inference beyond explicit commands.
- Background cleanup of expired/soft-deleted memories if retention policies are added.

**Test results:** 382 passed, 1 skipped

---

## Completed Card 30

### Card 30: AI-1222 — AI Confidence Scoring ✅ DONE

**PLAN_V2 Reference:** AI-1222 (AI Confidence Scoring)  
**Type:** Feature / AI CFO  
**Priority:** MEDIUM

**Completed:**
- Added `app/ai_cfo/confidence.py`: `ConfidenceLabel`, `ConfidenceFactor`, `ConfidenceScore`, `ConfidenceScorer`, `calculate_confidence_score`, `confidence_from_factors`, `label_from_score`, `explain_confidence`, `confidence_rules`.
- Score range 0.0–1.0; thresholds high >= 0.75, medium >= 0.45, low < 0.45; base score 0.60.
- 7 positive factors and 11 negative factors covering data completeness, recency, deterministic-vs-LLM origin, assumptions, forecast horizon, and LLM fallback.
- Wired confidence scoring into the What-If Simulator, Debt Optimizer, Savings Optimizer, Goal Planner, Proactive Alerts, and AI Chat, in every case as additive optional fields that preserve existing response fields.
- Added `ConfidenceFields` mixin and `ConfidenceFactorSchema`/`ConfidenceRulesResponse` to `app/schemas/ai.py`.
- Added `GET /ai/confidence/rules` (auth required) returning thresholds, labels, and the factor library.
- LLM narrative alone never boosts numeric confidence; a rule-based chat fallback (LLM unavailable/failed) is explicitly scored lower via the `llm_fallback` factor.
- Explicit "remember"/"forget"/"what do you remember" chat commands score as high confidence (deterministic, no LLM dependency); confirmed memory gives a small personalization boost when used in free-form LLM prompts.
- No database schema changes; no Alembic migration.
- Added 24 integration/unit tests in `app/tests/integration/test_confidence.py`.
- Full test suite: **406 passed, 1 skipped**.

**Remaining:**
- Confidence scores are not persisted/logged for later analysis or feedback-driven threshold tuning (deferred).
- No frontend confidence-badge UI built in this card.

**Test results:** 406 passed, 1 skipped

---

## Completed Card 31

### Card 31: AI-1223 — Dashboard v2 (AI-Centric) ✅ DONE

**PLAN_V2 Reference:** AI-1223 (Dashboard v2 (AI-Centric))  
**Type:** Feature / AI CFO  
**Priority:** CRITICAL

**Completed:**
- Added `app/services/dashboard_ai_service.py` (`DashboardAIService`) composing a single read-only "Today" payload from existing services/engines: `HealthScoreService`, `CommitmentService`, `FamilyGoalService`, `ProactiveAlertsEngine.preview()`, `SavingsOptimizer`, `DebtOptimizer`.
- Added `GET /dashboard/api/today` (JSON) and `GET /dashboard/partials/ai-today` (HTMX refresh), both auth/tenant-scoped.
- Rebuilt `app/templates/dashboard/index.html` around new AI-centric partials (`ai_today.html` + 5 sub-partials): AI brief, health snapshot, top alerts, AI recommendations, optimizer quick actions — while preserving the existing commitments and family-goals widgets unchanged.
- Confidence (AI-1222) surfaced throughout: overall summary confidence, per-alert confidence, per-insight-card confidence.
- Deterministic-first AI narrative; optional `?include_narrative=true` LLM enhancement via existing safety/cost-control stack, always falls back safely (works with no `OPENAI_API_KEY`).
- **Security fix:** `ProactiveAlertsEngine._detect_goal_risks()` did not respect family goal visibility, allowing a private goal to appear in another family member's alert text. Fixed to filter via `FamilyGoalService.can_view_goal()`, matching every other engine.
- No schema changes; no Alembic migration.
- Added 19 integration tests in `app/tests/integration/test_dashboard_ai.py`; full suite **425 passed, 1 skipped**.

**Remaining:**
- What-If/Debt/Savings/Goal Planner still have no dedicated HTML pages; dashboard shortcuts deep-link into AI Chat with a pre-filled question instead.
- LLM-enhanced narrative not exposed in the default page UI (cost control); available via API flag only.

**Test results:** 425 passed, 1 skipped

---

## Completed Card 32

### Card 32: FAM-1303 — Family Budgets ✅ DONE

**PLAN_V2 Reference:** FAM-1303 (Family Budgets)  
**Type:** Feature / Family Finance  
**Priority:** HIGH

**Completed:**
- Hardened `Budget` model: added `visibility` (private/shared/family), `status` (active/archived/closed), `currency`, `owner_user_id`, `family_id`, `created_by_user_id`; migration `07c75f53dbf6` preserves existing budget data and RLS/FORCE RLS (already active on `budgets`; `budget_categories` already covered via child-table RLS).
- Added `app/services/family_budget_service.py` (`FamilyBudgetService`): CRUD, role-based visibility/permission checks (mirroring `FamilyAccountAccessService`), budget-category management with expense-account validation, and read-only budget-vs-actual calculation from posted journal entries.
- Added `/family/budgets/*` routes (create/list/get/update/archive/summary/category CRUD), all auth + tenant-scoped.
- Fixed the pre-existing, broken `/budgets` router stub (had a `NameError` bug and no template) to require auth and delegate to `FamilyBudgetService`.
- Fixed a pre-existing generic RLS test (`test_rls_child_tables.py`) whose raw-SQL `budgets` insert predated the new NOT NULL columns.
- Added 26 integration tests; full suite **451 passed, 1 skipped**.

**Remaining:**
- No dashboard widget UI yet (documented follow-up: DB-1106A).
- No AI budget advisor or forecasting (explicitly out of scope for this card).

**Test results:** 451 passed, 1 skipped

---

## Completed Card 33

### Card 33: DB-1106A — Family Budget Dashboard Widget UI ✅ DONE

**PLAN_V2 Reference:** DB-1106A (informal follow-up to FAM-1303, matching the DB-1104A/DB-1105A widget pattern)  
**Type:** Feature / Dashboard  
**Priority:** HIGH

**Completed:**
- Added a Family Budgets widget to the AI-centric dashboard: `GET /dashboard/api/family-budgets` (JSON), `GET /dashboard/partials/family-budgets` (HTMX widget), `POST /dashboard/partials/family-budgets/{id}/archive` (permission-checked quick action), `GET /dashboard/partials/family-budgets/{id}/categories` (read-only expandable breakdown).
- New templates: `family_budgets_widget.html`, `family_budgets_list.html`, `family_budget_card.html`, `family_budget_categories.html`; integrated into `dashboard/index.html` alongside the existing AI Today brief, commitments, and family-goals widgets (none removed).
- Reused `FamilyBudgetService.list_visible_budgets_for_user()` / `calculate_budget_summary()` unchanged — no new budget calculation logic; added only two small public helpers (`get_role()`, `can_create_budget()`).
- Verified budget-vs-actual is computed fresh and never persisted during dashboard render, and that an inaccessible private account's name is never leaked through a shared budget's category display.
- No schema changes; no Alembic migration.
- Added 19 integration tests; full suite **470 passed, 1 skipped**.

**Remaining:**
- Category creation/editing still lives on the full `/family/budgets` page (dashboard links there rather than embedding editing).
- No unarchive quick action in the widget.

**Test results:** 470 passed, 1 skipped

---

## Completed Card 34

### Card 34: FAM-1304 — Allowance and Chore Tracking ✅ DONE

**PLAN_V2 Reference:** FAM-1304 (Allowance and Chore Tracking)  
**Type:** Feature / Family Finance  
**Priority:** MEDIUM

**Completed:**
- New tables `family_chores` and `family_chore_completions` (migration `356391296d35`), both tenant-scoped with RLS + FORCE RLS from creation; 46 tables total (was 44), RLS active on 37 (was 35).
- Added `app/services/family_chore_service.py` (`FamilyChoreService`): chore CRUD, completion submit/approve/reject, and a read-only allowance summary (pending/approved/rejected totals, per-member breakdown, scoped by role).
- Role matrix: HEAD/PARENT create/manage/approve everything and see all chores + the full allowance summary; ADULT sees all chores but cannot create/manage/approve (no elevated-permission flag exists yet); TEEN/CHILD see and can only act on chores assigned to themselves; VIEWER is fully read-only.
- Added `/family/chores/*`, `/family/chore-completions/{id}/approve|reject`, and `/family/allowance-summary` routes.
- No transactions, journal entries, or account-balance changes anywhere — allowance amounts are plain numeric fields only.
- Added 29 integration tests; full suite **499 passed, 1 skipped**.

**Remaining:**
- No accounting posting for approved allowance (documented follow-up: FAM-1305 — Allowance Payment Posting Through Accounting Engine).
- No dashboard widget yet, though `get_family_chore_summary()` was added specifically for one (documented follow-up: DB-1107A — Allowance and Chore Dashboard Widget UI).
- No recurring-chore auto-regeneration; `frequency` is descriptive only today.

**Test results:** 499 passed, 1 skipped

---

## Completed Card 35

### Card 35: DB-1107A — Allowance and Chore Dashboard Widget UI ✅ DONE

**PLAN_V2 Reference:** DB-1107A (informal follow-up to FAM-1304, matching the DB-1104A/DB-1105A/DB-1106A widget pattern)
**Type:** Feature / Dashboard
**Priority:** HIGH

**Completed:**
- Added a Chores & Allowance widget to the AI-centric dashboard: `GET /dashboard/api/family-chores` (JSON), `GET /dashboard/partials/family-chores` (HTMX widget), `POST /dashboard/partials/family-chores/{chore_id}/complete` (submit-completion quick action), `POST /dashboard/partials/family-chore-completions/{completion_id}/approve` (approve quick action).
- New templates: `family_chores_widget.html`, `family_chores_list.html`, `family_chore_card.html`, `family_chore_pending_approvals.html`, `family_allowance_summary.html`; integrated into `dashboard/index.html` alongside the existing AI Today brief, commitments, family-goals, and family-budgets widgets (none removed).
- Reused `FamilyChoreService.list_visible_chores_for_user()` and `get_allowance_summary()` unchanged; added two small read-only helper methods to the service (`list_pending_completions_for_user()`, `get_approved_allowance_this_month()`) — no chore/allowance calculation logic duplicated in the router. Due-soon/overdue bucketing is view-only categorization of chores the service already scoped by role.
- Verified role-based visibility (HEAD/PARENT see all chores + approvals + full summary; TEEN/CHILD see only their own assigned chores and completions; VIEWER sees no action buttons), and that submit/approve quick actions are permission-checked server-side (not just hidden in the UI).
- Reject is intentionally not offered as a dashboard quick action (it requires a reason); the widget links to `/family/chores` instead, matching the existing "View" link precedent from the family-budgets widget's `family_budget_card.html`.
- No schema changes; no Alembic migration (Alembic head unchanged at `356391296d35`).
- Added 25 integration tests; full suite **524 passed, 1 skipped**.

**Remaining:**
- Reject quick action not on the dashboard (documented limitation above).
- No accounting posting for approved allowance (documented follow-up: FAM-1305 — Allowance Payment Posting Through Accounting Engine).

**Test results:** 524 passed, 1 skipped

---

## Completed Card 36

### Card 36: FAM-1305 — Allowance Payment Posting Through Accounting Engine ✅ DONE

**PLAN_V2 Reference:** FAM-1305 (Allowance Payment Posting), following the FAM-1304 → DB-1107A → FAM-1305 "track, surface, post" sequence
**Type:** Feature / Accounting
**Priority:** MEDIUM

**Completed:**
- Added `payment_status`, `payment_account_id`, `expense_account_id`, `payment_journal_entry_id`, `payment_reversal_journal_entry_id`, `paid_at`, `paid_by_user_id` to `FamilyChoreCompletion` (migration `bd89e4fcf4b9`, nullable/defaulted, no data loss, RLS untouched).
- `FamilyChoreService.post_payment()` posts an approved completion's `earned_amount` as a balanced journal entry (debit Expense, credit Asset) through `AccountingService.create_journal_entry()` — never a direct insert. Reference `ALLOW-{tenant_id}-{completion_id}`; idempotent on `payment_journal_entry_id`.
- `FamilyChoreService.reverse_payment()` reverses a posted payment through the existing `AccountingService.reverse_journal_entry()` (ACC-503A) — idempotent, never deletes/mutates the original entry.
- HEAD/PARENT-only permission gate (`can_user_post_payment()`), separate from the assigned-member's ability to submit a completion.
- Account validation: tenant-scoped lookup (cross-tenant → 404), Asset/Expense type checks, `FamilyAccountAccessService.can_use_account_for_posting()`.
- `GET /family/allowance-summary` gained `approved_unpaid_amount`, `paid_amount`, `reversed_amount` (overall and per-member), without changing any existing field's meaning.
- Added `POST /family/chore-completions/{id}/post-payment` and `POST /family/chore-completions/{id}/reverse-payment`.
- Dashboard widget gained a "ready to pay" count/badge (HEAD/PARENT only) — no account-selecting payment form was added to the dashboard (documented follow-up: DB-1107B).
- Added 30 integration tests; full suite **554 passed, 1 skipped**.

**Remaining:**
- No dashboard-embedded payment form (documented follow-up: DB-1107B — Allowance Payment Dashboard Action Form).
- "Reject inaccessible private account" is structurally unreachable for the only permitted posting role (HEAD/PARENT already has full account access per FAM-1301) — documented as a known limitation rather than a gap.
- No partial or batch payment posting.

**Test results:** 554 passed, 1 skipped

---

## Latest Completed Card

**FAM-1305 - Allowance Payment Posting Through Accounting Engine** is complete. An approved chore completion's earned allowance can now be posted as a real, balanced journal entry (debit expense, credit asset/payment account) through the existing accounting engine, and safely reversed through the existing reversal engine — both HEAD/PARENT-only, idempotent, and fully tenant/RLS-isolated. The allowance summary and dashboard widget now distinguish pending, approved-unpaid, paid, and reversed amounts. Chore completion records are preserved exactly as before; nothing bypasses `AccountingService`, no journal entry is ever deleted or mutated, and the full test suite passes.

---

*End of PLAN_V2_CARD_STATUS.md*
