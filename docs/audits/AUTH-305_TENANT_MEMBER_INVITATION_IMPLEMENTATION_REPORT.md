# AUTH-305 — Tenant Member Invitation Flow Implementation Report

## Summary

Implemented a real invitation/acceptance flow for family (tenant) membership, replacing the previous "manual `PATCH /family/members/{id}` with `is_active: true`" workaround as the only way to activate a member. An authorized family member (HEAD/PARENT, or an ADULT with `can_manage_members`) can invite a person by email via `POST /family/members/invitations`. The invited person accepts through a token-gated, unauthenticated `POST /family/members/invitations/accept`, which creates their `User` account inside the inviting tenant and activates their `FamilyMember` row by reusing the existing `FamilyService.create_member()` unchanged, then logs them in.

No reversal/goal logic from GOAL-1401B or DB-1105B was touched. No accounting engine, journal entries, accounts, budgets, bills, or goals are created or modified by any invitation action.

The new `family_invitations` table is deliberately **not** RLS-protected — this mirrors a pattern the codebase already documents and uses for `email_verifications`/`password_resets` (`app/core/rls.py`'s `GLOBAL_TABLES`), for the same underlying reason: an accept-by-token request has no tenant context yet, and RLS policies require `app.current_tenant_id` to already be set, so RLS would make the row unreadable to the very request that needs to look it up. Tenant isolation for the *authenticated* create/list/cancel operations is enforced at the service layer instead — the exact same approach the `users` table already uses for its own auth lookups.

Alembic head moved from `a4c9e1f7b2d3` to `f3a8c1d94b7e`.

---

## Files Changed

**New:**
- `alembic/versions/f3a8c1d94b7e_add_family_invitations_table.py` — migration.
- `app/tests/integration/test_auth_invitations.py` — 18 new tests.
- `docs/audits/AUTH-305_TENANT_MEMBER_INVITATION_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/models/family.py` — added `FamilyInvitationStatus` enum and `FamilyInvitation` model.
- `app/models/__init__.py` — exported `FamilyInvitation`, `FamilyInvitationStatus`.
- `app/core/rls.py` — added `family_invitations` to `GLOBAL_TABLES` with an explanatory comment (documentation only; no functional change).
- `app/schemas/family.py` — added `FamilyInvitationCreate`, `FamilyInvitationResponse`, `FamilyInvitationAcceptRequest`.
- `app/services/family_service.py` — added `list_invitations`, `get_invitation`, `create_invitation`, `cancel_invitation`, `_mark_expired_if_needed`, `_send_invitation_email`, and the `INVITATION_EXPIRY_DAYS` constant.
- `app/services/auth_service.py` — added `create_user_in_organization()` and `accept_family_invitation()`.
- `app/routers/family.py` — added `_to_invitation_response()`, `_invitation_error_status()`, and four routes.

`FamilyService.create_member()`, `AccountingService`, and every GOAL-1401B/DB-1105B reversal method were **not modified** — all reused exactly as-is.

---

## Model / Schema Changes

New `family_invitations` table:

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | FK → `organizations.id`, not null | Application-level tenant filter (no RLS — see rationale above). |
| `family_id` | FK → `families.id`, not null | |
| `email`, `first_name`, `last_name`, `relationship_type`, `role` | as on `FamilyMember` | Copied onto the resulting `FamilyMember` at acceptance. |
| `token` | `String(255)`, unique, not null | Raw bearer token (stored in plaintext, matching the existing `EmailVerification.token`/`PasswordReset.token` precedent — not hashed). |
| `status` | `String(20)`, not null | `pending` / `accepted` / `cancelled` / `expired`. |
| `expires_at` | `DateTime`, not null | `created_at + 7 days`. |
| `accepted_at`, `cancelled_at` | `DateTime`, nullable | |
| `invited_by_user_id` | FK → `users.id`, not null | |
| `member_id` | FK → `family_members.id`, nullable | Set once accepted. |

`GoalContributionReversalRequest`/`GoalContributionResponse` and all GOAL-1401B/DB-1105B schemas are unchanged.

---

## Alembic Revision

- **Revision ID:** `f3a8c1d94b7e`
- **Down revision:** `a4c9e1f7b2d3`

Creates only the new `family_invitations` table, its indexes, and foreign keys — no existing table is altered, dropped, or recreated. No RLS policies are created for this table (intentional; see Summary). Verified via `python scripts/inspect_db.py`: 47 tables total (up from 46), `family_invitations` correctly reported with RLS disabled.

---

## Routes Added

| Method | Route | Auth | Description |
|---|---|---|---|
| POST | `/family/members/invitations` | `require_tenant_member` + `can_manage_members` | Create (or idempotently reuse) a pending invitation. |
| GET | `/family/members/invitations` | `require_tenant_member` | List the tenant family's invitations. |
| POST | `/family/members/invitations/{invitation_id}/cancel` | `require_tenant_member` + `can_manage_members` | Cancel a pending invitation. |
| POST | `/family/members/invitations/accept` | **None** (public, token-gated) | Create the invited user's account, activate their membership, and log them in. |

The accept route intentionally uses `get_db` (no tenant context dependency) instead of `get_db_with_tenant_context`, mirroring `/auth/register`, `/auth/verify-email/{token}`, and `/auth/reset-password` — all of which are also unauthenticated, token/email-driven routes with no prior tenant context. Route-shape analysis (verified via `app.openapi()`) confirmed no path collisions with the existing `/family/members`, `/family/members/{member_id}` routes.

The existing `create_member`/`list_members`/`update_member`/`delete_member` routes and their direct-PATCH activation path are **completely unchanged** — this card is purely additive.

---

## Invitation Lifecycle Rules

- **pending** — created by `create_invitation()`; the default state.
- **accepted** — set by `accept_family_invitation()`; `member_id` and `accepted_at` are populated; cannot be reversed or reused.
- **cancelled** — set by `cancel_invitation()`; can only be applied to a `pending` invitation; cannot later be accepted.
- **expired** — lazily computed: any read of a `pending` invitation whose `expires_at` has passed (`list_invitations`, `get_invitation`, `create_invitation`'s duplicate check, and `accept_family_invitation` itself) flips it to `expired` and persists that change before continuing. There is no background job — expiry is detected on next access, matching the project's existing "no new background jobs unless already required" constraint.
- **Idempotent creation:** calling `create_invitation()` again for an email with an existing `pending`, non-expired invitation returns that same invitation (same `id`, same `token`) instead of creating a duplicate row or issuing a new token.
- **Reuse rejection:** `accept_family_invitation()` explicitly checks `status != "pending"` and raises a clear, distinct error message per terminal state (`"...is accepted and cannot be accepted"`, `"...is cancelled..."`, `"...is expired..."`).

---

## Access Control Rules

- **Create / list / cancel** are gated by the existing `FamilyService.require_permission("can_manage_members")` — unchanged permission matrix (HEAD/PARENT always allowed; ADULT allowed per the existing family permission rules; TEEN/CHILD/VIEWER always denied). No new permission concept was introduced.
- **Accept** has no family-permission check by design — the bearer token itself is the authorization proof, exactly like accepting an email-verification or password-reset link. The resulting tenant is derived entirely from the invitation record (`invitation.tenant_id`), never from anything the caller supplies, so there is no parameter an attacker could manipulate to redirect an invitation to a different tenant.
- **Existing-account protection:** an email that already has a `User` account (in *any* tenant — this app is single-tenant-per-user, `User.email` is globally unique) is rejected both proactively at `create_invitation()` time and defensively at `accept_family_invitation()` time (covering the race where an account appears after the invitation was created). Cross-tenant account *linking* is explicitly out of scope: this app's architecture binds one `User` to exactly one `organization_id`, so silently re-pointing an existing user's tenant would sever their access to their original tenant's data — an unsafe operation this card correctly refuses rather than attempts.

---

## RLS / Tenant Isolation Result

- `family_invitations` has **no RLS** (by design — see Summary). Verified directly: `rls_status(db, "family_invitations")["rls_enabled"] is False`.
- `family_members`, `goals`, `journal_entries`, `journal_lines` all retain their pre-existing RLS + FORCE RLS, unchanged and re-verified.
- **Cross-tenant listing:** `list_invitations()`/`get_invitation()` filter by `FamilyInvitation.tenant_id == self.tenant_id` at the query level; Tenant B's `GET /family/members/invitations` never includes Tenant A's invitations — verified.
- **Cross-tenant cancel:** `get_invitation()`'s tenant filter means a foreign invitation ID resolves to `None` → `404` — verified.
- **Cross-tenant acceptance:** structurally impossible to redirect (see Access Control Rules); the closest real analogue — an email that already has an account in a *different* tenant — is explicitly rejected, verified by test.
- `set_tenant_context_async(db, invitation.tenant_id)` is called explicitly inside `accept_family_invitation()` immediately before creating the `FamilyMember` row (which *is* RLS-protected), so that INSERT satisfies the existing `WITH CHECK (tenant_id = current_setting(...))` policy correctly — this is the same tenant-context mechanism `get_db_with_tenant_context` already applies for every authenticated request, just invoked programmatically here since the accept route runs before any tenant is known from a JWT. This is not an RLS bypass; it is the correct, intended way to satisfy RLS once a legitimate tenant has been established from the token.

---

## Tests Run and Results

- `python -m compileall app` — OK
- `alembic current` — `f3a8c1d94b7e` (head)
- `alembic history` — linear through `f3a8c1d94b7e`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 47 tables (up from 46), `family_invitations` present with RLS disabled as intended
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **726 passed, 1 skipped** (up from the DB-1105B baseline of 708 passed, 1 skipped — 18 new tests, zero regressions)

`app/tests/integration/test_auth_invitations.py` (18 tests) covers:
- **Create/permissions:** requires auth; HEAD can create; VIEWER cannot (`403`); duplicate pending invitation is idempotent; an email with an existing account is rejected at create time.
- **List/cancel/isolation:** Tenant B's list never contains Tenant A's invitation; Tenant B cannot cancel Tenant A's invitation (`404`); a pending invitation can be cancelled.
- **Acceptance:** creates and activates the `FamilyMember` (correct role, `is_active=True`, linked `user_id`) and returns a valid `TokenResponse`; an accepted invitation cannot be accepted twice; a cancelled invitation cannot be accepted; an expired invitation cannot be accepted; an invalid/garbage token is rejected safely; an email that gains an account after invitation creation is rejected at accept time; the resulting account always joins the inviting tenant.
- **RLS:** `family_members`/`goals`/`journal_entries`/`journal_lines` remain RLS-protected; `family_invitations` is confirmed intentionally RLS-exempt.
- **Read-only safety:** the full create → list → accept sequence leaves `JournalEntry`, `Account`, `Budget`, `Bill`, `Goal`, and `GoalContribution` row counts for the tenant completely unchanged.

Regression: `test_auth.py`, `test_family_goals.py`, `test_dashboard_widget.py` (including the DB-1105A/DB-1105B family-goals-widget tests), `test_dashboard_family_goals_reversal.py`, and `test_goal_contribution_reversal.py` all pass (92 tests), alongside the complete project test suite.

---

## Known Limitations

- **No resend-invitation endpoint.** Cancelling and re-inviting achieves the same result (a fresh token/expiry) since creation is idempotent per-pending-invitation but a cancelled one is no longer "pending," so a follow-up `create_invitation()` call issues a genuinely new invitation.
- **No invitation-management UI/template.** This card is API-only, matching the pattern where several prior `-A` cards (e.g. GOAL-1401A) shipped API-first with a UI/dashboard follow-up in a later `-B` card.
- **Tokens are stored in plaintext**, matching the existing `EmailVerification.token`/`PasswordReset.token` precedent in this codebase (not a new weaker choice — consistent with how the project already handles this class of token).
- **No account "upgrade" path for an email that already exists elsewhere.** By design (see Access Control Rules) — considered a safe, deliberate limitation rather than an oversight, given this app's single-tenant-per-user architecture.

---

## Recommended Next Card

**ACC-502 — Opening Balances**

`PLAN_V2_CARD_STATUS.md` lists `ACC-502` as **Partial**: `Account.current_balance` exists as a field, but there is no opening-balance entry flow and no journal-entry auto-generation for it — a newly created account's starting balance is not currently reflected in the ledger. This is a well-scoped, low-risk gap that directly reuses the `AccountingService` journal-entry engine this session has already exercised repeatedly (GOAL-1401A/B, BILL-801A, FAM-1305, ACC-503A).
