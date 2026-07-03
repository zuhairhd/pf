# Summary 05 — Card 12: DB-1104A Bills and Subscriptions Dashboard Widget UI

## What was implemented

- Extended `/dashboard/api/commitments` to return UI-ready JSON with serialized upcoming bills, overdue bills, upcoming renewals, totals, counts, and currency.
- Updated `/dashboard/` route to require authentication, load commitments, and render the widget server-side.
- Added HTMX partial routes:
  - `GET /dashboard/partials/commitments`
  - `POST /dashboard/partials/bills/{id}/mark-paid`
  - `POST /dashboard/partials/run-reminders`
- Added four new Jinja2 partial templates for the widget and its sections.
- Added summary cards, empty states, and quick actions (Mark Paid, Run Reminders for admins).
- Updated `base.html` navigation with Bills, Subscriptions, and Notifications links.
- Added widget-specific CSS.
- Added defensive error handling for the pre-existing `HealthScoreService` bug so the dashboard renders.

## No migrations

This card was UI-only; no Alembic migrations were required.

## Tests

- Dashboard widget integration tests: 13 passed.
- Full suite: **146 passed, 1 skipped**.

## Key fixes during the card

- Switched `TemplateResponse` calls to the newer Starlette signature `(request, name, context)` to avoid Jinja2 cache-key errors.
- Wrapped `HealthScoreService` calls in try/except because `Account.current_balance` does not exist.

## Next recommended card

**BILL-801A — Bill Payment Posting Through Accounting Engine**
