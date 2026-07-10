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
| BDG-1000 to BDG-1003 | Budgets | Partial (models, routes, service exist) |
| DB-1100 to DB-1105 | Dashboard | **Done** for DB-1104A bills/subscriptions widget UI; Partial for remaining dashboard widgets |
| AI-1200 to AI-1223 | AI CFO | **Done** for AI-1201 LLM client; Partial for remaining AI engines (health score, chat, what-if, orchestrator exist but not all wired to LLM) |
| FAM-1300 | Family Finance Foundation | **Done** |
| FAM-1301 | Family Account Visibility and Shared/Private Data Rules | **Done** |
| FAM-1302 | Family Goals | **Done** |
| FAM-1303 to FAM-1305 | Family Finance (budgets, allowances, chores, dashboard) | Partial |
| GOAL-1400 to GOAL-1402 | Goals | Partial (models, routes, service exist) |
| LOAN-1500 to LOAN-1505 | Loans | Partial (models, routes, service exist) |
| NOTIF-1600 to NOTIF-1604 | Notifications | **Done** for NOTIF-1600 (email backend, reminder generation, CRUD/preferences routes, tests); Partial for remaining notification channels |
| ADMIN-1700 to ADMIN-1704 | Admin | Partial (router exists, limited functionality) |
| BILLING-1800 to BILLING-1803 | Billing | **Missing** (Stripe fields on model only) |
| API-1900 to API-1903 | API | **Missing** (no public API) |
| REP-2000 to REP-2005 | Reports | **Missing** (no report generators) |
| DOC-2100 to DOC-2103 | Documents | Partial (model, router, service exist; no OCR) |
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

## Latest Completed Card

**FAM-1302 - Family Goals** is complete. Goals now support family scoping, `private`/`shared`/`family` visibility, owner tracking, role-based access, contributions, and progress tracking. All data remains tenant-scoped with RLS + FORCE RLS enforced.

---

*End of PLAN_V2_CARD_STATUS.md*
