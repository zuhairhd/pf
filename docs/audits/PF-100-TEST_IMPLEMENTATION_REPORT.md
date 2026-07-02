# PF-100-TEST — Formalize Test Infrastructure for Auth, RLS, Tenant Isolation, and Seed Data

**Card ID:** PF-100-TEST  
**Project:** PF AI Personal Finance SaaS  
**Date:** 2026-07-02  
**Alembic Head:** `542823443f9e` (no new migration created for this card)  
**Status:** ✅ DONE

---

## Summary

This card establishes a reusable, documented test foundation for the PF project. Before this work, tests were spread across integration modules with duplicated setup code, no project-level pytest configuration, and no shared fixtures. Now there is a single `app/tests/conftest.py`, a helper module, clear markers, a smoke suite, and a documented test-database strategy.

Key outcomes:

- `pytest.ini` configures discovery, markers, and quiet output.
- `app/tests/conftest.py` provides shared async fixtures for DB sessions, HTTP clients, tenants, users, super admins, auth headers, and tenant context.
- `app/tests/helpers.py` centralizes synthetic data creation, RLS assertions, and auth-header generation.
- Existing auth, admin-access, and seed tests were refactored to use shared fixtures without reducing coverage.
- `scripts/test_rls.py` was converted from pytest-collectable `test_*` functions to `check_*` functions so it no longer pollutes pytest output.
- A new smoke suite verifies app imports, DB connectivity, Alembic head, RLS status, seed idempotency, and protected-route rejection.
- Warnings dropped from 8 to 2 (both are existing Pydantic `class Config` deprecations).
- Test count grew from 45 passed to **46 passed + 1 skipped**.

---

## Files Changed

| File | Change |
|------|--------|
| `pytest.ini` | New pytest configuration: testpaths, markers, naming conventions. |
| `app/tests/__init__.py` | New package marker so `app.tests.helpers` is importable. |
| `app/tests/conftest.py` | New shared fixtures: `async_engine`, `db`, `transactional_db`, `client`, `tenant`, `tenant_pair`, `test_user_credentials`, `test_user`, `super_admin_credentials`, `super_admin`, `auth_headers`, `admin_auth_headers`, `tenant_context`, `unique`. |
| `app/tests/helpers.py` | New helper functions: `unique`, `create_test_organization`, `create_test_user`, `auth_headers_for`, `rls_status`, `assert_rls_enabled`, `count_rows`. |
| `app/tests/integration/test_auth.py` | Refactored to use conftest fixtures and helpers; removed duplicated engine/session/client fixtures. |
| `app/tests/integration/test_admin_access.py` | Refactored to use shared `db`, `tenant_pair`, and `unique` fixtures; local cast fixture now builds on shared primitives. |
| `app/tests/integration/test_seed_default_data.py` | Refactored to use shared `db` and `tenant_context` fixtures; removed duplicated setup. |
| `app/tests/integration/test_smoke.py` | New smoke tests for app health, DB, migrations, RLS, seed idempotency, and auth. |
| `scripts/test_rls.py` | Renamed manual-verification functions from `test_*` to `check_*` to avoid pytest collection warnings; prefers `DATABASE_URL` env with fallback. |

---

## Test Structure Before / After

### Before

- No `pytest.ini`.
- No shared `conftest.py`.
- Each integration module duplicated database URL parsing, engine creation, and session fixtures.
- `scripts/test_rls.py` was collected by pytest and produced `PytestReturnNotNoneWarning` warnings.
- 45 tests passed with 8 warnings.

### After

- `pytest.ini` sets `testpaths = app/tests`, markers, and quiet mode.
- `app/tests/conftest.py` provides reusable, documented fixtures.
- `app/tests/helpers.py` exposes helper functions used by fixtures and tests.
- Existing modules are slimmer and consistent.
- Smoke tests give fast environment validation.
- 46 tests pass + 1 skipped (dev-password smoke test) with 2 warnings.

---

## Fixtures Created

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `unique` | function | Generate collision-free test strings. |
| `async_engine` | function | Per-test async SQLAlchemy engine. |
| `db` | function | Async session for direct DB setup/assertions (no auto-rollback; supports internal commits). |
| `transactional_db` | function | Async session wrapped in a savepoint that rolls back after the test. |
| `client` | function | `httpx.AsyncClient` against the FastAPI app with `get_db` overridden to a fresh session. |
| `tenant` | function | Single synthetic `Organization`. |
| `tenant_pair` | function | Two synthetic `Organization` rows for cross-tenant tests. |
| `test_user_credentials` | function | Verified active tenant user + password. |
| `test_user` | function | The user object from `test_user_credentials`. |
| `super_admin_credentials` | function | Verified active super admin + password. |
| `super_admin` | function | The super admin user object. |
| `auth_headers` | function | `Authorization: Bearer <token>` header for the default test user. |
| `admin_auth_headers` | function | `Authorization: Bearer <token>` header for the default super admin. |
| `tenant_context` | function | Callable to set RLS tenant context on the current session; cleared at teardown. |

---

## Test Database Strategy

- Tests prefer a dedicated database configured via `TEST_DATABASE_URL`.
- If `TEST_DATABASE_URL` is not set, tests fall back to `DATABASE_URL` (the shared development database).
- When running against the development database, tests use unique identifiers and avoid destructive operations.
- No `DROP`, `TRUNCATE`, or reset of non-test data is performed.
- The `transactional_db` fixture is available for tests that need automatic rollback; the default `db` fixture does not auto-rollback because many routes and the seed function commit internally.

---

## RLS Helpers

- `rls_status(db, table_name)` — returns `{"rls_enabled": bool, "force_rls": bool}`.
- `assert_rls_enabled(db, table_name, force=True)` — asserts RLS is enabled and (by default) `FORCE ROW LEVEL SECURITY` is active.
- `count_rows(db, model, *filters)` — counts rows for a model with optional filters.

## Auth Helpers

- `create_test_user(db, organization=None, **kwargs)` — creates a verified tenant user by default; supports `is_superuser`, `is_active`, `is_verified`, `role`, custom `email`/`password`.
- `create_test_organization(db, name, slug)` — creates a tenant organization.
- `auth_headers_for(client, email, password)` — logs in and returns an `Authorization` header dict.

## Seed Helpers

- Seed tests call `app.seeds.seed_all_default_data` directly and assert on the returned summary.
- `test_seed_is_idempotent` runs the seed twice and verifies accounts/budget/category counts remain stable.
- `test_smoke.py::test_seed_script_is_idempotent` provides a quick standalone check.

---

## Baseline vs Final Test Count

| Metric | Before | After |
|--------|--------|-------|
| Total collected | 45 | 47 |
| Passed | 45 | 46 |
| Skipped | 0 | 1 (smoke login for dev user when `DEV_SUPERUSER_PASSWORD` is unset) |
| Warnings | 8 | 2 |

---

## Warnings Fixed / Remaining

### Fixed

- `PytestReturnNotNoneWarning` from `scripts/test_rls.py` (no longer collected by pytest; functions renamed to `check_*`).

### Remaining

- `PydanticDeprecatedSince20: Support for class-based config is deprecated` in `app/config.py` and `app/schemas/admin.py`.
- These are existing codebase warnings and are outside the scope of this card.

---

## Commands Run

```text
python -m compileall app                 ✅ passed
alembic current                          ✅ 542823443f9e (head)
alembic history                          ✅ 4 revisions, head is 542823443f9e
python scripts/inspect_db.py             ✅ 40 tables, 30 with RLS, FORCE RLS active
python scripts/seed_default_data.py --dev   ✅ idempotent
python scripts/seed_default_data.py --dev   ✅ idempotent
python -m pytest -q --tb=no              ✅ 46 passed, 1 skipped, 2 warnings
python -m pytest -v --tb=no              ✅ 46 passed, 1 skipped, 2 warnings
```

---

## Recommended Next Card

**IMP-700-CSV — Create Import Module with CSV Parser**

Rationale: The test foundation is now solid, auth works, RLS is enforced, and seed data is in place. CSV import is the highest-value user-facing feature for the Oman market and is the next logical step in the build sequence. The new fixtures and helpers will make it straightforward to write integration tests for uploaded imports and tenant-scoped transaction rows.
