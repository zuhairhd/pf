# SAAS-200-SEED — Seed Default Platform Data

## AI Personal CFO / Financial Digital Twin SaaS Platform

**Card ID:** SAAS-200-SEED  
**Title:** Seed Default Platform Data  
**Date:** 2026-07-02  
**Status:** COMPLETE  
**Alembic Revision:** `542823443f9e` (no schema migration required for this card)  

---

## Summary

This card created safe, repeatable, idempotent seed data so the application is usable for development and future onboarding. The seed script respects PostgreSQL Row-Level Security (RLS) by setting `app.current_tenant_id` for every tenant-scoped insert. No real personal financial data, no hardcoded passwords, and no secrets were committed.

At the end of this card:
- Global platform plan configurations are defined in code.
- A development tenant (`Development Family`, slug `dev-family`) exists.
- A development super-admin user exists with email/password from environment variables or a generated temporary password.
- A complete OMR-friendly Chart of Accounts (31 accounts) is seeded under the development tenant.
- A default monthly household budget with 14 categories is seeded under the development tenant.
- Default notification preferences are seeded for the development user.
- Each seed run writes a `system_events` audit record.
- The seed script is idempotent: running it twice creates no duplicates.
- 9 new seed tests pass, and the full suite is green.

---

## Pre-flight Checks

| Check | Result |
|-------|--------|
| `git status` | Clean except `Next_KIMI_prompt.txt` untracked |
| `.env` ignored | YES — `.gitignore` contains `.env` and `.env.*` |
| `.env.local` ignored | YES — covered by `.env.*` |
| Alembic current | `542823443f9e` (head) |
| Database connection | SUCCESS — PostgreSQL 14.23 |
| RLS enabled | 30 tables |
| FORCE RLS | Still enabled |
| Row counts before seed | accounts: 0, budgets: 0, budget_categories: 0, notification_settings: 0, organizations: 62, system_events: 0, users: 93 |

**Note on row counts:** `scripts/inspect_db.py` reports `0` for tenant-scoped tables such as `accounts` and `budgets` because it does not set a tenant context; RLS correctly hides those rows. Tenant-scoped counts were verified inside the appropriate tenant context in tests.

---

## Files Changed

| File | Change |
|------|--------|
| `app/seeds/__init__.py` | New package init exposing `seed_all_default_data` |
| `app/seeds/default_data.py` | New idempotent async seed logic |
| `scripts/seed_default_data.py` | New CLI entry point (`--dev`) |
| `app/tests/integration/test_seed_default_data.py` | New integration tests |
| `docs/audits/SAAS-200-SEED_IMPLEMENTATION_REPORT.md` | This report |
| `docs/audits/PLAN_V2_CARD_STATUS.md` | Updated |
| `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md` | Updated |

---

## Seed Data Created

### 1. Global platform plan configurations

No dedicated `plans` table exists in the current schema. Plan configuration is stored as a Python dict (`PLAN_CONFIGS`) and applied to the development tenant's limit fields.

| Plan | max_users | max_transactions | max_ai_requests_per_day | max_storage_mb |
|------|-----------|------------------|-------------------------|----------------|
| free | 1 | 100 | 5 | 100 |
| premium | 2 | 1,000 | 50 | 1,024 |
| family | 6 | 2,000 | 100 | 5,120 |
| professional | 10 | 10,000 | 500 | 20,480 |

**Schema gap:** A separate `Plan`/`SubscriptionPlan` table does not exist. Limits are columns on `organizations`. Future card `SAAS-202` can normalize this.

### 2. Development tenant

| Field | Value |
|-------|-------|
| name | Development Family |
| slug | dev-family |
| plan | family |
| currency | OMR |
| status | active |

### 3. Development super-admin user

| Field | Value |
|-------|-------|
| email | `DEV_SUPERUSER_EMAIL` or `dev@example.local` |
| password | `DEV_SUPERUSER_PASSWORD` or a generated 20-char temporary password printed once |
| role | owner |
| is_superuser | true |
| currency | OMR |
| timezone | Asia/Muscat |

Password handling:
- If `DEV_SUPERUSER_PASSWORD` is set, it is hashed and applied.
- If it is missing, a cryptographically secure temporary password is generated **only on first creation** and printed once to the console.
- Running the seed again for an existing user does **not** regenerate or print a password unless the env var is provided.

### 4. Chart of Accounts (31 accounts)

Seeded under the development tenant with `tenant_id = <dev_org_id>` and RLS context set.

| Type | Count | Examples |
|------|-------|----------|
| Asset | 8 | Cash, Bank Muscat, OAB Bank, Alizz Bank, Wallet, Savings Account |
| Liability | 4 | Credit Card, Personal Loan, Family Loan, Sister Account Liability |
| Equity | 2 | Opening Balance, Retained Earnings |
| Income | 3 | Salary, Rental Income, Other Income |
| Expense | 14 | Food & Groceries, Dining Out, Transport, Fuel, Utilities, Internet & Phone, Education, Medical, Family Support, Housemaid / Domestic Help, Insurance, Bank Charges, Charity, Miscellaneous |

### 5. Default budget and categories

| Field | Value |
|-------|-------|
| name | Monthly Household Budget |
| period | MONTHLY |
| total_budgeted | OMR 1,420.000 |
| categories | 14 (one per major expense account) |

### 6. Notification preferences

8 default `NotificationSetting` rows for the development user, all with `in_app=True` and `email=False` until SMTP is configured.

### 7. Audit record

Each successful seed run inserts one `SystemEvent` row:
- `event_type`: `info`
- `source`: `seed_default_data`
- `message`: `Default development seed data applied.`
- `details_json`: `{"organization_id": <id>, "organization_slug": "dev-family", "user_id": <id>}`

---

## How to Run

```bash
# Development seed (creates/updates dev tenant, super-admin, COA, budget, defaults)
python scripts/seed_default_data.py --dev

# With explicit credentials
DEV_SUPERUSER_EMAIL=admin@example.local DEV_SUPERUSER_PASSWORD=SecurePass123 python scripts/seed_default_data.py --dev
```

The script is idempotent and safe to run multiple times.

---

## RLS Handling

All tenant-scoped inserts set the PostgreSQL configuration variable:

```sql
SET LOCAL app.current_tenant_id = '<dev_org_id>';
```

This satisfies RLS policies on:
- `accounts`
- `budgets`
- `budget_categories` (join-based RLS through `budgets`)
- `tenant_subscriptions` (organization_id-based RLS)

The context is cleared at the end of the seed run:

```sql
SET LOCAL app.current_tenant_id = '';
```

---

## Idempotency Proof

Running the seed script a second time produced:

```
Seed completed successfully.
  Organization: Development Family (id=77)
  User:         dev@example.local (id=205)
  Accounts:     31
  Budget:       Monthly Household Budget
  Notification settings: 0
```

`Notification settings: 0` confirms existing rows were found and not duplicated. Account and budget counts remained at 31 and 1 respectively.

The `test_seed_is_idempotent` test programmatically verifies this by comparing counts before and after a second seed invocation.

---

## Test Results

### New Seed Tests

```
app/tests/integration/test_seed_default_data.py::test_seed_script_runs_successfully[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_seed_is_idempotent[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_development_tenant_exists_with_plan_limits[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_development_user_is_super_admin[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_chart_of_accounts_belongs_to_dev_tenant[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_tenant_scoped_rows_invisible_without_context[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_budget_categories_linked_to_expense_accounts[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_force_rls_remains_enabled[asyncio] PASSED
app/tests/integration/test_seed_default_data.py::test_env_files_are_ignored[asyncio] PASSED
```

### Full Test Suite

```
30 passed, 8 warnings in 4.24s
```

Breakdown:
- 9 seed tests (this card)
- 9 admin access tests (PF-103B)
- 6 child-table RLS tests (PF-103C)
- 6 original RLS tests (PF-103A)

### Verification Commands

| Command | Result |
|---------|--------|
| `python -m compileall app scripts/seed_default_data.py` | PASS |
| `alembic current` | `542823443f9e (head)` |
| `alembic history` | 4 revisions, linear history |
| `python scripts/inspect_db.py` | PASS — 40 tables, 30 RLS-enabled |
| `python scripts/seed_default_data.py --dev` | PASS, idempotent |
| `python scripts/seed_default_data.py --dev` (second run) | PASS, no duplicates |
| `python -m pytest -q` | 30 passed |

---

## Schema Gaps Found

1. **No dedicated `plans` table.** Plan limits are columns on `organizations`. The current enum `SubscriptionPlan` drives behavior, but limits are duplicated per organization. Recommended future card: `SAAS-202` — normalize plans into a `plans` table and reference it from `organizations`.

2. **No general transaction categories table.** `BudgetCategory` is tied to a `Budget`. A standalone `TransactionCategory` table would be useful for imports and transaction classification. Recommended future card: `TRX-604A — Transaction Category Model and Seed Data`.

3. **No tenant-scoped row counts without context.** `scripts/inspect_db.py` reports `0` for tenant-scoped tables because it does not set `app.current_tenant_id`. This is correct RLS behavior but may confuse operators. A future improvement could add an optional tenant context flag to the inspector.

---

## Safety Notes

- No real personal financial data was seeded.
- No hardcoded passwords exist in code.
- The temporary password is generated at runtime and printed once; it is never logged to a file or committed.
- `.env` and `.env.*` are ignored by Git.
- RLS and FORCE RLS were not disabled or bypassed.
- No manual database edits were made.
- No unrelated product features were built.

---

## Recommended Next Card

### AUTH-300-FIX — Complete Authentication Flow (Email, RBAC Guards)

**Why next:** Seed data and a development super-admin now exist, but the authentication flow still has placeholders (email sending, token expiry, RBAC route guards). Completing auth is the gateway to making the seeded tenant and user actually usable.

**Acceptance criteria:**
- Implement email sending (SMTP or console backend for dev).
- Fix access/refresh token expiry (15 min / 7 days per PLAN_V2.md).
- Add `require_role` decorators and resource-level permission checks.
- Add logout endpoint that revokes refresh tokens.
- End-to-end password reset and email verification flows work.

---

## Conclusion

SAAS-200-SEED delivers safe, idempotent default data for development. The application now has a working development tenant, a super-admin user, a full Chart of Accounts, a default budget, and notification preferences — all protected by RLS. The seed script is repeatable and tested, and the security foundation from PF-103A/PF-103C/PF-103B remains intact.

---

*End of SAAS-200-SEED_IMPLEMENTATION_REPORT.md*
