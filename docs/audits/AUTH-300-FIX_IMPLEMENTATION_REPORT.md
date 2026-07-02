# AUTH-300-FIX — Complete Authentication Flow, Email Verification Stubs, and RBAC Guards

**Card ID:** AUTH-300-FIX  
**Project:** PF AI Personal Finance SaaS  
**Date:** 2026-07-02  
**Alembic Head:** `542823443f9e` (no new migration created for this card)  
**Status:** ✅ DONE

---

## Summary

This card completes the authentication gateway so that seeded tenants, users, and the development super-admin can register, log in, verify email, reset passwords, refresh tokens, and log out safely. All changes preserve PostgreSQL Row-Level Security (RLS) and FORCE RLS; no universal admin bypass was introduced.

Key outcomes:

- Working register / login / logout / refresh endpoints.
- 15-minute access tokens and 7-day refresh tokens.
- Dev-mode email verification and password reset (links logged, no SMTP required).
- Reusable RBAC and tenant-context dependencies in `app.core.security`.
- Admin routes now require `require_super_admin`.
- 15 route-level auth integration tests, all passing; full suite 45/45 passing.

---

## Files Changed

| File | Change |
|------|--------|
| `app/config.py` | Added `EMAIL_DEV_MODE=True`, `JWT_ACCESS_EXPIRATION_MINUTES=15`, `JWT_REFRESH_EXPIRATION_DAYS=7`. Kept deprecated `JWT_EXPIRATION_MINUTES` for compatibility. |
| `app/core/security.py` | New module with `get_current_user`, `require_active_user`, `require_verified_user`, `require_tenant_member`, `require_tenant_role`, `require_tenant_admin`, `require_tenant_owner`, `require_super_admin`, and `get_db_with_tenant_context`. |
| `app/services/auth_service.py` | Normalized email to lowercase; reject inactive users on login; 15-min / 7-day token expiry; unique `jti` claim on refresh tokens to avoid storage collisions; added `create_email_verification`, `send_verification_email`, `verify_email`, `create_password_reset`, `send_password_reset`, `reset_password`, `refresh_access_token`, `revoke_refresh_token`; seeded default notification settings on registration. |
| `app/schemas/auth.py` | Added `RefreshTokenRequest`, `PasswordResetRequest`, `PasswordResetConfirm`. |
| `app/routers/auth.py` | Implemented `POST /auth/register`, `POST /auth/login`, `GET /auth/verify-email/{token}`, `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/refresh`, `POST /auth/logout`. Dev-mode links are logged. |
| `app/routers/admin.py` | Replaced ad-hoc admin checks with `require_super_admin` dependency from `app.core.security`. |
| `app/tests/integration/test_auth.py` | New integration tests covering registration, duplicate email, login, wrong password, inactive user, JWT protection, invalid token, refresh token rotation, email verification, password reset, RBAC, tenant isolation, and RLS enforcement. |

---

## Auth Routes Fixed / Created

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/auth/register` | Create user + organization; send/log verification email. |
| POST | `/auth/login` | Authenticate; return 15-min access token + 7-day refresh token. |
| GET | `/auth/verify-email/{token}` | Mark email verified. |
| POST | `/auth/forgot-password` | Create reset token; always returns same message. |
| POST | `/auth/reset-password` | Reset password with valid token. |
| POST | `/auth/refresh` | Exchange refresh token for a new access/refresh pair (rotates). |
| POST | `/auth/logout` | Revoke supplied refresh token. |

All HTML page routes (`/register`, `/login`, `/reset-password/{token}`) remain available for server-rendered flows.

---

## Token Behavior

- **Access token:** JWT, `type=access`, 15-minute lifetime, payload includes `sub` (user id), `email`, `tenant_id` (`organization_id`), `role`.
- **Refresh token:** JWT, `type=refresh`, 7-day lifetime, stored in `refresh_tokens` with `expires_at` and `is_revoked`.
- **Token rotation:** `/auth/refresh` revokes the used refresh token and issues a new pair.
- **Collision fix:** Refresh tokens now include a unique `jti` claim (`secrets.token_urlsafe(16)`) so two tokens created for the same user in the same second no longer violate the unique constraint on `refresh_tokens.token`.
- **Logout:** `/auth/logout` revokes the supplied refresh token; access tokens naturally expire.

---

## Email Verification Behavior

- `AuthService.send_verification_email` creates a 24-hour `EmailVerification` token.
- When `EMAIL_DEV_MODE=True` (default in development), the verification URL is logged with the email masked by `mask_email()`; no SMTP is required.
- `GET /auth/verify-email/{token}` marks the token used and sets `users.is_email_verified=True` and `email_verified_at`.
- Expired or already-used tokens fail safely with `400 Invalid or expired verification token`.

---

## Password Reset Behavior

- `AuthService.send_password_reset` creates a 1-hour `PasswordReset` token.
- In dev mode the reset URL is logged with a masked email.
- The `/auth/forgot-password` endpoint always returns the same success message to prevent account enumeration.
- `POST /auth/reset-password` validates the token (not used, not expired), marks it used, and updates the hashed password.
- Used/expired tokens fail safely.

---

## RBAC Guards Added

All guards are FastAPI dependencies in `app.core.security`:

| Dependency | Requirement |
|------------|-------------|
| `get_current_user` | Valid Bearer JWT, user exists. |
| `require_active_user` | `is_active=True`. |
| `require_verified_user` | Email verified. |
| `require_tenant_member` | User has an `organization_id`. |
| `require_tenant_role({...})` | Factory; user role is in allowed set. |
| `require_tenant_admin` | `OWNER` or `ADMIN`. |
| `require_tenant_owner` | `OWNER`. |
| `require_super_admin` | `is_superuser=True`. |

`app.routers.admin` now injects `require_super_admin` on all admin/support-access endpoints.

---

## Tenant Context Behavior

- `TenantScopingMiddleware` extracts `tenant_id` from the JWT access token and executes `SET LOCAL app.current_tenant_id = '<tenant_id>'` for each request.
- `app.core.security.get_db_with_tenant_context` provides an optional dependency that sets RLS context explicitly from the token.
- Users cannot impersonate another tenant: the token carries their `organization_id`, and RLS policies block cross-tenant reads.
- Admin support access still uses `SET LOCAL` for one tenant at a time; no bypass is implemented.

---

## Test Results

### Auth integration tests

```text
python -m pytest app/tests/integration/test_auth.py -v
15 passed, 2 warnings in 8.95s
```

Tests cover:

1. `test_register_user`
2. `test_register_duplicate_email_rejected`
3. `test_login_success`
4. `test_login_wrong_password_rejected`
5. `test_login_inactive_user_rejected`
6. `test_jwt_protected_endpoint_works`
7. `test_invalid_token_rejected`
8. `test_refresh_token_works` (rotation + revocation)
9. `test_email_verification_token_creation_and_verification`
10. `test_password_reset_request_and_completion`
11. `test_expired_reset_token_rejected`
12. `test_normal_user_cannot_access_admin_route`
13. `test_super_admin_can_access_admin_route`
14. `test_user_cannot_impersonate_another_tenant`
15. `test_rls_active_during_authenticated_request`

### Full suite

```text
python -m pytest -q
45 passed, 8 warnings in 13.10s
```

### Verification commands

```text
python -m compileall app           ✅ passed
alembic current                    ✅ 542823443f9e (head)
alembic history                    ✅ 4 revisions, head is 542823443f9e
python scripts/inspect_db.py       ✅ 40 tables, 30 with RLS enabled, FORCE RLS active
python scripts/seed_default_data.py --dev   ✅ idempotent
```

---

## Security Warnings

- JWT secrets still default to `change-me-in-production` in `app/config.py`. **Production must set `JWT_SECRET` and `SECRET_KEY` via environment variables.**
- `EMAIL_DEV_MODE=True` by default. In production, set `EMAIL_DEV_MODE=False` and configure SMTP before enabling real user registration.
- bcrypt emits a benign `(trapped) error reading bcrypt version` warning because of a passlib/bcrypt version mismatch; password hashing and verification still work. Upgrading passlib or pinning bcrypt can silence this later.
- The register endpoint still auto-creates an organization for every user. A separate tenant-onboarding card should refine this for multi-member organizations.
- The `JWT_EXPIRATION_MINUTES` setting is deprecated; new code uses `JWT_ACCESS_EXPIRATION_MINUTES`.

---

## Deferred Items

- Full SMTP email delivery backend.
- HTML email templates for verification and password reset.
- Tenant member invitation flow (`AUTH-305`).
- Resource-level permission checks (e.g., "can this user edit this specific transaction?"). Current guards cover route-level roles only.
- Two-factor authentication (TOTP fields exist but are not enforced).
- Tenant onboarding during registration for existing organizations.

---

## Recommended Next Card

**PF-100-TEST — Formalize Test Infrastructure (Auth + Tenant Isolation)**

Rationale: AUTH-300-FIX added working auth tests, but the project still lacks a dedicated test database, a shared `conftest.py`, and reusable async fixtures. Formalizing the test pyramid now protects the RLS and auth work already completed before adding CSV/SMS import or LLM integration.

Alternatively, if test infrastructure is considered sufficient, the next card should be:

**IMP-700-CSV — Create Import Module with CSV Parser**

This is the highest-value user-facing feature for the Oman market and depends on the tenant/auth foundation now in place.
