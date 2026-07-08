# NEXT_RECOMMENDED_BUILD_ORDER.md

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Audit Date:** 2026-07-01  
**Plan Reference:** `PLAN_V2.md`  
**Current State:** `docs/audits/CURRENT_STATE_AUDIT.md`, `docs/audits/PLAN_V2_CARD_STATUS.md`, `docs/audits/DATABASE_SCHEMA_AUDIT.md`

---

## Executive Summary

Cards PF-014-DB (Database Initialization), PF-103A (RLS Implementation), PF-103C (Child Table RLS Coverage), PF-103B (Safe Super Admin Access), SAAS-200-SEED (Seed Default Data), AUTH-300-FIX (Complete Authentication Flow), and PF-100-TEST (Formalize Test Infrastructure) are **COMPLETE**. **IMP-700-CSV (CSV Import Module)** is also complete. The database now has 42 tables with Alembic-managed migrations, 32 tenant-scoped tables are protected by PostgreSQL Row-Level Security with FORCE RLS, the auth gateway is functional, a shared test foundation is in place, and users can upload CSV files to create journal entries.

Cards PF-014-DB, PF-103A, PF-103C, PF-103B, SAAS-200-SEED, AUTH-300-FIX, PF-100-TEST, IMP-700-CSV, and **IMP-702-SMS** are now complete. The next card should be **AI-1201-LLM — Integrate OpenAI LLM Client**, the core intelligence differentiator for the platform.

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

### Card 5: AUTH-300-FIX — Complete Authentication Flow (Email, RBAC Guards) ✅ DONE
**PLAN_V2 Reference:** AUTH-300 to AUTH-305  
**Type:** Feature Completion  
**Priority:** HIGH

**Completed:**
- Implemented dev-mode email verification and password reset (links logged, no SMTP required).
- Added `app.core.security` with reusable RBAC and tenant-context dependencies.
- Fixed JWT token expiry to 15-minute access + 7-day refresh; added refresh-token rotation and logout revocation.
- Added unique `jti` claim to refresh tokens to prevent storage collisions.
- Updated `/auth/register`, `/auth/login`, `/auth/verify-email/{token}`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/refresh`, `/auth/logout`.
- Admin routes now require `require_super_admin`.
- 15 auth integration tests pass; full suite 45/45 passes.

**Remaining:**
- Resource-level object permissions (e.g., can this user edit this specific transaction?).
- SMTP production email backend and HTML templates.
- Tenant member invitation flow (`AUTH-305`).

**Acceptance criteria:**
- [x] Registration sends/logs verification email
- [x] Login returns proper 15-min access + 7-day refresh tokens
- [x] Role dependencies protect admin routes
- [x] Users can only access their own tenant data (RLS + JWT tenant_id)
- [x] Logout revokes refresh token
- [x] Password reset flow works end-to-end

**Estimated effort:** 4-6 hours

---

### Card 6: PF-100-TEST — Formalize Test Infrastructure ✅ DONE
**PLAN_V2 Reference:** PF-100 (Project Architecture) + Testing  
**Type:** Testing  
**Priority:** HIGH

**Completed:**
- Created `pytest.ini` with async markers and testpaths.
- Created `app/tests/conftest.py` with reusable fixtures for db, client, tenant, user, super admin, auth headers, and tenant context.
- Created `app/tests/helpers.py` with data builders, RLS assertions, and auth-header helper.
- Refactored auth, admin-access, and seed tests to use shared fixtures.
- Added smoke suite covering app imports, DB connection, Alembic head, RLS, seed idempotency, and protected-route rejection.
- Renamed `scripts/test_rls.py` functions to `check_*` to eliminate pytest collection warnings.

**Remaining:**
- CI pipeline (GitHub Actions) requires `DATABASE_URL`/`TEST_DATABASE_URL` secrets; deferred to SCALE-2405A.

**Acceptance criteria:**
- [x] `pytest` runs without import errors
- [x] All auth tests pass
- [x] All tenant isolation tests pass
- [x] `TEST_DATABASE_URL` is supported; fallback to `DATABASE_URL` is documented
- [x] Tests run in < 30 seconds (15-20s typical)

**Estimated effort:** 4-6 hours

---

### Card 7: IMP-700-CSV — Create Import Module with CSV Parser ✅ DONE
**PLAN_V2 Reference:** IMP-700 (CSV Import) + PF-008 (Import Strategy)  
**Type:** New Feature  
**Priority:** HIGH (Oman Market Critical)

**Completed:**
- Created `app/imports/` module with `ImportJob`, `ImportedRow`, schemas, service, routes, and CSV parser.
- Implemented upload, preview, confirm, and cancel endpoints at `/imports/*`.
- Parser supports UTF-8/UTF-8-BOM, common date formats, debit/credit columns, negative amounts, and column aliases.
- Duplicate detection is deterministic per file using `{date}|{amount}|{description}|{reference}`.
- Invalid rows are captured with errors and never imported.
- Valid rows are posted as journal entries through the existing double-entry accounting service.
- Added Alembic migration `9ee380da96d5` with RLS + FORCE RLS on both import tables.
- Added sample CSV fixtures and integration tests; full suite passes.

**Remaining:**
- Excel parser (IMP-701-EXCEL) and SMS parser (IMP-702-SMS) are not part of this card.
- Column mapping UI is not built; the API accepts a JSON mapping object.

**Acceptance criteria:**
- [x] CSV files can be uploaded
- [x] Column mapping is supported via API
- [x] Preview returns all parsed rows
- [x] Duplicates are detected
- [x] Valid rows are imported as journal entries
- [x] Import job status is tracked

**Estimated effort:** 6-8 hours (actual)

---

### Card 8: IMP-702-SMS — Implement SMS Bank Alert Parser ✅ DONE
**PLAN_V2 Reference:** IMP-702 (SMS Import Parser)  
**Type:** New Feature  
**Priority:** HIGH (Oman Market Critical)

**Completed:**
- Implemented rule-based SMS parser in `app/imports/parsers/sms_parser.py`.
- Added bank-specific patterns for Bank Muscat, BankDhofar, Oman Arab Bank, Alizz Islamic Bank, Sohar International, and NBO.
- Added generic fallback parser for unrecognized messages.
- Added `POST /imports/sms/parse` endpoint that reuses `ImportJob` / `ImportedRow`.
- Reused existing `/imports/{job_id}/confirm` to post valid SMS rows as journal entries.
- Added fake SMS fixtures and 15 integration tests.
- No new migration required; `import_type = "sms"` uses the existing `String(20)` column.

**Remaining:**
- Excel parser (IMP-701-EXCEL).
- AI-driven parsing and learning from user corrections (future enhancement).
- SMS import UI (frontend paste interface) is not part of this card.

**Acceptance criteria:**
- [x] SMS from major Omani banks are parsed
- [x] Amount, date, description are extracted
- [x] Debit/credit is detected
- [x] Transactions are created from parsed SMS via confirm endpoint
- [x] RLS remains active on import tables
- [x] Full test suite passes

**Estimated effort:** 6-8 hours (actual)

**Test results:** 74 passed, 1 skipped

---

### Card 9: AI-1201-LLM — Integrate OpenAI LLM Client ✅ DONE
**PLAN_V2 Reference:** AI-1201 (LLM Client and Prompt Management) + AI-1202 (Cost Control)  
**Type:** New Feature  
**Priority:** HIGH (Core Differentiator)

**Completed:**
- Added `openai>=1.0.0` to `requirements.txt` and installed in venv.
- Created `app/ai_cfo/llm/client.py` — OpenAI client wrapper with retry, timeout, and structured output.
- Created `app/ai_cfo/llm/prompts.py` — prompt templates for health insight, cash forecast, anomaly, chat, and spending advice engines.
- Created `app/ai_cfo/llm/cost_control.py` — token tracking, per-tenant daily limits, cost estimation.
- Created `app/ai_cfo/llm/safety.py` — disclaimer injection, content filtering, prompt injection guard.
- Integrated LLM into `AIOrchestrator`, `AIChatService`, and `AIForecastService` with rule-based fallback when LLM unavailable or over budget.
- Fixed `app/routers/ai.py` and `app/middleware/tenant_scoping.py` for proper tenant context.
- Added `AITokenUsage` model integration and cost logging.
- Added unit and integration tests; full suite 89 passed, 1 skipped.

**Remaining:**
- Move remaining rule-based engines (debt optimizer, savings optimizer, goal planner) behind LLM-augmented wrappers.
- Add production rate limits and provider failover.

**Acceptance criteria:**
- [x] OpenAI client is configured and working
- [x] Prompt templates are defined for each engine
- [x] Cost is tracked per request
- [x] Tenant limits are enforced
- [x] Disclaimers are injected
- [x] Fallback to rule-based works
- [x] Token usage is logged to `AITokenUsage` model

**Estimated effort:** 6-8 hours (actual)

**Test results:** 89 passed, 1 skipped

---

### Card 10: BILL-800 / SUB-900 — Build Bills and Subscriptions Routers ✅ DONE
**PLAN_V2 Reference:** BILL-800 (Bill Creation), SUB-900 (Subscription Tracking)  
**Type:** Feature Completion  
**Priority:** MEDIUM-HIGH

**Completed:**
- Added `is_paid` and `paid_at` columns to `bills`; added `status` string column to `subscriptions`.
- Created Alembic migration `c7ec07582862` to track schema changes safely.
- Created `app/services/bill_subscription_service.py` with `BillService`, `SubscriptionService`, and `CommitmentService`.
- Created `app/routers/bills.py` with full CRUD plus `/mark-paid`, `/mark-unpaid`, `/cancel`, `/upcoming`, `/overdue`.
- Created `app/routers/subscriptions.py` with full CRUD plus `/mark-paid`, `/cancel`, `/pause`, `/activate`, `/upcoming-renewals`, `/active`, `/cancelled`.
- Added `/dashboard/api/commitments` endpoint returning upcoming bills, overdue bills, upcoming renewals, monthly subscription total, and total fixed commitments.
- All routes require authentication and tenant membership and use `get_db_with_tenant_context` so RLS remains enforced.
- Added 24 integration tests covering CRUD, status transitions, tenant isolation, RLS, and dashboard commitments.
- Full test suite: 113 passed, 1 skipped.

**Remaining:**
- Bill reminders and subscription renewal alerts require notification delivery (NOTIF-1600).
- Paid-bill accounting-engine integration is deferred to BILL-801A.
- Dashboard widget UI templates are deferred to DB-1104A.

**Acceptance criteria:**
- [x] Bills can be created, edited, deleted
- [x] Subscriptions can be created, edited, deleted
- [x] Dashboard shows upcoming bills and renewals (service/API layer)
- [x] Tenant isolation enforced
- [x] RLS remains active

**Estimated effort:** 4-6 hours (actual)

**Test results:** 113 passed, 1 skipped

---

## Build Sequence Rationale

### Why This Order?

```
Card 1: Database          → DONE ✅
Card 2: RLS               → DONE ✅
Card 2a: Child Table RLS  → DONE ✅
Card 3: Admin Access      → DONE ✅
Card 4: Seed Data         → DONE ✅
Card 5: Auth Completion   → DONE ✅
Card 6: Tests             → Confidence. Protects against regressions.
Card 6: Tests             → DONE ✅
Card 7: CSV Import        → DONE ✅
Card 8: SMS Import        → DONE ✅
Card 9: LLM Integration   → DONE ✅ Intelligence. Core product value.
Card 10: Bills/Subs       → DONE ✅ Features. Completes Financial Life MVP.
Card 11: Notifications    → DONE ✅ Engagement. Reminders for bills/subscriptions.
Card 12: Dashboard Widgets → DONE ✅ Visibility. Surface commitments and notifications.
```

### Dependencies Graph

```
Card 1 (Database) ✅
    │
    ├──→ Card 2 (RLS) ✅ ──→ Card 2a (Child Table RLS) ✅ ──→ Card 3 (Admin Access) ✅
    │       │                                                              │
    │       │                                                              └──→ Card 4 (Seed Data) ✅
    │       │                                                                     │
    │       │                                                                     └──→ Card 5 (Auth) ✅ ──→ Card 6 (Tests) ✅ ──→ Card 7 (CSV Import) ✅
    │       │
    │       └──→ Card 7 (CSV Import) ✅ ──→ Card 8 (SMS Import) ✅
    │               │
    │               └──→ Card 9 (LLM) ✅ ──→ Card 10 (Bills/Subs) ✅
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
| Regressions from changes | ~~Tests (Card 6) catch issues early~~ **DONE** |
| Users can't enter data | CSV/SMS import (Cards 7-8 ✅) enables data entry |
| Product is just accounting | ~~LLM (Card 9) adds intelligence~~ **DONE** |
| Missing core features | ~~Bills/Subs (Card 10) completes MVP~~ **DONE** |

---

## Completed Card 11

### Card 11: NOTIF-1600 — Email Notifications and Bill/Subscription Reminders ✅ DONE
**PLAN_V2 Reference:** NOTIF-1600 (Email Notifications) + BILL-800/SUB-900 (Reminders)  
**Type:** Feature Completion  
**Priority:** MEDIUM-HIGH

**Completed:**
- Added safe email configuration (`EMAIL_BACKEND`, `SMTP_*`, `NOTIFICATIONS_ENABLED`, `BILL_REMINDER_DAYS_DEFAULT`, `SUBSCRIPTION_REMINDER_DAYS_DEFAULT`).
- Extended `Notification` model with `channel`, `status`, `scheduled_for`, `sent_at`, `error_message`, `related_entity_type`, `related_entity_id`.
- Created `app/notifications/channels/email.py` with console / disabled / SMTP backends and `EmailResult`.
- Created `app/notifications/services.py` (`NotificationDeliveryService`) covering CRUD, preferences, email dispatch, and bill/subscription reminder generation with duplicate prevention.
- Added JSON notification routes: `GET/POST /notifications`, `/unread-count`, `/{id}/read`, `/{id}/unread`, `/mark-all-read`, `/preferences`, `/test-email`, `/run-reminders`, `/send-pending-emails`.
- Added `scripts/run_notification_reminders.py` for manual/dev reminder runs.
- Updated Celery stubs in `app/tasks/notifications.py`.
- Created Alembic migrations `196cef681c37` (extend notification model) and `334009b6ab5a` (add `BILL_OVERDUE` enum value, verify RLS).
- Added 20 notification integration tests covering email backends, CRUD, preferences, reminders, duplicate prevention, tenant isolation, and RLS.
- Full test suite: **133 passed, 1 skipped**.

**Remaining:**
- SMS/WhatsApp/push channels (NOTIF-1601+).
- Production Celery scheduling for reminders.
- HTML email templates.

**Test results:** 133 passed, 1 skipped

---

## Completed Card 12

### Card 12: DB-1104A — Bills and Subscriptions Dashboard Widget UI ✅ DONE
**PLAN_V2 Reference:** DB-1104 (Dashboard Widgets) + BILL-800/SUB-900/NOTIF-1600  
**Type:** UI / Feature Completion  
**Priority:** MEDIUM-HIGH

**Completed:**
- Updated `/dashboard/` route to require authentication and tenant membership, load commitments, and pass them to the template.
- Extended `/dashboard/api/commitments` to return UI-ready JSON including serialized upcoming bills, overdue bills, upcoming renewals, totals, counts, and currency.
- Added HTMX-enabled partial routes:
  - `GET /dashboard/partials/commitments`
  - `POST /dashboard/partials/bills/{id}/mark-paid`
  - `POST /dashboard/partials/run-reminders`
- Added templates:
  - `app/templates/dashboard/partials/commitments_widget.html`
  - `app/templates/dashboard/partials/upcoming_bills.html`
  - `app/templates/dashboard/partials/overdue_bills.html`
  - `app/templates/dashboard/partials/upcoming_subscriptions.html`
- Added empty states for no data, summary cards, and quick actions.
- Updated `base.html` navigation with Bills, Subscriptions, and Notifications links.
- Added widget-specific CSS.
- Added defensive error handling around the pre-existing `HealthScoreService`/`Account.current_balance` mismatch so the dashboard renders.
- Added 13 dashboard widget integration tests; full suite **146 passed, 1 skipped**.

**Remaining:**
- Other dashboard widgets (net worth, cash flow, AI insights surface) are still partial.
- HTMX quick actions rely on the client sending the JWT Authorization header; a cookie-based or inline-token mechanism may be added later.

**Test results:** 146 passed, 1 skipped

---

## Completed Card 13

### Card 13: BILL-801A — Bill Payment Posting Through Accounting Engine DONE

**Completed:**
- Bills and subscriptions now post balanced payment journal entries through `AccountingService`.
- Mark-paid validates tenant-owned Asset payment accounts and Expense debit accounts.
- `payment_journal_entry_id` prevents duplicate posting.
- Deterministic tenant-aware references are used: `BILL-{tenant_id}-{bill_id}` and `SUB-{tenant_id}-{subscription_id}`.
- Dashboard bill mark-paid uses the same safe service path and returns a clear missing-account warning.
- Mark-unpaid is blocked after payment posting because journal-entry reversal support is not implemented.

**Migration:** `89f59125ee5e`

---

## Exact Recommended Next Card

### Card 16: FAM-1301 — Family Account Visibility and Shared/Private Data Rules

**Decision:** FAM-1300 established the family profile, member roles, and permission matrix. The next logical step is to enforce those permissions against real financial data by implementing shared/private account visibility rules and wiring the permission matrix into account/transaction reads.

**What to tell the coding agent for FAM-1301:**

> "Implement FAM-1301: Enforce family role permissions on accounts and transactions. Add shared/private account visibility flags, allow heads/parents to share or hide accounts per member, and ensure teen/child/viewer scopes cannot see data beyond their role. Keep RLS active and add focused tests."

---

## Completed Card 15

### Card 15: FAM-1300 — Family Finance Module Foundation DONE

- Created `Family` and `FamilyMember` models with `FamilyRole` enum.
- Added `/family`, `/family/members`, and `/family/permissions` endpoints.
- Auto-creates the creator as family head.
- Added role-based permission matrix (head/parent/adult/teen/child/viewer).
- Alembic revision `417e4cf19e63` with RLS + FORCE RLS on `families` and `family_members`.
- Added 14 integration tests; full suite 173 passed, 1 skipped.

---

## Completed Card 14

### Card 14: ACC-503A - Journal Entry Reversal Support DONE

**Completed:**
- Added `AccountingService.reverse_journal_entry()` to create balanced reversing entries.
- Added reversal metadata on `journal_entries`.
- Added bill/subscription payment reversal journal links.
- Bill mark-unpaid now creates a reversal entry instead of blocking.
- Subscription mark-unpaid and `reverse-payment` now create a reversal entry.
- Reversals are idempotent and use deterministic references: `REV-{tenant_id}-{original_journal_entry_id}`.
- Direct API route added: `POST /accounts/journal-entries/{journal_entry_id}/reverse`.
- Tenant isolation and RLS remain enforced.

**Migration:** `a7c9d2e4f601`

---

## After Card 12

Once these 12 cards are complete, the project will have:

- A working database with all tables and RLS
- Security via RLS + child-table RLS + safe admin access
- Default data seeded
- Complete authentication
- Test coverage for critical paths
- CSV and SMS import (Oman-ready)
- AI intelligence via LLM
- Bills and subscriptions tracking
- Email notifications and bill/subscription reminders
- Bills and subscriptions dashboard widget UI

**Next batch (Cards 14-23):**
- Family finance module (FAM-1300)
- Family finance module (FAM-1300)
- Reports (REP-2000)
- Document OCR (DOC-2100)
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
