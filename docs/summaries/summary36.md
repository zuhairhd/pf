> **Note:** Summary files are incrementally appended. This entry covers the work completed for **Card 43: DB-1105B — Family Goal Contribution Reversal Dashboard Action**.

# Summary 36 — Card 43: DB-1105B Family Goal Contribution Reversal Dashboard Action

## What Was Done

Added a permission-aware "Recent Contributions" list to each goal card in the Family Goals dashboard widget, plus a "Reverse" action for eligible posted contributions — reusing `FamilyGoalService.reverse_contribution()` (and transitively `AccountingService.reverse_journal_entry()`) unchanged from GOAL-1401B. No reversal logic was rebuilt; this card only adds a read-only contribution list and a thin HTMX route that calls the existing service and re-renders the widget.

## Key Changes

- No schema changes; no Alembic migration (head unchanged at `a4c9e1f7b2d3`).
- `app/schemas/goal.py`: added `DashboardGoalContributionItem`; `DashboardFamilyGoalItem` gained `recent_contributions` (default `[]`, backward compatible).
- `app/routers/dashboard.py`: `_build_family_goals_dashboard()` now loads each goal's recent contributions (via the unchanged `FamilyGoalService.list_contributions()`) and computes a `can_reverse` flag per contribution (mirrors the exact eligibility `reverse_contribution()` itself enforces); added `POST /dashboard/partials/family-goals/{goal_id}/contributions/{contribution_id}/reverse`.
- New template `family_goal_contributions.html`, included at the bottom of `family_goal_card.html`; shows date/amount/contributor/status badge and a `hx-confirm`-gated Reverse button (matching the existing complete/cancel button pattern) when eligible.
- The Reverse button's visibility is a display-only convenience — the backend's own `require_manage()` check still runs on every POST, so an unauthorized or crafted request is rejected server-side regardless of what the client shows.
- Added `app/tests/integration/test_dashboard_family_goals_reversal.py` with 18 tests: rendering/eligibility, route/auth, reversal correctness, idempotency, read-only safety, and tenant/RLS isolation.

## Verification

- `python -m compileall app` — OK
- `alembic current` — `a4c9e1f7b2d3` (unchanged, no new migration)
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **708 passed, 1 skipped** (up from 690 passed, 1 skipped)

## Next Recommended Card

**AUTH-305 — Tenant Member Invitation Flow**
