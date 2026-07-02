# NEXT_RECOMMENDED_BUILD_ORDER.md

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Audit Date:** 2026-07-01  
**Plan Reference:** `PLAN_V2.md`  
**Current State:** `docs/audits/CURRENT_STATE_AUDIT.md`, `docs/audits/PLAN_V2_CARD_STATUS.md`, `docs/audits/DATABASE_SCHEMA_AUDIT.md`

---

## Executive Summary

Cards PF-014-DB (Database Initialization), PF-103A (RLS Implementation), PF-103C (Child Table RLS Coverage), and PF-103B (Safe Super Admin Access) are **COMPLETE**. The database now has 40 tables with Alembic-managed migrations, and 30 tenant-scoped tables are protected by PostgreSQL Row-Level Security with FORCE RLS.

The next 10 cards must focus on **making the application usable**: seed data, completing auth, building tests, and adding the import system that is critical for the Oman market.

---

## Completed Cards

### Card 1: PF-014-DB — Initialize Database and Alembic ✅ DONE
**Date:** 2026-07-01  
**Alembic Revision:** 89b158bef60e  
**Tables Created:** 39  
**Status:** All tables match models, alembic_version active.

### Card 2: PF-103A — Implement PostgreSQL Row-Level Security ✅ DONE
**Date:** 2026-07-01  
**Alembic Revision:** 4a2c8d1e5f6b  
**Tables Protected:** 24 with RLS+FORCE  
**Policies Created:** 96  
**Tests:** 6/6 passed  
**Status:** RLS active, tenant context set via SET LOCAL, cross-tenant access blocked.

### Card 3: PF-103C — RLS Coverage Audit for Child Tables ✅ DONE
**Date:** 2026-07-02  
**Alembic Revision:** df41f5ea2f46  
**Tables Protected:** 6 additional child/tenant tables (30 total with RLS+FORCE)  
**Policies Created:** 24 additional policies (120 total)  
**Tests:** 6/6 passed  
**Status:** Child tables now protected via join-based or organization_id-based RLS.

### Card 4: PF-103B — Safe Super Admin Tenant Access ✅ DONE
**Date:** 2026-07-02  
**Alembic Revision:** 542823443f9e  
**Admin Access Model:** One-tenant-at-a-time support sessions with audit logging  
**Tests:** 9/9 passed  
**Status:** No true RLS bypass implemented; admin access still obeys normal RLS policies.

---

## The Next 10 Cards

### Card 3: PF-103B — Safe Super Admin Tenant Access ✅ DONE
**PLAN_V2 Reference:** PF-103 (PostgreSQL RLS Implementation)  
**Type:** Security / Infrastructure  
**Priority:** HIGH

**Completed:**
- Implemented one-tenant-at-a-time support sessions via `AdminAccessSession`.
- Added `/admin/support-access/*` endpoints with super-admin authorization.
- Audit records include admin, target tenant, reason, timing, IP, and user agent.
- No true RLS bypass; normal app user still obeys RLS.
- 9 integration tests pass.

**Remaining:**
- Schedule a background job to mark expired sessions as `expired`.
- If a true break-glass DBA bypass is ever required, implement `PF-103D` separately.

---

### Card 4: SAAS-200-SEED — Seed Default Data (Chart of Accounts, Categories, Plans) ✅ DONE
**PLAN_V2 Reference:** ACC-500 (Chart of Accounts) + SAAS-202 (Subscription Plans)  
**Type:** Data / Migration  
**Priority:** HIGH

**Completed:**
- Created `scripts/seed_default_data.py` and `app/seeds/default_data.py`.
- Seeded development tenant `dev-family` with Family plan limits.
- Seeded development super-admin (email/password from env or generated temp password).
- Seeded 31-account OMR-friendly Chart of Accounts under the dev tenant.
- Seeded default monthly budget with 14 categories linked to expense accounts.
- Seeded 8 default notification preferences for the dev user.
- Seed is idempotent; running twice creates no duplicates.
- 9 integration tests pass.

**Remaining:**
- No dedicated `plans` table yet; limits are columns on `organizations`.
- No general transaction categories table yet; `BudgetCategory` is budget-specific.
- Future cards: `SAAS-202` (plan table) and `TRX-604A` (transaction categories).

**Acceptance criteria:**
- [x] Default COA is created for new tenants
- [x] Default categories exist (budget categories)
- [x] Plans are seeded with correct limits
- [x] Seeding is idempotent
- [x] Seed script is documented

**Estimated effort:** 2-3 hours

---

### Card 5: AUTH-300-FIX — Complete Authentication Flow (Email, RBAC Guards)
**PLAN_V2 Reference:** AUTH-300 to AUTH-305  
**Type:** Feature Completion  
**Priority:** HIGH

**What to do:**
- Implement email sending (SMTP or console backend for dev)
- Add email verification email template
- Add password reset email template
- Add role-based route guards (`require_role` decorator)
- Add resource-level permission checks (can this user edit this transaction?)
- Fix token expiry (15 min access, 7 day refresh per PLAN_V2.md)
- Add logout endpoint that revokes refresh token

**Why fifth:** Auth is the gateway to everything. Incomplete auth blocks user onboarding and creates security holes.

**Acceptance criteria:**
- [ ] Registration sends verification email
- [ ] Login returns proper 15-min access + 7-day refresh tokens
- [ ] Role decorators protect admin routes
- [ ] Users can only access their own data
- [ ] Logout revokes refresh token
- [ ] Password reset flow works end-to-end

**Estimated effort:** 4-6 hours

---

### Card 6: PF-100-TEST — Write First Tests (Auth + Tenant Isolation)
**PLAN_V2 Reference:** PF-100 (Project Architecture) + Testing  
**Type:** Testing  
**Priority:** HIGH

**What to do:**
- Set up pytest with async support (`pytest-asyncio`)
- Create test database configuration (separate test DB)
- Write tests for:
  - User registration (success, duplicate email, weak password)
  - User login (success, wrong password, unverified email)
  - JWT token generation and validation
  - Tenant middleware (tenant extraction, missing tenant)
  - RLS policies (cross-tenant access blocked)
- Create `conftest.py` with fixtures for db, client, test user
- Run tests: `pytest -q`

**Why sixth:** Tests provide confidence for refactoring. Without tests, every change risks breaking something. Auth and tenant isolation are the most critical to test.

**Acceptance criteria:**
- [ ] `pytest` runs without import errors
- [ ] All auth tests pass
- [ ] All tenant isolation tests pass
- [ ] Test database is separate from dev database
- [ ] Tests run in < 30 seconds

**Estimated effort:** 4-6 hours

---

### Card 7: IMP-700-CSV — Create Import Module with CSV Parser
**PLAN_V2 Reference:** IMP-700 (CSV Import) + PF-008 (Import Strategy)  
**Type:** New Feature  
**Priority:** HIGH (Oman Market Critical)

**What to do:**
- Create `app/imports/` module structure:
  - `models.py` — ImportJob, ImportMapping, ImportedRow
  - `schemas.py` — Pydantic models for import requests
  - `services.py` — Import orchestration
  - `routes.py` — Upload, preview, confirm endpoints
  - `parsers/csv_parser.py` — CSV parsing logic
  - `parsers/excel_parser.py` — Excel parsing (stub)
  - `parsers/sms_parser.py` — SMS parsing (stub)
- Implement CSV upload with column mapping UI
- Implement preview (first 10 rows)
- Implement duplicate detection
- Implement import job tracking
- Generate journal entries for imported transactions

**Why seventh:** CSV/Excel import is the primary data entry method for Oman users. Bank APIs are not available. This feature is critical for user adoption.

**Acceptance criteria:**
- [ ] CSV files can be uploaded
- [ ] Column mapping UI works
- [ ] Preview shows first 10 rows
- [ ] Duplicates are detected
- [ ] Valid rows are imported as transactions
- [ ] Journal entries are auto-generated
- [ ] Import job status is tracked

**Estimated effort:** 6-8 hours

---

### Card 8: IMP-702-SMS — Implement SMS Bank Alert Parser
**PLAN_V2 Reference:** IMP-702 (SMS Import Parser)  
**Type:** New Feature  
**Priority:** HIGH (Oman Market Critical)

**What to do:**
- Implement SMS parser for major Omani banks:
  - Bank Muscat
  - OAB
  - Alizz
  - Sohar International
  - NBO
  - HSBC Oman
- Parse: bank name, account mask, amount, date, description, balance
- Detect debit vs credit
- Suggest category based on description
- Create SMS import UI (paste text)
- Store SMS patterns and learn from corrections
- Link parsed SMS to transaction creation

**Why eighth:** SMS is the most reliable transaction source in Oman. Every bank sends SMS alerts. This is the strongest differentiator for the Oman market.

**Acceptance criteria:**
- [ ] SMS from major Omani banks are parsed
- [ ] Amount, date, description are extracted
- [ ] Debit/credit is detected
- [ ] Category is suggested
- [ ] User can correct parsing errors
- [ ] Parser learns from corrections
- [ ] Transactions are created from parsed SMS

**Estimated effort:** 6-8 hours

---

### Card 9: AI-1201-LLM — Integrate OpenAI LLM Client
**PLAN_V2 Reference:** AI-1201 (LLM Client and Prompt Management) + AI-1202 (Cost Control)  
**Type:** New Feature  
**Type:** HIGH (Core Differentiator)

**What to do:**
- Add `openai` to requirements.txt
- Create `app/ai_cfo/llm/client.py` — OpenAI client wrapper with retry
- Create `app/ai_cfo/llm/prompts.py` — prompt templates for each engine
- Create `app/ai_cfo/llm/cost_control.py` — token tracking, per-tenant limits
- Create `app/ai_cfo/llm/safety.py` — disclaimer injection, content filtering
- Integrate LLM into `AIOrchestrator` (replace rule-based insights with LLM-augmented)
- Add fallback to rule-based when LLM is unavailable
- Track token usage per tenant

**Why ninth:** AI is the core differentiator. Without LLM integration, the platform is just another accounting app. The rule-based foundation is solid — now it needs intelligence.

**Acceptance criteria:**
- [ ] OpenAI client is configured and working
- [ ] Prompt templates are defined for each engine
- [ ] Cost is tracked per request
- [ ] Tenant limits are enforced
- [ ] Disclaimers are injected
- [ ] Fallback to rule-based works
- [ ] Token usage is logged to `AITokenUsage` model

**Estimated effort:** 6-8 hours

---

### Card 10: BILL-800 / SUB-900 — Build Bills and Subscriptions Routers
**PLAN_V2 Reference:** BILL-800 (Bill Creation), SUB-900 (Subscription Tracking)  
**Type:** Feature Completion  
**Priority:** MEDIUM-HIGH

**What to do:**
- Create `app/routers/bills.py` with full CRUD
- Create `app/routers/subscriptions.py` with full CRUD
- Create bill templates (list, detail, create, edit)
- Create subscription templates (list, detail, create, edit)
- Add bill reminder logic (Celery task)
- Add subscription renewal alerts
- Link bills to transactions when marked paid
- Show bills and subscriptions in dashboard widget

**Why tenth:** Bills and subscriptions are core "Financial Life" features. Users need to track recurring payments. The models exist but the UI is missing.

**Acceptance criteria:**
- [ ] Bills can be created, edited, deleted
- [ ] Subscriptions can be created, edited, deleted
- [ ] Bill reminders are generated
- [ ] Subscription renewal alerts work
- [ ] Paid bills link to transactions
- [ ] Dashboard shows upcoming bills and renewals
- [ ] Templates are responsive

**Estimated effort:** 4-6 hours

---

## Build Sequence Rationale

### Why This Order?

```
Card 1: Database          → DONE ✅
Card 2: RLS               → DONE ✅
Card 2a: Child Table RLS  → DONE ✅
Card 3: Admin Access      → DONE ✅
Card 4: Seed Data         → DONE ✅
Card 5: Auth Completion   → Gateway. Users can't onboard without it.
Card 5: Auth Completion   → Gateway. Users can't onboard without it.
Card 6: Tests             → Confidence. Protects against regressions.
Card 7: CSV Import        → Data Entry. Primary user workflow.
Card 8: SMS Import        → Differentiator. Oman market critical.
Card 9: LLM Integration   → Intelligence. Core product value.
Card 10: Bills/Subs       → Features. Completes Financial Life MVP.
```

### Dependencies Graph

```
Card 1 (Database) ✅
    │
    ├──→ Card 2 (RLS) ✅ ──→ Card 2a (Child Table RLS) ✅ ──→ Card 3 (Admin Access) ✅
    │       │                                                              │
    │       │                                                              └──→ Card 4 (Seed Data) ✅
    │       │                                                                     │
    │       │                                                                     └──→ Card 5 (Auth) ──→ Card 6 (Tests)
    │       │
    │       └──→ Card 7 (CSV Import) ──→ Card 8 (SMS Import)
    │               │
    │               └──→ Card 9 (LLM) ──→ Card 10 (Bills/Subs)
    │
    └──→ (Future: Core Module refactor, gradual)
```

### Risk Mitigation

| Risk | Mitigation in this order |
|------|--------------------------|
| Database schema drift | Alembic (Card 1) ensures versioned migrations |
| Tenant data leak | RLS (Card 2) + child-table RLS (Card 2a) before any real data |
| Support can't debug | Admin access (Card 3) enables safe support access |
| App has no default data | Seed data (Card 4) makes app usable |
| Users can't sign up | Auth completion (Card 5) fixes onboarding |
| Regressions from changes | Tests (Card 6) catch issues early |
| Regressions from changes | Tests (Card 6) catch issues early |
| Users can't enter data | CSV/SMS import (Cards 7-8) enables data entry |
| Product is just accounting | LLM (Card 9) adds intelligence |
| Missing core features | Bills/Subs (Card 10) completes MVP |

---

## Exact Recommended Next Card

### Card 5: AUTH-300-FIX — Complete Authentication Flow (Email, RBAC Guards)

**Decision:** SAAS-200-SEED is complete. The database, RLS, admin access, and default data are now in place. The next priority is completing authentication so the seeded development tenant and super-admin can actually log in and use the application.

**What to tell the coding agent for AUTH-300-FIX:**

> "Implement Card AUTH-300-FIX: Complete Authentication Flow. Implement email sending (SMTP or console backend for dev), add email verification and password reset templates, add `require_role` decorators and resource-level permission checks, fix JWT token expiry to 15-minute access + 7-day refresh, and add a logout endpoint that revokes refresh tokens. Do not weaken RLS. Run `python -m pytest -q` after changes."

---

## After Card 10

Once these 10 cards are complete, the project will have:

- A working database with all tables and RLS
- Security via RLS + child-table RLS + safe admin access
- Default data seeded
- Complete authentication
- Test coverage for critical paths
- CSV and SMS import (Oman-ready)
- AI intelligence via LLM
- Bills and subscriptions tracking

**Next batch (Cards 11-20):**
- Family finance module (FAM-1300)
- Reports (REP-2000)
- Document OCR (DOC-2100)
- Notification channels (NOTIF-1600)
- What-If Simulator (AI-1214)
- Debt Optimizer (AI-1211)
- Savings Optimizer (AI-1212)
- Goal Planner (AI-1213)
- Proactive Alerts (AI-1219)
- Dashboard v2 AI-centric (AI-1223)

---

## Refactor Strategy: Gradual, Not Big-Bang

The existing flat structure should **not** be refactored all at once. Instead:

1. **Create `app/core/`** (Card 3) — new code uses it
2. **When building a new feature**, create it in the new module structure
3. **When modifying an existing feature**, move it to the new structure
4. **Leave untouched features** in the flat structure until they need changes
5. **After 3 months**, the majority of code will be in modules
6. **Then** remove the flat directories

This approach:
- Preserves working code
- Avoids massive PRs
- Allows incremental testing
- Keeps the app functional throughout

---

*End of NEXT_RECOMMENDED_BUILD_ORDER.md*
