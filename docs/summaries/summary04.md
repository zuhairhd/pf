# Summary 04 — Card 11: NOTIF-1600 Email Notifications and Reminders

## What was implemented

- Safe email notification infrastructure with pluggable backends:
  - `console` (default, dev-only logging)
  - `disabled` (drops email)
  - `smtp` (production, only sends when fully configured)
- Extended `Notification` model with `channel`, `status`, `scheduled_for`, `sent_at`, `error_message`, `related_entity_type`, `related_entity_id`.
- Added `NotificationChannel` and `NotificationStatus` enums.
- Created `app/notifications/` package with `channels/email.py` and `services.py`.
- Added notification CRUD, preferences, test-email, and reminder endpoints under `/notifications`.
- Added bill/subscription reminder generation with duplicate prevention.
- Added `scripts/run_notification_reminders.py` for manual/dev runs.
- Updated Celery stubs in `app/tasks/notifications.py`.
- Fixed stale `app/__init__.py` to re-export `app.main` so new modules are reachable via `run.py`.
- Hardened `BillService`/`SubscriptionService` to coerce string dates and amounts.

## Migrations

- `196cef681c37` — extend notification model for email delivery.
- `334009b6ab5a` — add `BILL_OVERDUE` enum value and verify `notifications` RLS/FORCE RLS.

## Tests

- Notification integration tests: 20 passed.
- Full suite: **133 passed, 1 skipped**.

## Key fixes during the card

- Removed duplicate router prefix on `/notifications` so JSON API routes resolve correctly.
- Added missing `BILL_OVERDUE` value to the PostgreSQL `notificationtype` enum.
- Fixed `app/__init__.py` shadowing the `app.notifications` package.
- Added date/decimal coercion in bill/subscription services to support direct service calls from tests.

## Next recommended card

**DB-1104A — Bills and Subscriptions Dashboard Widget UI**
