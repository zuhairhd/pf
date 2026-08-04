# GOAL-1401B — Goal Contribution Reversal Implementation Report

## Summary

Implemented safe reversal for family goal contributions that were posted through the accounting engine (GOAL-1401A). When a contribution has a `journal_entry_id`, the user can now reverse it via `POST /family/goals/{goal_id}/contributions/{contribution_id}/reverse`, which creates a balanced reversing journal entry through the exact same `AccountingService.reverse_journal_entry()` engine already proven by ACC-503A (bill/subscription reversal) and FAM-1305 (allowance payment reversal) — no reversal logic was rebuilt. The original journal entry and its lines are never deleted or mutated; only reversal metadata is recorded, and the reversal is fully idempotent.

Progress-only contributions (never posted to accounting) cannot be reversed — there is nothing to undo. Reversing a posted contribution decrements the goal's `current_amount` by the contribution's amount (reverting `status` from `completed` back to `active` if it drops back below target), so a reversed contribution no longer counts toward active progress while the original row remains for audit.

No dashboard changes were made in this card — the Family Goals dashboard widget has no per-contribution history list to attach a reversal action to, and adding one was explicitly out of scope for a service/API card. Follow-up: **DB-1105B — Family Goal Contribution Reversal Dashboard Action**.

---

## Files Changed

**New:**
- `alembic/versions/a4c9e1f7b2d3_add_goal_contribution_reversal_columns.py` — migration.
- `app/tests/integration/test_goal_contribution_reversal.py` — 16 new tests.
- `docs/audits/GOAL-1401B_CONTRIBUTION_REVERSAL_IMPLEMENTATION_REPORT.md` (this file).

**Modified:**
- `app/models/goal.py` — added `reversal_journal_entry_id`, `reversed_at`, `reversed_by_user_id`, `reversal_reason` columns and relationships to `GoalContribution`.
- `app/schemas/goal.py` — extended `GoalContributionResponse` with the four new fields; added `GoalContributionReversalRequest`.
- `app/services/family_goal_service.py` — added `FamilyGoalService.reverse_contribution()`.
- `app/routers/family.py` — added `POST /family/goals/{goal_id}/contributions/{contribution_id}/reverse`; `_to_contribution_response()` now includes the new fields.

`app/services/accounting_service.py` (`reverse_journal_entry`) and `app/services/family_account_access_service.py` were **not modified** — both are reused exactly as-is.

---

## Model / Schema Changes

`GoalContribution` gained:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `reversal_journal_entry_id` | FK → `journal_entries.id` | Yes | Set once reversed. |
| `reversed_at` | `DateTime` | Yes | |
| `reversed_by_user_id` | FK → `users.id` | Yes | |
| `reversal_reason` | `Text` | Yes | Optional free-text reason supplied by the caller. |

`posting_status` (already a plain `String(20)`, no DB-level enum/CHECK constraint — same as GOAL-1401A and FAM-1305's `payment_status`) gains a new application-level value: `"reversed"`.

`GoalContributionResponse` now surfaces all four new fields. A new `GoalContributionReversalRequest` (`reversal_date: Optional[date]`, `reason: Optional[str]`, max 500 chars) is the request body for the reversal route.

---

## Alembic Revision

- **Revision ID:** `a4c9e1f7b2d3`
- **Down revision:** `bd89e4fcf4b9`
- **Name:** `add goal contribution reversal columns`

The migration adds only nullable columns, two indexes, and two foreign keys to the existing `goal_contributions` table. No table is dropped or recreated; existing rows are preserved and default to unreversed. RLS + FORCE RLS on `goal_contributions` (already active since GOAL-1401A) is untouched by adding columns.

The migration was hand-written rather than using the raw `alembic revision --autogenerate` output: autogenerate additionally proposed dropping and recreating unrelated foreign keys on `bills`, `subscriptions`, `family_chore_completions`, `family_members`, `journal_entries`, and several other tables — pre-existing comparator noise from FK `ondelete`-clause naming differences that predates this card (confirmed by reproducing the same noise with no model changes at all). Only the four new `goal_contributions` columns/indexes/FKs were kept, matching the same minimal, hand-written style used by the GOAL-1401A and FAM-1305 migrations.

---

## Reversal Behavior

`FamilyGoalService.reverse_contribution(goal_id, contribution_id, reason=None, reversal_date=None)`:

1. Loads the contribution via the existing tenant-scoped `get_contribution()` (which itself loads the goal via `get_goal()`, enforcing tenant scoping and view permission).
2. Calls `require_manage(goal)` — see **Permission Behavior** below.
3. Rejects contributions with no `journal_entry_id` (`"This contribution was never posted to accounting and cannot be reversed"`, mapped to `400`).
4. If `reversal_journal_entry_id` is already set, returns the contribution unchanged (idempotent — see below).
5. Calls `AccountingService.reverse_journal_entry(contribution.journal_entry_id, reversal_date=reversal_date, reason=reason or "Goal contribution reversed: {goal name}", created_by=user.id)` — unchanged from ACC-503A/FAM-1305. This creates a new balanced journal entry with debits/credits swapped relative to the original, tags the original with `reversal_entry_id`/`reversed_at`/`reversal_reason`, and never deletes or edits the original's lines.
6. Stores `reversal_journal_entry_id`, sets `posting_status = "reversed"`, `reversed_at = utcnow()`, `reversed_by_user_id = user.id`, `reversal_reason = reason`.
7. Decrements `goal.current_amount` by the contribution's amount (floored at zero) and reverts `goal.status` from `completed` to `active` if the goal is no longer at/above target.

---

## Progress Calculation Behavior

`Goal.current_amount` is a running total incremented directly at contribution-creation time (not re-derived by summing `goal_contributions` on each read — confirmed by inspecting `add_contribution()` and `get_progress()`). Because of this, reversal must explicitly decrement it:

- **Reversed posted contribution:** `current_amount` is decremented by the contribution's amount at reversal time, so it no longer counts toward `GET /family/goals/{goal_id}/progress`. Verified by `test_reversed_contribution_no_longer_counts_toward_progress`.
- **Progress-only contribution (never posted):** unaffected by this card — it continues to count toward progress exactly as before, since it was never posted and cannot be reversed. Verified by `test_progress_only_contribution_still_counts_if_not_reversed`.
- **Progress-only contribution reversal attempt:** rejected with a safe `400` (`"...cannot be reversed"`), since a progress-only contribution never had a journal entry to reverse. Verified by `test_cannot_reverse_progress_only_contribution`.
- The original `GoalContribution` row is never deleted; it remains queryable via `GET /family/goals/{goal_id}/contributions` with `posting_status = "reversed"` for audit purposes.

---

## API Routes

### Added

- `POST /family/goals/{goal_id}/contributions/{contribution_id}/reverse`
  Request: `{"reversal_date": "YYYY-MM-DD" (optional), "reason": "..." (optional, max 500 chars)}`
  Response: `GoalContributionResponse`, including `posting_status`, `journal_entry_id` (original, unchanged), `reversal_journal_entry_id`, `reversed_at`, `reversed_by_user_id`, `reversal_reason`.

All other goal/contribution routes (`create`, `list`, `get`, `post-to-accounting`) are unchanged.

---

## Idempotency Behavior

- `reverse_contribution()` checks `contribution.reversal_journal_entry_id` first; if already set, the contribution is returned unchanged and **no new journal entry is created** — matching the exact pattern used by `ImportService.confirm_job`, `FamilyChoreService.reverse_payment`, and `BillSubscriptionService`'s reversal paths.
- As a secondary safety net, `AccountingService.reverse_journal_entry()` itself is also idempotent (`_get_existing_reversal`), so even a concurrent/racing call cannot create two reversal entries for the same original.
- Verified by `test_repeated_reversal_does_not_duplicate_journal_entries` (exactly one `JournalEntry` with `reversed_entry_id` pointing at the original after two reversal calls) and `test_already_reversed_contribution_returns_existing_state` (repeated API calls return `200` with the same `reversal_journal_entry_id`, not an error).

---

## Permission Behavior

Reversal uses `require_manage(goal)` rather than the more permissive `require_contribute(goal)` used by `add_contribution()`:

- **HEAD / PARENT** (or tenant OWNER/ADMIN without a `FamilyMember` row, which already resolve to HEAD) can always reverse.
- **ADULT** can reverse contributions on shared/family goals, or on their own private goal — but not another adult's private goal.
- **TEEN / CHILD / VIEWER** can never reverse (even though TEEN/CHILD may be allowed to *contribute* to some goals under `can_contribute_to_goal`).

This intentionally mirrors the FAM-1305 precedent (allowance payment posting/reversal is gated more tightly than submitting a chore completion) — undoing a financial posting is a stronger action than making one, so it uses the stricter of the two existing permission checks rather than a new one.

Verified by `test_parent_can_reverse_contribution`, `test_viewer_cannot_reverse_contribution`, `test_adult_cannot_reverse_others_private_goal_contribution`.

---

## RLS / Tenant Safety

- The reversal route requires `require_tenant_member` and uses `get_db_with_tenant_context`, identical to every other family goal route.
- `get_contribution()`/`get_goal()` are tenant-scoped queries; a contribution or goal ID from another tenant resolves to "not found" (`404`), never a silent cross-tenant operation.
- `AccountingService.reverse_journal_entry()` loads the original journal entry scoped to `self.tenant_id`, so a cross-tenant journal entry ID is also unreachable.
- `goals`, `goal_contributions`, `journal_entries`, and `journal_lines` all retain RLS + FORCE RLS — verified by `test_rls_active_on_goal_and_journal_tables`.
- Verified by `test_tenant_a_cannot_reverse_tenant_b_contribution` (`404`).

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `a4c9e1f7b2d3` (head)
- `alembic history` — linear through `a4c9e1f7b2d3`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged, new columns present on `goal_contributions`
- `python scripts/seed_default_data.py --dev` — OK (idempotent)
- `python -m pytest -q` — **690 passed, 1 skipped** (up from the IMP-703 baseline of 674 passed, 1 skipped — 16 new tests, zero regressions)

`app/tests/integration/test_goal_contribution_reversal.py` (16 tests) covers:
- Reversal: posted contribution can be reversed, reversal creates a balanced reversing journal entry with debit/credit sides swapped, the original entry's lines are byte-for-byte unchanged after reversal, repeated reversal does not duplicate journal entries.
- Progress: reversed contributions no longer count toward `current_amount`/progress, progress-only contributions are unaffected, progress-only contributions cannot be reversed.
- Permissions: PARENT can reverse, VIEWER cannot, an ADULT cannot reverse another member's private-goal contribution, Tenant A cannot reverse Tenant B's contribution.
- API safety: the route requires auth, an invalid contribution ID returns a safe `404`, a contribution from a different goal is rejected via the `goal_id` in the route, and an already-reversed contribution returns its existing state instead of erroring.
- RLS: `goals`, `goal_contributions`, `journal_entries`, `journal_lines` all remain RLS/FORCE-RLS protected.

Regression: `test_family_goals.py`, `test_goal_contributions_accounting.py`, and `test_dashboard_widget.py` (which includes the Family Goals dashboard widget tests) all pass, alongside the complete project test suite.

---

## Known Limitations

- **No dashboard reversal action.** The Family Goals dashboard widget (DB-1105A) shows aggregate progress and quick-contribute/complete/cancel actions, but no per-contribution history list — there is nothing in the current UI to attach a reversal button to without inventing new UI surface area outside this card's scope. Follow-up: **DB-1105B — Family Goal Contribution Reversal Dashboard Action**.
- **No partial reversal.** Like ACC-503A, reversal is always full-entry; there is no way to reverse only part of a contribution's amount.
- **No edit-in-place.** Correcting a posted contribution's amount still requires reverse + re-add rather than an edit endpoint.
- **`reversal_date` is accepted but only affects the reversal journal entry's date**, not the original contribution's `date` field, matching how `reversal_date` already behaves for bill/subscription/allowance reversal.

---

## Recommended Next Card

**DB-1105B — Family Goal Contribution Reversal Dashboard Action**

The reversal engine and API now exist and are fully tested, but the Family Goals dashboard widget has no contribution-history list or reversal action — exactly the same gap DB-1107C closed for allowance payments after FAM-1305 shipped. Add a small, permission-aware contribution list to the goal widget/detail view with a reverse action (with confirmation) that posts to the now-existing `/family/goals/{goal_id}/contributions/{contribution_id}/reverse` route, without duplicating any reversal logic.
