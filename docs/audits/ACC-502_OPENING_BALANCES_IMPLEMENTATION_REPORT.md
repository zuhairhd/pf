# ACC-502 — Opening Balances Implementation Report

## Summary

Implemented opening balances by converting a configured `Account.opening_balance` into a real, idempotent, balanced journal entry through the existing `AccountingService` engine. A user can set `opening_balance` (and an optional `opening_balance_date`) when creating or updating an account; `POST /accounts/opening-balances/post` then posts one balanced journal entry per eligible account against an auto-resolved (or auto-created) tenant-scoped "Opening Balance" Equity account, reusing `create_journal_entry()` unchanged — no direct `JournalEntry`/`JournalLine` insert was written for this card.

**A stale premise was corrected during implementation.** The card brief (and `PLAN_V2_CARD_STATUS.md`'s prior "Evidence" column for ACC-502) stated that `Account.current_balance` already existed. It does not — direct model introspection (`hasattr(Account, "current_balance")` → `False`) confirmed only `Loan.current_balance` is real; several other modules (`app/routers/dashboard.py`, `app/services/ai_forecast.py`, `app/services/ai_orchestrator.py`, `app/services/health_score_service.py`) reference `Account.current_balance` as if it existed, which is pre-existing latent/dead code unrelated to this card (not touched here, since fixing it would be an unrelated broad change outside ACC-502's scope — flagged as a known issue below). This card instead adds a distinctly-named `opening_balance` field, which is the actual "configured starting balance a user enters," never a live/computed balance.

No goal, budget, bill, or invitation logic (GOAL-1401B, DB-1105B, AUTH-305) was touched. Alembic head moved from `f3a8c1d94b7e` to `b7d2e5a91c48`.

---

## Files Changed

**New:**
- `alembic/versions/b7d2e5a91c48_add_account_opening_balance_columns.py` — migration.
- `app/tests/integration/test_opening_balances.py` — 17 new tests.
- `docs/audits/ACC-502_OPENING_BALANCES_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/models/accounting.py` — added `opening_balance`, `opening_balance_date`, `opening_balance_journal_entry_id` to `Account`.
- `app/schemas/accounting.py` — extended `AccountCreate`/`AccountUpdate`/`AccountResponse`; added `OpeningBalanceAccountResult`, `OpeningBalanceStatusResponse`, `OpeningBalancePostResponse`.
- `app/services/accounting_service.py` — added `post_opening_balances()`, `get_opening_balance_status()`, and supporting private helpers; `create_account()` now persists the two new optional input fields.
- `app/routers/accounts.py` — added `_require_accounting_admin()`, `POST /accounts/opening-balances/post`, `GET /accounts/opening-balances/status`; `update_account()` now accepts `opening_balance`/`opening_balance_date` and rejects changing either once posted.

`GoalContribution`/`FamilyGoalService` (GOAL-1401B), the dashboard reversal route (DB-1105B), and `FamilyInvitation`/`FamilyService` (AUTH-305) were **not modified**.

---

## Database / Migration Changes

`accounts` gained three nullable columns:

| Column | Type | Notes |
|---|---|---|
| `opening_balance` | `Numeric(15,3)`, nullable | `NULL` = never configured (skipped); `0` = configured as zero (also skipped, nothing to post); any other value = the amount to post. |
| `opening_balance_date` | `Date`, nullable | Journal entry date; falls back to today if unset. |
| `opening_balance_journal_entry_id` | FK → `journal_entries.id`, nullable | Idempotency marker — set once posted. |

- **Revision ID:** `b7d2e5a91c48`
- **Down revision:** `f3a8c1d94b7e`

Additive only — no existing table, row, or posted journal entry is touched. RLS/FORCE RLS on `accounts` (already active) is untouched by adding columns.

---

## Routes Added

| Method | Route | Auth | Description |
|---|---|---|---|
| GET | `/accounts/opening-balances/status` | `require_tenant_member` + HEAD/PARENT | Read-only preview of what posting would do; never mutates anything. |
| POST | `/accounts/opening-balances/post` | `require_tenant_member` + HEAD/PARENT | Posts all eligible accounts' opening balances; idempotent. |

`POST /accounts/`, `PATCH /accounts/{id}` are unchanged in shape but now accept/return the two new opening-balance input fields (plus the read-only `opening_balance_journal_entry_id`). All other existing account/journal routes are untouched.

---

## Opening Balance Posting Rules

1. For each tenant account (optionally filtered to specific IDs), classify it:
   - `skipped_offset_account` — it *is* the resolved Opening Balance Equity account (never posted against itself).
   - `already_posted` — `opening_balance_journal_entry_id` is already set.
   - `skipped_no_balance` — `opening_balance` is `NULL`.
   - `skipped_zero` — `opening_balance == 0`.
   - `pending` — a real, unposted, non-zero amount.
2. If there is at least one `pending` account, the tenant's "Opening Balance" Equity account (code `3000`, matching the naming already used by the dev seed's `CHART_OF_ACCOUNTS`) is looked up, or created via the unchanged `create_account()` if absent.
3. Each pending account gets exactly one balanced journal entry (2 lines: the account itself, and the equity offset), created via the unchanged `create_journal_entry()`:
   - **Asset / Expense** (normal debit balance), positive amount → account **debited**, equity **credited**.
   - **Liability / Equity / Income** (normal credit balance), positive amount → account **credited**, equity **debited**.
   - A negative `opening_balance` flips the sides for either group, always keeping the pair balanced.
   - Reference: `OB-{tenant_id}-{account_id}` (deterministic, tenant-namespaced, matching the `GOAL-`/`ALLOW-`/`REV-` reference conventions already used elsewhere in this codebase).
   - Narration: `Opening balance: {account name}`.
4. `Account.opening_balance_journal_entry_id` is set immediately after each successful post.

---

## Idempotency Rules

- `post_opening_balances()` checks `opening_balance_journal_entry_id` **before** creating anything; an already-posted account is reported as `already_posted` and is never re-posted or duplicated.
- Verified: two consecutive calls against the same accounts produce exactly one `JournalEntry` per account (not two), and the second call's `accounts_posted` is `0`.
- `_get_or_create_opening_balance_equity_account()` itself is idempotent (look-up-before-create), so repeated runs never create a second "Opening Balance" equity account.
- Once posted, `PATCH /accounts/{id}` rejects further changes to `opening_balance`/`opening_balance_date` (`400`), so the stored configured value can never silently drift from what was actually posted — "do not rewrite historical balances" is enforced structurally, not just by convention.

---

## Access Control Rules

- Both routes require `require_tenant_member` **and** an elevated family role — `FamilyAccountAccessService.get_role()` must return `HEAD` or `PARENT` (a tenant `OWNER`/`ADMIN` with no family record already resolves to `HEAD` via that same service, unchanged). This is the exact same elevated-role gate FAM-1305 (allowance payment posting/reversal) and GOAL-1401B/DB-1105B (goal contribution reversal) already use — reused, not reinvented.
- `ADULT`/`TEEN`/`CHILD`/`VIEWER` are always rejected with `403`, verified by test (including confirming zero journal entries are created on a rejected attempt).
- No existing permission check was weakened; `create_account`'s existing (unchanged) `require_tenant_member`-only gate is untouched.

---

## RLS / Tenant Isolation Result

- Both new routes use `get_db_with_tenant_context`, identical to every other accounts route.
- `_opening_balance_candidate_accounts()` filters by `Account.tenant_id == self.tenant_id`; a request against Tenant B never returns or posts Tenant A's accounts — verified: Tenant B's own posting run reports `accounts_considered: 0` when only Tenant A has accounts, and Tenant A's account never appears in Tenant B's status results.
- `accounts`, `journal_entries`, `journal_lines` all retain their pre-existing RLS + FORCE RLS, unchanged and re-verified.
- No cross-tenant journal entry was created in any test scenario.

---

## Tests Run and Results

- `python -m compileall app` — OK
- `alembic current` — `b7d2e5a91c48` (head)
- `alembic history` — linear through `b7d2e5a91c48`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 47 tables unchanged, new columns present on `accounts`
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **743 passed, 1 skipped** (up from the AUTH-305 baseline of 726 passed, 1 skipped — 17 new tests, zero regressions)

`app/tests/integration/test_opening_balances.py` (17 tests) covers:
- **Posting:** a non-zero account gets a journal entry; the entry balances debits and credits; zero-balance and unconfigured accounts are skipped safely; repeated posting is idempotent (no duplicate entries); the status endpoint correctly transitions `pending → already_posted`.
- **Normal balance rules:** an Asset account's opening balance debits the account; a Liability account's opening balance credits the account; the auto-created equity offset account is correctly excluded from its own posting on a follow-up call.
- **Permissions:** both routes require auth; a VIEWER is rejected with `403` and creates zero journal entries.
- **Tenant isolation / RLS:** Tenant B's posting run never touches Tenant A's accounts; `accounts`/`journal_entries`/`journal_lines` RLS re-verified.
- **Read-only-adjacent safety:** the full status → post sequence leaves `Budget`, `Bill`, `Goal`, `GoalContribution`, and `FamilyInvitation` row counts completely unchanged.
- **Update guard:** `PATCH` rejects changing `opening_balance` after it has already been posted.

Regression: `test_dashboard_family_goals_reversal.py` (DB-1105B), `test_auth_invitations.py` (AUTH-305), `test_goal_contribution_reversal.py`, `test_family_goals.py`, `test_family_account_visibility.py`, `test_goal_contributions_accounting.py`, and `test_rls_child_tables.py` all pass (99 tests), alongside the complete project test suite.

---

## Known Limitations

- **No opening-balance entry UI.** This card is API-only.
- **No bulk "set for N accounts" convenience endpoint.** Each account's `opening_balance` is configured individually (at creation or via `PATCH`); `post_opening_balances()` itself already processes every eligible account in one call, so this only affects *configuring* values, not posting them.
- **Pre-existing, unrelated `Account.current_balance` references were left untouched.** `app/routers/dashboard.py`, `app/services/ai_forecast.py`, `app/services/ai_orchestrator.py`, and `app/services/health_score_service.py` all reference a `current_balance` attribute that does not exist on `Account` (confirmed via `hasattr()`). `dashboard.py` defensively uses `getattr(a, "current_balance", 0)` and silently degrades to `0`; `health_score_service.py`'s `select(func.coalesce(func.sum(Account.current_balance), ...))` would raise `AttributeError` if that code path is ever actually reached at runtime (it appears to be a dead/untested path, since the full 743-test suite passes cleanly). This is a pre-existing bug predating this card, out of ACC-502's scope to fix (would require auditing and likely refactoring several AI/health-score modules — a broad change explicitly out of scope per this card's "do not perform a broad refactor" constraint). Flagged here for visibility; a dedicated follow-up card should either compute these views from real account balances (`AccountingService.get_account_balance()`, already correct and tested) or add the missing attribute if a stored/cached balance is genuinely wanted.

---

## Recommended Next Card

**ACC-500 — Chart of Accounts (Hidden Foundation)**

`PLAN_V2_CARD_STATUS.md` lists `ACC-500` as **Partial**: a full, OMR-oriented default chart of accounts already exists (`app/seeds/default_data.py`'s `CHART_OF_ACCOUNTS`, including the exact "Opening Balance" Equity account this card just started reusing), but it is only ever applied to the single `--dev` seed tenant — a real, self-registered tenant starts with an empty chart of accounts. This was directly surfaced while building ACC-502: `post_opening_balances()` has to auto-create the Opening Balance Equity account on demand precisely because no default chart exists for a real tenant. Auto-provisioning the same, already-reviewed account list at registration time closes a real onboarding gap using code that already exists and is already trusted.
