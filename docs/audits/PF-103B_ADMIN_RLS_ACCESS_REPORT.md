# PF-103B — Safe Super Admin Tenant Access and RLS Admin Design

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Card ID:** PF-103B  
**Title:** Safe Super Admin Tenant Access and RLS Admin Design  
**Date:** 2026-07-02  
**Status:** COMPLETE  
**Alembic Revision:** `542823443f9e`  
**Previous Revision:** `df41f5ea2f46`  

---

## Summary

This card implemented a safe super-admin support access model that lets support staff work inside a single tenant's context at a time without weakening PostgreSQL Row-Level Security (RLS).

**Key security result:** No true RLS bypass was implemented. The normal application database user cannot query across tenants. Admin access works by selecting one tenant, providing a reason, and setting `app.current_tenant_id` to that tenant's ID. Normal RLS policies continue to filter every query.

At the end of this card:
- `admin_access_sessions` table stores audited support sessions.
- `app/core/admin_context.py` provides safe tenant-context helpers.
- `app/services/admin_access_service.py` wraps the helpers for routes and tests.
- `app/routers/admin.py` exposes `/admin/support-access/*` endpoints.
- 9 new integration tests pass.
- FORCE ROW LEVEL SECURITY remains enabled on all tenant-scoped tables.

---

## Pre-flight Safety Checks

| Check | Result |
|-------|--------|
| `git status` | On main; only `Next_KIMI_prompt.txt` untracked; no secrets staged |
| `.env` ignored | YES — `.gitignore` contains `.env` and `.env.*` |
| Alembic current | `542823443f9e` (head) |
| Previous revision | `df41f5ea2f46` |
| Database connection | SUCCESS — PostgreSQL 14.23 |
| RLS enabled | 30 tables |
| FORCE RLS | Still enabled on all 30 tenant-scoped tables |
| Data deleted/reset | NONE |

---

## Admin Access Design

### Principle

Super-admin access is **one tenant at a time**, **audited**, **reasoned**, and **time-bounded**. The application never grants a universal view of all tenants.

### What was avoided

| Dangerous approach | Status |
|--------------------|--------|
| Broad RLS bypass for normal app user | NOT implemented |
| `current_user = 'pf_user'` as a bypass condition | NOT used |
| `app.bypass_rls=true` GUC flag | NOT created |
| Disabling FORCE ROW LEVEL SECURITY | NOT done |
| Web endpoint that returns all-tenant financial data | NOT created |

### What was implemented

1. **Admin selects one tenant** (`target_organization_id`).
2. **Admin provides a reason** (required, max 2000 chars).
3. **System creates an `AdminAccessSession`** with:
   - `admin_user_id`
   - `target_organization_id`
   - `reason`
   - `access_started_at`
   - `access_expires_at` (default 30 minutes, max 8 hours)
   - `ip_address` and `user_agent` (from request headers)
   - `status` (`active` / `expired` / `revoked`)
4. **System sets `SET LOCAL app.current_tenant_id = '<tenant_id>'`** on the same database connection.
5. **All subsequent queries are filtered by normal RLS policies.**
6. **Session must be explicitly ended** or it expires automatically.

### Admin access lifecycle

```
Super Admin
    │
    ▼
POST /admin/support-access/start
    │
    ├──► verify is_superuser
    ├──► require reason
    ├──► verify target organization exists
    ├──► create AdminAccessSession (audit record)
    ├──► SET LOCAL app.current_tenant_id = <target_org_id>
    └──► return session
    │
    ▼
Admin operates inside Tenant A context only
    │
    ▼
POST /admin/support-access/{id}/end
    │
    ├──► mark session revoked
    ├──► SET LOCAL app.current_tenant_id = ''
    └──► return session
```

---

## Tables Changed

### New table: `admin_access_sessions`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | — |
| `admin_user_id` | INTEGER FK → users.id | Indexed |
| `target_organization_id` | INTEGER FK → organizations.id | Indexed |
| `reason` | TEXT NOT NULL | Required justification |
| `access_started_at` | DATETIME NOT NULL | UTC |
| `access_expires_at` | DATETIME NOT NULL | Default 30 minutes |
| `access_ended_at` | DATETIME NULL | Set on revoke/end |
| `ip_address` | VARCHAR(45) | From request metadata |
| `user_agent` | VARCHAR(500) | From request metadata |
| `status` | VARCHAR(20) | `active` / `expired` / `revoked`, check constraint |
| `created_at` / `updated_at` | DATETIME | Timestamp mixin |

**RLS:** None. This is a global audit table that supervises support access itself. It does not contain financial data.

### Files changed

| File | Change |
|------|--------|
| `app/models/admin_access.py` | New `AdminAccessSession` model and `AdminAccessStatus` enum |
| `app/models/__init__.py` | Imported `AdminAccessSession` and `AdminAccessStatus` |
| `app/core/admin_context.py` | New helpers for starting/ending/verifying admin tenant context |
| `app/core/rls.py` | Fixed `set_tenant_context_async` to inline the validated tenant ID for asyncpg compatibility |
| `app/services/admin_access_service.py` | New service wrapper |
| `app/schemas/admin.py` | New Pydantic request/response models |
| `app/routers/admin.py` | Added `/admin/support-access/*` endpoints |
| `alembic/versions/542823443f9e_add_admin_access_sessions_table.py` | New migration |
| `app/tests/integration/test_admin_access.py` | New integration tests |
| `docs/audits/PF-103B_ADMIN_RLS_ACCESS_REPORT.md` | This report |
| `docs/audits/PLAN_V2_CARD_STATUS.md` | Updated |
| `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md` | Updated |

---

## RLS Behavior

### No bypass for the app user

The application database user continues to obey RLS on every tenant-scoped table. Setting `app.current_tenant_id` is the only mechanism, and it is scoped to the current transaction via `SET LOCAL`.

### Admin in Tenant A cannot see Tenant B

Tests confirm that after `start_support_session(target=Tenant A)`:
- `SELECT * FROM goals` returns only Tenant A goals.
- Tenant B goals are invisible.
- Clearing `app.current_tenant_id` returns zero rows.

### FORCE RLS remains enabled

Verified on `accounts` and all other tenant-scoped tables:

```sql
SELECT relforcerowsecurity FROM pg_class
WHERE relname = 'accounts' AND relnamespace = 'public'::regnamespace;
-- returns true
```

---

## Break-Glass Design (Documented Only)

A true database-level bypass was **not** implemented in the web app. If emergency DBA access is ever required, it should follow a separate procedure:

**Future card:** `PF-103D — Break-Glass DBA Access Procedure`

Requirements:
- Separate database role (not the web app user).
- No web or API exposure.
- Manual approval workflow.
- Full audit logging.
- Limited operational use only.

---

## Routes

| Method | Route | Purpose | Authorization |
|--------|-------|---------|---------------|
| GET | `/admin/` | Admin dashboard | super admin |
| GET | `/admin/tenants` | List tenants | super admin |
| POST | `/admin/support-access/start` | Start support session | super admin |
| POST | `/admin/support-access/{id}/end` | End support session | super admin (own session) |
| GET | `/admin/support-access/active` | Get active session | super admin |
| GET | `/admin/support-access/recent` | List recent sessions | super admin |

---

## Test Results

### Admin Access Integration Tests

```
app/tests/integration/test_admin_access.py::test_super_admin_can_start_support_session[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_normal_user_cannot_start_support_session[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_tenant_admin_cannot_access_other_tenant[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_start_session_requires_reason[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_expired_session_rejected_for_context[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_admin_context_sees_only_target_tenant[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_no_all_tenant_query_in_admin_mode[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_audit_event_created[asyncio] PASSED
app/tests/integration/test_admin_access.py::test_force_rls_remains_enabled[asyncio] PASSED
```

### Full Test Suite

```
21 passed, 8 warnings in 2.41s
```

Breakdown:
- 9 new admin access tests (this card)
- 6 child-table RLS tests (PF-103C)
- 6 original RLS tests (PF-103A)

### Verification Commands

| Command | Result |
|---------|--------|
| `python -m compileall app` | PASS |
| `alembic current` | `542823443f9e (head)` |
| `alembic history` | 4 revisions, linear history |
| `alembic upgrade head` | Already at head, no errors |
| `python scripts/inspect_db.py` | PASS — 40 tables, 12 enums, 30 RLS-enabled |
| `python -m pytest -q` | 21 passed |

---

## Alembic Revision

| Property | Value |
|----------|-------|
| Revision ID | `542823443f9e` |
| Message | Add admin access sessions table |
| Down revision | `df41f5ea2f46` |
| Status | head (current) |

---

## Remaining Risks

1. **Admin session expiry enforcement** — Expired sessions are rejected when re-applying context, but a background job should periodically call `expire_stale_sessions()` to mark them `expired`. This is not yet scheduled.
2. **Single active session per admin** — The service blocks starting a second active session, but this check is time-based and relies on `expire_stale_sessions()` being run.
3. **Audit-only table** — `admin_access_sessions` is global and unprotected by RLS by design. It contains no financial data, only support metadata.
4. **IP/user_agent source** — The service reads `X-Forwarded-For` then falls back to `request.client.host`. In production, ensure the proxy setup is trusted before relying on `X-Forwarded-For`.
5. **No dedicated admin DB role** — The design intentionally avoids a separate role. If future operations need true break-glass access, implement `PF-103D` with a separate role and no web path.
6. **Admin dashboard stats** — Existing `/admin/` and `/admin/tenants` endpoints still query global tables (`users`, `organizations`) which is acceptable for admin dashboards but must not be extended to tenant-scoped financial tables without setting tenant context.

---

## Recommended Next Card

### SAAS-200-SEED — Seed Default Data (Chart of Accounts, Categories, Plans)

**Why next:** The RLS and admin-access foundation is now complete. Before onboarding real users, the application needs default data: a Chart of Accounts, transaction categories, and subscription plans. Seeding is safe now that tenant isolation is enforced.

**Acceptance criteria:**
- Create `scripts/seed_data.py`.
- Seed default COA, categories, and plans idempotently.
- Seed data must respect tenant context (use `SET LOCAL app.current_tenant_id`).
- Document the seeding procedure.

---

## Conclusion

PF-103B delivers a safe, audited, one-tenant-at-a-time support access model. It avoids every dangerous bypass pattern, keeps FORCE RLS active, and ensures that even super admins cannot accidentally query all tenant financial data. The only way to access tenant-scoped data is through the same RLS policies that protect normal users.

---

*End of PF-103B_ADMIN_RLS_ACCESS_REPORT.md*
