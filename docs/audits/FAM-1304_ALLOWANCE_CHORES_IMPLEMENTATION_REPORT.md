# FAM-1304 — Allowance and Chore Tracking Implementation Report

## Summary

Implemented family chore assignment and allowance tracking: heads/parents define chores (optionally assigned to a specific family member with an allowance amount, frequency, and due date), assigned members submit completions, and heads/parents approve or reject those completions. Approved completions record an `earned_amount`; a read-only allowance summary aggregates pending/approved/rejected totals, scoped by role. No payments, transactions, journal entries, or account-balance changes are created anywhere in this card — allowance amounts are tracked as plain numeric fields only, exactly as scoped.

Two new tenant-scoped tables (`family_chores`, `family_chore_completions`) were added with RLS + FORCE RLS from creation. Alembic head advanced to `356391296d35`.

---

## Files Changed

**New:**
- `app/models/family_chore.py` — `FamilyChore`, `FamilyChoreCompletion` models; `ChoreFrequency`, `ChoreStatus`, `ChoreCompletionStatus` enums.
- `alembic/versions/356391296d35_add_family_chore_and_completion_tables.py` — migration.
- `app/schemas/family_chore.py` — `ChoreCreate`, `ChoreUpdate`, `ChoreResponse`, `ChoreCompletionCreate`, `ChoreCompletionResponse`, `ChoreApprovalRequest`, `AllowanceMemberBreakdown`, `AllowanceSummaryResponse`.
- `app/services/family_chore_service.py` — `FamilyChoreService`, `FamilyChoreServiceError`.
- `app/tests/integration/test_family_chores.py` — 29 new tests.
- `docs/audits/FAM-1304_ALLOWANCE_CHORES_IMPLEMENTATION_REPORT.md` — this report.

**Modified:**
- `app/models/__init__.py` — export the new models/enums.
- `app/routers/family.py` — added the `/family/chores`, `/family/chore-completions`, and `/family/allowance-summary` route group.

No existing models, schemas, services, or routes were changed. No dashboard template was touched (per scope: "do not build a full dashboard widget unless trivial").

---

## Model/Schema Changes

**Alembic revision:** `356391296d35` (down_revision `07c75f53dbf6`)

Two brand-new tables, both `TenantMixin` + `TimestampMixin` (tenant-scoped, `created_at`/`updated_at`):

**`family_chores`**
`id`, `tenant_id`, `family_id` (FK families), `title`, `description`, `assigned_to_member_id` (nullable FK family_members), `created_by_user_id` (nullable FK users), `allowance_amount`, `currency` (default `OMR`), `frequency` (`one_time`/`daily`/`weekly`/`monthly`), `due_date` (nullable), `status` (`active`/`paused`/`completed`/`cancelled`/`archived`), `requires_approval`.

Indexes: `tenant_id`, `family_id`, `assigned_to_member_id`, `status`, plus composite `(tenant_id, status)`, `(tenant_id, assigned_to_member_id)`, `(tenant_id, due_date)`.

**`family_chore_completions`**
`id`, `tenant_id`, `chore_id` (FK family_chores), `family_id` (FK families), `completed_by_member_id` (FK family_members), `completed_at`, `submitted_notes` (nullable), `status` (`submitted`/`approved`/`rejected`), `approved_by_user_id` (nullable FK users), `approved_at` (nullable), `rejection_reason` (nullable), `earned_amount`.

Indexes: `tenant_id`, `chore_id`, `family_id`, `completed_by_member_id`, `status`, plus composite `(tenant_id, status)`, `(tenant_id, completed_by_member_id)`.

Both tables are brand new — no existing data was touched, and no unrelated financial table was modified.

---

## Chore Workflow

1. A HEAD or PARENT calls `POST /family/chores` with a title, optional description, optional `assigned_to_member_id`, `allowance_amount`, `frequency`, optional `due_date`, and `requires_approval` flag. The chore starts in `active` status.
2. Any visible chore can be listed (`GET /family/chores`, filtered by role — see "Role Permission Matrix") or fetched individually (`GET /family/chores/{id}`).
3. HEAD/PARENT can `PATCH /family/chores/{id}` to reassign, retitle, reprice, or change status, and `POST /family/chores/{id}/archive` to archive it.
4. Reassigning a chore validates that the new `assigned_to_member_id` belongs to the same family (cross-family/cross-tenant member IDs are rejected).

---

## Completion / Approval Workflow

1. The member the chore is assigned to calls `POST /family/chores/{chore_id}/completions` with optional `submitted_notes` and an optional `completed_at` (defaults to now). This creates a `FamilyChoreCompletion` in `submitted` status with `earned_amount = 0`.
2. A HEAD or PARENT calls `POST /family/chore-completions/{completion_id}/approve` (optionally overriding `earned_amount`; defaults to the chore's `allowance_amount`) — the completion moves to `approved`, `approved_by_user_id`/`approved_at` are stamped, and `earned_amount` is set.
3. A HEAD or PARENT calls `POST /family/chore-completions/{completion_id}/reject` with a required `rejection_reason` — the completion moves to `rejected`, `earned_amount` stays `0`, and the reason is stored. Rejecting without a reason returns 400.
4. `GET /family/chores/{chore_id}/completions` lists all completions for a chore the caller can view.

No completion, approval, or rejection ever creates a `JournalEntry`, `JournalLine`, `Transaction`, or modifies an `Account` balance — verified by dedicated tests.

---

## Allowance Summary Behavior

`GET /family/allowance-summary` calls `FamilyChoreService.get_allowance_summary()`, which computes (fresh, never persisted):
- `pending_approval_amount` — sum of the linked chore's `allowance_amount` for every `submitted` completion in scope.
- `approved_earned_amount` — sum of `earned_amount` for every `approved` completion in scope.
- `rejected_amount` — sum of the linked chore's `allowance_amount` for every `rejected` completion in scope (what was *forfeited*, for visibility).
- `by_member` — the same three figures broken down per family member.

**Scope by role:**
- HEAD/PARENT: all completions across the whole family.
- Everyone else (ADULT/TEEN/CHILD/VIEWER): only completions where `completed_by_member_id` equals their own `FamilyMember.id`. A user with no active `FamilyMember` record (e.g., a tenant admin who never joined the family) gets an all-zero summary rather than an error.

"By period" breakdown (mentioned as optional in the card) was not added — `completed_at`/`approved_at` timestamps are already stored on every completion, so a period filter can be layered on later without a schema change.

---

## Role Permission Matrix

| Role | View chores | Create/manage chores | Submit completion | Approve/reject | Allowance summary scope |
|---|---|---|---|---|---|
| **head** | All | ✅ | Own assigned chores | ✅ | All members |
| **parent** | All | ✅ | Own assigned chores | ✅ | All members |
| **adult** | All (broad, like shared/family budgets) | ❌ (no elevated-permission flag exists yet — see below) | Own assigned chores only | ❌ | Own completions only |
| **teen** | Own assigned chores only | ❌ | Own assigned chores only | ❌ | Own completions only |
| **child** | Own assigned chores only | ❌ | Own assigned chores only | ❌ | Own completions only |
| **viewer** | All (read-only) | ❌ | ❌ | ❌ | Own completions only (always empty, since viewers can't submit) |

**On ADULT create/approve rights:** the card spec explicitly hedges these as *"only if current family permissions allow; otherwise no"* / *"approve only if elevated permission exists; otherwise no"*. No such elevated-permission flag exists for chores today (the closest analog, `_permissions_for_role()` in `family_service.py`, doesn't cover chores), so both default to **no** for ADULT. This is intentionally conservative and documented here so a future card can add a flag if product requirements call for it, without needing to revisit this service's structure.

**Unassigned members can never submit another member's chore** — `can_user_submit_completion()` strictly requires `chore.assigned_to_member_id == caller's own FamilyMember.id`; there is no "any adult can complete any chore" shortcut.

---

## RLS / Tenant Safety

- Both new tables have RLS **and** FORCE RLS enabled directly in the creation migration — verified post-migration: `family_chores` → `(True, True)`, `family_chore_completions` → `(True, True)`.
- Every service query filters explicitly by `tenant_id` in addition to RLS (defense in depth, matching every other service in this codebase).
- `test_tenant_a_cannot_see_tenant_b_chores` confirms Tenant B's list/detail never surface Tenant A's chore (detail returns 404).
- `test_tenant_a_cannot_approve_tenant_b_completion` confirms a cross-tenant completion ID cannot be approved (404, not merely 403 — the completion is invisible, not just protected).
- `test_rls_active_on_chore_tables` re-confirms RLS + FORCE RLS on both new tables via `assert_rls_enabled`.

---

## Read-Only Financial Safety

- `FamilyChoreService` never imports or calls `AccountingService`, never constructs a `JournalEntry`/`JournalLine`, and never touches `Account.current_balance` (there is no such mutable field touched anywhere in this module).
- `test_chore_workflow_creates_no_financial_records` — creating a chore and reading it back leaves `Account`, `Goal`, and `JournalEntry` row counts unchanged.
- `test_completion_approval_creates_no_financial_records` — approving a completion (which sets `earned_amount`) leaves `Account` and `JournalEntry` row counts unchanged.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `356391296d35` (new head)
- `alembic history` — chains cleanly from `07c75f53dbf6`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables (was 44), RLS active on 37 (was 35); `family_chores`/`family_chore_completions` confirmed
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **499 passed, 1 skipped** (up from the DB-1106A baseline of 470 passed, 1 skipped — 29 new tests, zero regressions)

`app/tests/integration/test_family_chores.py` covers:
- Chores: auth required; head/parent create; teen/child/viewer/adult all rejected (403); list filtered by assigned member for teen vs. full visibility for head; unauthorized detail access rejected (403); update/archive permission-gated.
- Completions: assigned teen/child can submit; an unassigned member cannot submit another member's chore (403); viewer cannot submit (403); head/parent can approve (earned_amount defaults to allowance_amount, approver stamped); teen cannot approve their own completion (403); reject requires and stores a reason (400 without one).
- Allowance summary: approved-amount and pending-amount totals calculated correctly; child/teen see only their own summary and `by_member` entry; head/parent see every member's breakdown.
- Tenant/RLS: cross-tenant chore visibility and cross-tenant completion approval both blocked (404); RLS + FORCE RLS confirmed on both new tables.
- Read-only safety: full chore-and-approval workflow leaves Account/Goal/JournalEntry counts unchanged.

Regression: `test_family.py`, `test_family_goals.py`, `test_family_budgets.py`, `test_family_account_visibility.py`, `test_dashboard_widget.py`, `test_dashboard_ai.py`, and `test_dashboard_family_budgets.py` all still pass in full.

---

## Known Limitations

- **No accounting posting.** Approved allowance amounts are tracked numerically only; nothing is ever transferred, and no journal entry is created. Documented follow-up: **FAM-1305 — Allowance Payment Posting Through Accounting Engine** (per this card's explicit scope instruction — note this label is a task-assigned follow-up name, distinct from the "Family Dashboard" card that PLAN_V2.md separately lists under the FAM-1305 ID).
- **No dashboard widget.** `FamilyChoreService.get_family_chore_summary()` was added specifically to power a future widget (due-soon count, overdue count, pending-approvals count, approved-allowance-this-scope amount) but nothing was wired into `dashboard/index.html` in this card, per the explicit "do not build a full dashboard widget unless trivial" instruction. Documented follow-up: **DB-1107A — Allowance and Chore Dashboard Widget UI**.
- **No recurring-chore auto-regeneration.** `frequency` (`daily`/`weekly`/`monthly`) is stored but purely descriptive today — there is no scheduler that automatically creates a fresh chore/completion cycle when a recurring chore's period elapses. A head/parent currently manages recurrence manually (e.g., by resubmitting/re-approving).
- **ADULT role has no create/approve path yet.** As documented in the permission matrix, this is intentional per the card's own conditional wording, not an oversight — a future card can introduce a per-family "adult can manage chores" flag if needed.

---

## Recommended Next Card

**DB-1107A — Allowance and Chore Dashboard Widget UI**

`FamilyChoreService.get_family_chore_summary()` already exists specifically for this purpose. Surfacing it on the AI-centric dashboard alongside the existing commitments, family-goals, and family-budgets widgets is the lowest-risk, most immediately valuable next step, following the exact same "service now → widget next" rhythm already used for FAM-1303 → DB-1106A.
