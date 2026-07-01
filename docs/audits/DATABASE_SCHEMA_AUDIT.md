# DATABASE_SCHEMA_AUDIT.md

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Audit Date:** 2026-07-01  
**Database Server:** PostgreSQL 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1) on x86_64-pc-linux-gnu  
**Connection:** `postgresql://pf_user:***@172.16.100.39:5433/pf_db`  
**Auditor:** Code Review Agent

---

## Connection Status

| Check | Result |
|-------|--------|
| Database reachable | **YES** |
| Authentication | **SUCCESS** |
| PostgreSQL version | 14.23 (PLAN_V2.md recommends 15+) |
| Server OS | Ubuntu 22.04.3 LTS |
| Connection method | TCP/IP over LAN (172.16.100.39:5433) |

---

## Table Inventory

| Table | Status | Columns | tenant_id | Row Count |
|-------|--------|---------|-----------|-----------|
| *(all tables)* | **NO TABLES EXIST** | — | — | 0 |

**Result:** The database is completely empty. No tables have been created.

---

## Enum Types

| Enum | Status |
|------|--------|
| *(all enums)* | **NO ENUMS EXIST** |

---

## Row-Level Security (RLS) Status

| Table | RLS Enabled | Policies |
|-------|-------------|----------|
| *(all tables)* | **NO TABLES** | N/A |

**Result:** No RLS policies exist because no tables exist. When tables are created, RLS must be explicitly enabled per table with `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`.

---

## Alembic Status

| Check | Result |
|-------|--------|
| `alembic_version` table | **DOES NOT EXIST** |
| Alembic CLI available | **NO** (command not found) |
| `alembic/` directory | Exists but only has `versions/` subdirectory (empty) |
| `alembic.ini` | **NOT FOUND** |
| `alembic/env.py` | **NOT FOUND** |
| Migration history | **NONE** |

**Result:** Alembic has never been initialized. Database schema management is entirely missing.

---

## Model-to-Database Mapping

The codebase defines **26 model classes** across **18 model files**, but **zero of them exist in the database**.

### Models Defined in Code (Expected Tables)

| Model File | Models | Expected Tables |
|------------|--------|-----------------|
| `app/models/tenant.py` | Organization, TenantSubscription | organizations, tenant_subscriptions |
| `app/models/user.py` | User, FamilyMember | users, family_members |
| `app/models/auth.py` | RefreshToken, EmailVerification, PasswordReset | refresh_tokens, email_verifications, password_resets |
| `app/models/accounting.py` | Account, JournalEntry, JournalLine, RecurringTransaction | accounts, journal_entries, journal_lines, recurring_transactions |
| `app/models/budget.py` | Budget, BudgetCategory, BudgetAlert | budgets, budget_categories, budget_alerts |
| `app/models/goal.py` | Goal, GoalContribution | goals, goal_contributions |
| `app/models/loan.py` | Loan, LoanPayment | loans, loan_payments |
| `app/models/subscription.py` | Subscription, Bill | subscriptions, bills |
| `app/models/notification.py` | Notification, NotificationSetting | notifications, notification_settings |
| `app/models/ai.py` | AIInsight, AIReport, AIChatSession, AIChatMessage | ai_insights, ai_reports, ai_chat_sessions, ai_chat_messages |
| `app/models/audit.py` | AuditLog, SystemEvent | audit_logs, system_events |
| `app/models/analytics.py` | UserActivity, FeatureUsage, AITokenUsage | user_activities, feature_usage, ai_token_usage |
| `app/models/asset.py` | Asset, Investment | assets, investments |
| `app/models/credit.py` | CreditProfile, CreditScoreHistory | credit_profiles, credit_score_histories |
| `app/models/document.py` | Document, DocumentType | documents, document_types |
| `app/models/tax.py` | TaxProfile, TaxPayment | tax_profiles, tax_payments |

**Total expected tables:** ~34

**Total existing tables:** 0

---

## tenant_id Coverage Analysis

### Models WITH TenantMixin (tenant_id column in code)

| Model | tenant_id | Notes |
|-------|-----------|-------|
| Organization | No (is the tenant itself) | Root tenant table |
| TenantSubscription | No | Links to organization_id |
| User | No | Links to organization_id |
| FamilyMember | No | Links to user_id |
| Account | **Yes** | TenantMixin |
| JournalEntry | **Yes** | TenantMixin |
| JournalLine | **Yes** | TenantMixin |
| RecurringTransaction | **Yes** | TenantMixin |
| Budget | **Yes** | TenantMixin |
| BudgetAlert | **Yes** | TenantMixin |
| Goal | **Yes** | TenantMixin |
| Loan | **Yes** | TenantMixin |
| Subscription | **Yes** | TenantMixin |
| Bill | **Yes** | TenantMixin |
| Notification | **Yes** | TenantMixin |
| AIInsight | **Yes** | TenantMixin |
| AIReport | **Yes** | TenantMixin |
| AIChatSession | **Yes** | TenantMixin |
| AuditLog | No (has tenant_id field directly) | Has tenant_id but not via TenantMixin |
| UserActivity | No (has tenant_id field directly) | Has tenant_id but not via TenantMixin |
| FeatureUsage | No (has tenant_id field directly) | Has tenant_id but not via TenantMixin |
| AITokenUsage | No (has tenant_id field directly) | Has tenant_id but not via TenantMixin |

### Models WITHOUT tenant_id (System/Global Tables)

| Model | Reason |
|-------|--------|
| RefreshToken | User-scoped, not tenant-scoped |
| EmailVerification | User-scoped |
| PasswordReset | User-scoped |
| BudgetCategory | Budget-scoped (via budget_id) |
| GoalContribution | Goal-scoped (via goal_id) |
| LoanPayment | Loan-scoped (via loan_id) |
| NotificationSetting | User-scoped |
| AIChatMessage | Session-scoped (via session_id) |
| SystemEvent | System-wide |
| Asset | Not audited in detail |
| Investment | Not audited in detail |
| CreditProfile | Not audited in detail |
| CreditScoreHistory | Not audited in detail |
| Document | Not audited in detail |
| DocumentType | Not audited in detail |
| TaxProfile | Not audited in detail |
| TaxPayment | Not audited in detail |

### Assessment

- **Good:** Most financial models have `tenant_id` via `TenantMixin`
- **Concern:** `User` and `Organization` use `organization_id` instead of `tenant_id` — naming inconsistency
- **Concern:** Some models have `tenant_id` directly (not via mixin) — inconsistency
- **Critical:** Even though `tenant_id` exists in code, no tables exist in the database, so no actual isolation is enforced

---

## Tenant Isolation Assessment

### Current State: Application-Level Only

| Layer | Isolation Method | Status |
|-------|-----------------|--------|
| Application (routes) | `request.state.tenant_id` extracted from JWT | **Implemented** |
| Application (queries) | Explicit `.where(Model.tenant_id == tenant_id)` | **Implemented** |
| Database (RLS) | No policies | **NOT IMPLEMENTED** |
| Database (RLS context) | No `SET LOCAL app.current_tenant_id` | **NOT IMPLEMENTED** |

### Risk Assessment

| Risk | Level | Explanation |
|------|-------|-------------|
| Missing `WHERE tenant_id = ?` in query | **HIGH** | Any forgotten filter exposes cross-tenant data |
| SQL injection bypassing app filters | **HIGH** | Raw SQL or complex queries could skip filters |
| Developer error | **HIGH** | New developer might not know to add tenant_id filter |
| Compromised application | **HIGH** | Attacker with DB access sees all data |
| RLS as defense in depth | **MISSING** | No final line of defense |

### Required RLS Implementation

When tables are created, the following must be done:

```sql
-- For each tenant-scoped table:
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON accounts
    USING (tenant_id = current_setting('app.current_tenant_id', true)::INTEGER);

-- Set tenant context per connection:
SET LOCAL app.current_tenant_id = '123';
```

**Tables requiring RLS:** accounts, journal_entries, journal_lines, recurring_transactions, budgets, budget_alerts, goals, loans, subscriptions, bills, notifications, ai_insights, ai_reports, ai_chat_sessions, audit_logs, user_activities, feature_usage, ai_token_usage

---

## Schema/Model Mismatches

### Issue 1: Naming Inconsistency — "Organization" vs "Tenant"

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| `Tenant` | `Organization` | Low — functionally equivalent, but confusing for new developers |
| `tenant_id` | `organization_id` (on User) | Medium — breaks mental model and searchability |

**Recommendation:** Add alias or rename. If renaming is too disruptive, document the mapping clearly.

### Issue 2: Account Type as String vs Enum

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| `AccountType` enum | `String(50)` for `account_type` | Medium — no DB-level validation, typos possible |

**Recommendation:** Add `AccountType` enum and migrate.

### Issue 3: Missing `created_by` / `updated_by` Audit Fields

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| `created_by`, `updated_by` on all tables | Only `created_at`, `updated_at` in `TimestampMixin` | Medium — cannot track who made changes |

**Recommendation:** Add `created_by` and `updated_by` to `TimestampMixin` or create `AuditMixin`.

### Issue 4: Currency Default Mismatch

| PLAN_V2.md | Code | Database | Impact |
|------------|------|----------|--------|
| OMR default | `CURRENCY_DEFAULT="OMR"` | Not applicable (no DB) | Low — config is correct |
| 3 decimal places for OMR | `CURRENCY_DECIMALS=3` | Not applicable | Low — config is correct |

### Issue 5: Missing `uuid` Primary Keys

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| UUID primary keys | Integer primary keys | Low — integers are fine for v1, but UUIDs are more secure for multi-tenant |

**Recommendation:** Acceptable for v1. Consider UUID migration in v2.

### Issue 6: Decimal Precision

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| `Decimal(19, 4)` | `Numeric(15, 3)` | Low — 15,3 is sufficient for OMR (3 decimals) but limits very large amounts |

**Recommendation:** Acceptable for v1. OMR uses 3 decimals, so `Numeric(15, 3)` is correct.

### Issue 7: Missing `is_system` on Account

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| `is_system` flag | Not present | Low — prevents accidental deletion of system accounts |

**Recommendation:** Add `is_system` to Account model.

### Issue 8: `current_balance` on Account Model

| PLAN_V2.md | Code | Impact |
|------------|------|--------|
| Calculated from journal lines | `current_balance` column exists | Medium — denormalized field risks inconsistency |

**Recommendation:** Either remove `current_balance` and calculate dynamically, or add triggers to keep it updated. For v1, calculating on read is safer.

---

## Indexes Analysis

Since no tables exist, no indexes exist. When tables are created, the following indexes should be verified:

### Required Indexes (from model code)

| Table | Column | Indexed in Code? | Critical? |
|-------|--------|------------------|-----------|
| organizations | slug | Yes (`index=True`) | Yes |
| organizations | plan | No | No |
| users | email | Yes (`index=True`) | Yes |
| users | organization_id | Yes (FK implies index) | Yes |
| accounts | tenant_id | Yes (`index=True` via TenantMixin) | Yes |
| accounts | code | No | Yes (for lookups) |
| accounts | account_type | No | Yes (for reporting) |
| journal_entries | tenant_id | Yes (via TenantMixin) | Yes |
| journal_entries | date | Yes (`index=True`) | Yes |
| journal_lines | journal_entry_id | Yes (FK implies index) | Yes |
| journal_lines | account_id | Yes (FK implies index) | Yes |
| budgets | tenant_id | Yes (via TenantMixin) | Yes |
| goals | tenant_id | Yes (via TenantMixin) | Yes |
| loans | tenant_id | Yes (via TenantMixin) | Yes |
| ai_insights | tenant_id | Yes (via TenantMixin) | Yes |
| ai_insights | insight_type | No | Yes (for filtering) |
| ai_insights | priority | No | Yes (for sorting) |
| ai_reports | tenant_id | Yes (via TenantMixin) | Yes |
| ai_reports | report_type | No | Yes (for filtering) |
| notifications | user_id | Yes (FK implies index) | Yes |
| notifications | tenant_id | Yes (via TenantMixin) | Yes |

### Missing Indexes to Add

- `accounts.code` + `tenant_id` (composite, unique per tenant)
- `journal_entries.date` + `tenant_id` (composite, for date range queries)
- `ai_insights.created_at` + `tenant_id` (composite, for recent insights)
- `ai_reports.period_start` + `period_end` + `tenant_id` (composite, for report lookups)

---

## Data Presence

| Check | Result |
|-------|--------|
| Any user data | **NO** — database is empty |
| Any financial data | **NO** — database is empty |
| Any AI data | **NO** — database is empty |
| Any test data | **NO** — database is empty |

**Safety:** No sensitive data exposure risk. Database is completely clean.

---

## Safety Warnings

### WARNING 1: Database Initialization Risk
When `init_db()` is called (in `app/models/database.py`), it runs `Base.metadata.create_all()`. This will:
- Create all tables at once
- Use the current model definitions
- **Not** create RLS policies
- **Not** create Alembic version entry

**Risk:** If models change later, there's no migration path. The database would need to be dropped and recreated.

**Mitigation:** Set up Alembic BEFORE running `init_db()` in production. Use Alembic for all schema changes.

### WARNING 2: Async Engine with Sync URL Mismatch

| Config | Value |
|--------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://...` (async) |
| `DATABASE_URL_SYNC` | `postgresql://...` (sync) |
| Audit connection | Used `postgresql://...` (sync via psycopg2) |

The async engine uses `asyncpg` driver. The sync URL uses `psycopg2`. Both are installed. This is correct for hybrid usage (async for app, sync for Celery/background tasks).

### WARNING 3: Empty Database Means No Runtime Validation

All models exist only in Python code. Without actual database tables:
- No foreign key constraints are enforced
- No unique constraints are tested
- No index performance is validated
- No data type compatibility is verified

**Recommendation:** Create tables immediately and run basic CRUD tests.

### WARNING 4: PostgreSQL 14 vs 15+ RLS Features

PostgreSQL 14 supports RLS fully. PostgreSQL 15+ adds:
- Row security policies on views
- Improved performance for RLS with partitioning

**Assessment:** PostgreSQL 14 is sufficient for v1. No immediate upgrade needed.

---

## Recommendations

### Immediate (This Session)

1. **Create `.env` file** with `DATABASE_URL=postgresql://pf_user:W0rk%40786@172.16.100.39:5433/pf_db`
2. **Install Alembic:** `pip install alembic` and `alembic init alembic`
3. **Configure Alembic** to use the async database URL
4. **Generate initial migration:** `alembic revision --autogenerate -m "Initial schema"`
5. **Run migration:** `alembic upgrade head`

### Short Term (This Week)

6. **Verify all tables created** with correct columns and types
7. **Add RLS policies** to all tenant-scoped tables
8. **Test RLS** with a simple query: verify user A cannot see user B's data
9. **Add composite indexes** for common query patterns
10. **Seed default data:** Chart of Accounts, default categories, system settings

### Medium Term (Next 2 Weeks)

11. **Add `created_by`/`updated_by` to audit mixins**
12. **Rename `Organization` to `Tenant`** (or add alias)
13. **Add `AccountType` enum** and migrate
14. **Add `is_system` to Account model**
15. **Decide on `current_balance` strategy** (calculated vs stored)

---

*End of DATABASE_SCHEMA_AUDIT.md*
