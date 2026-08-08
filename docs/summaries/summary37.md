> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 44: AUTH-305 — Tenant Member Invitation Flow**.

# Summary 37 — Card 44: AUTH-305 Tenant Member Invitation Flow

## What Was Done

Implemented a real invitation/acceptance flow for family membership, replacing the previous "manual PATCH to activate" workaround as the only path. An authorized member (HEAD/PARENT) invites by email via `POST /family/members/invitations`; the invited person accepts through a token-gated, unauthenticated `POST /family/members/invitations/accept`, which creates their account inside the inviting tenant and activates their `FamilyMember` row by reusing `FamilyService.create_member()` unchanged, then logs them in.

## Key Changes

- New `FamilyInvitation` model/table (Alembic `f3a8c1d94b7e`), `pending → accepted | cancelled | expired` lifecycle, 7-day expiry, unique bearer token.
- `app/services/family_service.py`: added `create_invitation` (idempotent per pending email, rejects emails with existing accounts), `list_invitations`, `get_invitation`, `cancel_invitation`, lazy expiry-on-read.
- `app/services/auth_service.py`: added `create_user_in_organization()` (joins an *existing* tenant instead of creating a new one, unlike self-registration) and `accept_family_invitation()` (validates the token, creates the user, calls `FamilyService.create_member()` to activate membership).
- `app/routers/family.py`: added `POST/GET /family/members/invitations`, `POST .../{id}/cancel`, `POST .../accept`.
- **Key architectural decision:** `family_invitations` is deliberately **not** RLS-protected — this mirrors the codebase's own documented pattern for `email_verifications`/`password_resets` (`app/core/rls.py` `GLOBAL_TABLES`): an accept-by-token request has no tenant context yet, and RLS requires `app.current_tenant_id` to already be set, so RLS would make the row unreadable to the very request that needs it. Tenant isolation for the authenticated create/list/cancel operations is enforced at the service layer instead (same approach the `users` table already uses). `family_members`/`goals`/`journal_entries`/`journal_lines` RLS is unchanged.
- `set_tenant_context_async()` is called explicitly right before the `FamilyMember` insert during acceptance, since that table *is* RLS-protected.
- Reuses the existing pluggable `send_email()` backend (console-logged by default in dev/test) — no new or paid email service.
- Added `app/tests/integration/test_auth_invitations.py` with 18 tests: create/permissions, list/cancel/tenant isolation, acceptance/idempotency/expiry/cancellation, RLS, and read-only safety.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `f3a8c1d94b7e` (head, up from `a4c9e1f7b2d3`)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 47 tables (up from 46), `family_invitations` RLS-disabled as intended
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **726 passed, 1 skipped** (up from 708 passed, 1 skipped)

## Next Recommended Card

**ACC-502 — Opening Balances**
