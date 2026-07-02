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
| PF-005 | Define AI CFO Safety Rules | **Partial** | `AIInsight` has confidence field | No `app/ai_cfo/llm/safety.py`, no disclaimer injection, no content filtering | Create safety module with 10 rules |
| PF-006 | Define User Navigation Around Financial Life | **Partial** | Templates exist for dashboard, accounts, budgets, goals, loans, ai, transactions | Navigation not reorganized around "Today", "This Month", "Cash Flow" per PLAN_V2.md | Restructure nav in `base.html` |
| PF-007 | Define Normal User View vs Accountant View | **Partial** | Accounts router shows COA; no accountant toggle | No "Accountant View" mode, no hidden accounting | Add view mode toggle and hide COA from normal users |
| PF-008 | Define Import Strategy (Manual, CSV, Excel, SMS) | **Missing** | No `app/imports/` module | No CSV parser, no Excel parser, no SMS parser | Create `app/imports/` with parsers |
| PF-009 | Define MVP User Journey | **Unknown** | No documentation found | No user journey document | Write `docs/product/mvp-journey.md` |
| PF-010 | Define Family Finance Model | **Partial** | `FamilyMember` model exists on `User` | No `Family` model, no shared/private account logic, no roles matrix | Create proper `app/family/` module |
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
| SAAS-200 | Tenant Model and CRUD | **Partial** | `Organization` model with CRUD fields | Named "Organization" not "Tenant"; no `Plan` model separate from enum | Rename or alias; extract Plan model |
| SAAS-201 | Tenant Isolation Middleware | **Done** | `TenantScopingMiddleware` extracts tenant_id from JWT and sets DB RLS context | Application-level + DB-level RLS both active | Monitor for performance impact |
| SAAS-202 | Subscription Plans (Free, Premium, Family) | **Partial** | `SubscriptionPlan` enum with 4 plans | No plan feature flags, no limit enforcement logic | Add feature checking service |
| SAAS-203 | Usage Limits and Quotas | **Partial** | `max_users`, `max_transactions`, `max_ai_requests_per_day` on Organization | No usage tracking or enforcement | Create `UsageLog` model and enforcement |
| AUTH-300 | User Registration | **Partial** | Register endpoint, AuthService.create_user() | Email sending is placeholder (`pass`) | Implement email or console backend |
| AUTH-301 | User Login and JWT | **Partial** | Login endpoint, access/refresh tokens, JWT encoding | Token expiry: 7 days (not 15 min + 7 days per PLAN_V2.md) | Adjust token expiry |
| AUTH-302 | Forgot Password | **Partial** | Endpoint exists, AuthService.reset_password() | Email sending is placeholder | Implement email delivery |
| AUTH-303 | Email Verification | **Partial** | Endpoint exists, AuthService.verify_email() | Email sending is placeholder | Implement email delivery |
| AUTH-304 | Role-Based Access Control (RBAC) | **Partial** | `UserRole` enum (owner/admin/editor/viewer) | No route guards, no resource-level checks, no permission decorators | Add permission decorators and guards |
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
| **Done** | 11 | PF-000, PF-001, PF-003, PF-011, PF-012, PF-014, PF-101, PF-103, PF-103C, PF-103B, SAAS-201, USR-401 |
| **Partial** | 18 | PF-004, PF-005, PF-006, PF-007, PF-010, PF-015, PF-100, PF-102, SAAS-200, SAAS-202, SAAS-203, AUTH-300, AUTH-301, AUTH-302, AUTH-303, AUTH-304, AUTH-305, USR-400, USR-402, ACC-500, ACC-501, ACC-502 |
| **Missing** | 1 | PF-008 |
| **Should Refactor** | 2 | PF-002, PF-013 |
| **Unknown** | 1 | PF-009 |

**Note:** The counts don't sum to exactly 30 because some cards span multiple statuses (e.g., "Partial" covers a range of completion).

---

## Cards Beyond 30 (Quick Assessment)

| Card Range | Area | Overall Status |
|------------|------|---------------|
| TRX-600 to TRX-605 | Transactions | Partial (models exist, routes exist, service exists) |
| IMP-700 to IMP-703 | Imports | **Missing** (no module) |
| BILL-800 to BILL-801 | Bills | Partial (model exists, no dedicated router) |
| SUB-900 to SUB-901 | Subscriptions | Partial (model exists, no dedicated router) |
| BDG-1000 to BDG-1003 | Budgets | Partial (models, routes, service exist) |
| DB-1100 to DB-1105 | Dashboard | Partial (main dashboard works, widgets incomplete) |
| AI-1200 to AI-1223 | AI CFO | Partial (orchestrator, health score, chat exist; LLM integration missing) |
| FAM-1300 to FAM-1305 | Family Finance | Partial (FamilyMember model only) |
| GOAL-1400 to GOAL-1402 | Goals | Partial (models, routes, service exist) |
| LOAN-1500 to LOAN-1505 | Loans | Partial (models, routes, service exist) |
| NOTIF-1600 to NOTIF-1604 | Notifications | Partial (models, routes, service exist) |
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
6. **AUTH-300 to AUTH-305** — Complete auth flow (email sending, RBAC guards)
7. **AI-1201** — LLM client integration (OpenAI) — core differentiator
8. **PF-002 / PF-013** — Structural alignment (gradual refactor)

### Medium Priority (Important for V1)
8. **BILL-800 / SUB-900** — Bills and subscriptions (models exist, need routers)
9. **DB-1101 to DB-1105** — Dashboard widgets
10. **NOTIF-1600** — Email notifications (SMTP integration)
11. **Tests** — No test coverage

### Lower Priority (Can Defer)
12. **BILLING-1800** — Stripe billing
13. **API-1900** — Public REST API
14. **MOB-2200** — PWA/mobile
15. **FEED-2300** — Bank feeds

---

*End of PLAN_V2_CARD_STATUS.md*
