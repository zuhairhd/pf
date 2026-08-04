> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 42: GOAL-1401B — Goal Contribution Reversal**.

# Summary 35 — Card 42: GOAL-1401B Goal Contribution Reversal

## What Was Done

Implemented safe reversal for family goal contributions posted through the accounting engine (GOAL-1401A). A new `POST /family/goals/{goal_id}/contributions/{contribution_id}/reverse` route calls `FamilyGoalService.reverse_contribution()`, which reuses `AccountingService.reverse_journal_entry()` unchanged — the same engine already proven by ACC-503A (bill/subscription reversal) and FAM-1305 (allowance payment reversal). The original journal entry is never deleted or mutated; reversal is idempotent; and `goal.current_amount` is decremented so a reversed contribution no longer counts toward active progress while the original row remains for audit.

## Key Changes

- `GoalContribution` gained four nullable columns: `reversal_journal_entry_id`, `reversed_at`, `reversed_by_user_id`, `reversal_reason` (Alembic `a4c9e1f7b2d3`, additive only — hand-written after autogenerate proposed unrelated, pre-existing FK-comparator noise on other tables).
- `app/services/family_goal_service.py`: added `reverse_contribution()`, gated by `require_manage()` (stricter than the `require_contribute()` used to add a contribution — mirrors the FAM-1305 precedent that undoing a posting requires more permission than making one).
- `app/routers/family.py`: added the reverse route, matching the existing `.../contributions/{contribution_id}/post` naming convention.
- `app/schemas/goal.py`: extended `GoalContributionResponse`; added `GoalContributionReversalRequest`.
- Reversing decrements `goal.current_amount` (reverting `status` from `completed` to `active` if it drops back below target) and is idempotent — a second call returns the existing reversal unchanged.
- No dashboard changes in this card (no per-contribution history list exists to attach a reversal action to) — follow-up documented as DB-1105B.
- Added `app/tests/integration/test_goal_contribution_reversal.py` with 16 tests: reversal, progress exclusion, permissions, tenant/RLS isolation, idempotency, and API safety.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `a4c9e1f7b2d3` (head, up from `bd89e4fcf4b9`)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged, new columns present on `goal_contributions`
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **690 passed, 1 skipped** (up from 674 passed, 1 skipped)

## Next Recommended Card

**DB-1105B — Family Goal Contribution Reversal Dashboard Action**
