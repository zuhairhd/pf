> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 34: FAM-1304 — Allowance and Chore Tracking**.

# Summary 27 — Card 34: FAM-1304 Allowance and Chore Tracking

## What Was Done

Implemented family chore assignment and allowance tracking: heads/parents define chores (optionally assigned to a specific family member, with an allowance amount, frequency, and due date), assigned members submit completions, and heads/parents approve or reject those completions. Approved completions record an `earned_amount`; a read-only allowance summary aggregates pending/approved/rejected totals per member, scoped by role. No payments, transactions, journal entries, or account-balance changes are created anywhere — allowance amounts are tracked as plain numeric fields only.

## Key Changes

- Migration `356391296d35` adds two brand-new tenant-scoped tables with RLS + FORCE RLS from creation: `family_chores` and `family_chore_completions` (46 tables total, was 44; RLS active on 37, was 35).
- Added `app/models/family_chore.py`: `FamilyChore`, `FamilyChoreCompletion` models; `ChoreFrequency`, `ChoreStatus`, `ChoreCompletionStatus` enums.
- Added `app/services/family_chore_service.py` (`FamilyChoreService`):
  - Role resolution delegated to `FamilyAccountAccessService`, consistent with `FamilyBudgetService`
  - Chore CRUD (create/list/get/update/archive), gated to HEAD/PARENT for create/manage
  - Completion submit (assigned member only — unassigned members cannot submit another member's chore), approve/reject (HEAD/PARENT only; reject requires a reason)
  - `get_allowance_summary()` — pending/approved/rejected totals + per-member breakdown, scoped to "own completions only" for everyone except HEAD/PARENT
  - `get_family_chore_summary()` — lightweight aggregate added specifically for a future dashboard widget (DB-1107A)
- Added `/family/chores/*`, `/family/chore-completions/{id}/approve|reject`, and `/family/allowance-summary` routes in `app/routers/family.py`
- Role matrix: HEAD/PARENT full control and full visibility; ADULT sees all chores but cannot create/manage/approve (no elevated-permission flag exists yet for chores, per the card's own conditional wording); TEEN/CHILD can only view/act on chores assigned to themselves; VIEWER is fully read-only
- Added `app/tests/integration/test_family_chores.py` with 29 tests covering chore CRUD permissions, completion submit/approve/reject, allowance summary math and role-scoping, tenant/RLS isolation, and read-only financial safety

## Verification

- `python -m compileall app` — OK
- `alembic current` — `356391296d35` (new head)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables, RLS active on 37; `family_chores`/`family_chore_completions` confirmed RLS + FORCE RLS
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **499 passed, 1 skipped**

## Next Recommended Card

**DB-1107A — Allowance and Chore Dashboard Widget UI**
