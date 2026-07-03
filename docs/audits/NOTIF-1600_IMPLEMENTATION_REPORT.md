# NOTIF-1600 — Email Notifications and Bill/Subscription Reminders

## Summary

Implemented safe email notification infrastructure and bill/subscription reminder generation for the PF AI Personal Finance platform. The work adds configurable email backends (console/dev, disabled, SMTP), extends the `Notification` model to track channel/status/delivery metadata, exposes notification CRUD and preference endpoints, and generates in-app reminders for upcoming bills, overdue bills, and subscription renewals.

No real email is sent in development by default. No SMTP secrets were committed. RLS and FORCE RLS remain enabled on the `notifications` table.

---

## Files Changed

- `app/config.py` — added email/notification configuration variables.
- `.env.example` — added placeholders for all new email/notification settings.
- `app/models/notification.py` — extended `Notification` with `channel`, `status`, `scheduled_for`, `sent_at`, `error_message`, `related_entity_type`, `related_entity_id`, and `user` relationship; added `NotificationChannel` and `NotificationStatus` enums.
- `app/models/__init__.py` — exported `NotificationStatus`.
- `app/schemas/notification.py` — added response/update schemas for notifications and preferences, plus `ReminderRunResponse` and `TestEmailResponse`.
- `app/notifications/channels/email.py` — new pluggable email backends (`ConsoleEmailBackend`, `DisabledEmailBackend`, `SmtpEmailBackend`) and `send_email()` helper.
- `app/notifications/services.py` — new `NotificationDeliveryService` with CRUD, preferences, email dispatch, and reminder generation.
- `app/notifications/__init__.py` — public exports.
- `app/notifications/channels/__init__.py` — package init.
- `app/routers/notifications.py` — added JSON API endpoints; moved legacy HTML routes to `/notifications/list` and `/notifications/settings-page`.
- `app/services/bill_subscription_service.py` — hardened `create`/`update` to coerce string dates/decimals from test payloads and API clients.
- `app/tasks/notifications.py` — updated Celery stubs to delegate to `NotificationDeliveryService`.
- `scripts/run_notification_reminders.py` — new dev/manual script for running reminders.
- `app/tests/integration/test_notifications.py` — new integration tests.
- `alembic/versions/196cef681c37_extend_notification_model_for_email_.py` — added notification columns and enums.
- `alembic/versions/334009b6ab5a_add_bill_overdue_notification_type_and_.py` — added `BILL_OVERDUE` enum value and verified RLS.
- `app/__init__.py` — simplified to re-export `app` from `app/main` to avoid shadowing the new `app.notifications` package.

---

## Models Used or Changed

### `Notification`

New columns:
- `channel` (`NotificationChannel`) — `in_app`, `email`, `push`, `sms`; defaults to `in_app`.
- `status` (`NotificationStatus`) — `pending`, `sent`, `failed`, `skipped`, `read`; defaults to `pending`.
- `scheduled_for` — optional future delivery time.
- `sent_at` — timestamp when email was successfully handed off.
- `error_message` — delivery failure or skip reason.
- `related_entity_type` / `related_entity_id` — link back to bill, subscription, etc.
- `user` relationship for loading recipient email.

### `NotificationSetting`

Unchanged. Used by `NotificationDeliveryService` to respect per-channel preferences.

---

## Alembic Revision IDs

- `196cef681c37` — extend notification model for email delivery and status tracking.
- `334009b6ab5a` — add `BILL_OVERDUE` value to `notificationtype` enum and verify `notifications` RLS/FORCE RLS.

Current head after this card: `334009b6ab5a`.

---

## Config Variables Added

- `EMAIL_BACKEND` — `console` (default), `smtp`, or `disabled`.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS`.
- `EMAIL_FROM`, `EMAIL_FROM_NAME`.
- `NOTIFICATIONS_ENABLED` — global kill-switch.
- `BILL_REMINDER_DAYS_DEFAULT` — default 3.
- `SUBSCRIPTION_REMINDER_DAYS_DEFAULT` — default 7.
- `EMAIL_DEV_MODE` — existing; still respected by auth dev-mode logging.

---

## Email Backend Behavior

| Backend | Behavior |
|---------|----------|
| `console` | Prints email to stdout; default for development. Returns `success=True`. |
| `disabled` | Silently drops email; returns `success=False` with reason. |
| `smtp` | Sends via configured SMTP only when `SMTP_HOST` and `SMTP_USER` are set. Uses TLS and auth when configured. Returns `success=False` safely if misconfigured or network fails. |

No real email is sent unless `EMAIL_BACKEND=smtp` and valid SMTP credentials are configured.

---

## Routes Added

All JSON routes are under `/notifications` and require authentication and tenant membership. Admin-only routes require `owner` or `admin` tenant role.

- `GET /notifications` — list current user's notifications.
- `POST /notifications` — create a notification for current user.
- `GET /notifications/unread-count` — unread count.
- `PATCH /notifications/{id}/read` — mark read.
- `PATCH /notifications/{id}/unread` — mark unread.
- `POST /notifications/mark-all-read` — mark all user notifications read.
- `GET /notifications/preferences` — list preferences.
- `PATCH /notifications/preferences` — update a preference.
- `POST /notifications/test-email` — send a test email via configured backend.
- `POST /notifications/run-reminders` — generate bill/subscription reminders (tenant admin+).
- `POST /notifications/send-pending-emails` — dispatch pending email notifications (tenant admin+).

Legacy HTML routes:
- `GET /notifications/list`
- `GET /notifications/settings-page`
- `POST /notifications/{id}/read-legacy`

---

## Reminder Generation Behavior

- **Upcoming bills:** unpaid, active bills with `due_date` within `BILL_REMINDER_DAYS_DEFAULT`.
- **Overdue bills:** unpaid, active bills with `due_date` < today.
- **Subscription renewals:** active subscriptions with `next_billing_date` within `SUBSCRIPTION_REMINDER_DAYS_DEFAULT`.

Reminders are created as `IN_APP` notifications with `status=pending`. They link to the source bill/subscription via `related_entity_type` and `related_entity_id`.

---

## Idempotency Behavior

Running reminders twice on the same day does not create duplicates. `_existing_reminder_today()` checks for a notification of the same type for the same entity created since UTC midnight. Duplicates are counted as `skipped` in the `run-reminders` response.

---

## RLS Status

- `notifications` table has RLS enabled and FORCE RLS enabled.
- Policies exist for `SELECT`, `INSERT`, `UPDATE`, and `DELETE` scoped to `tenant_id`.
- `notification_settings` is global per user (not tenant-scoped) and remains without RLS.

---

## Test Results

- Notification tests: **20 passed**.
- Full test suite: **133 passed, 1 skipped**.

Key coverage:
- Console/disabled/SMTP backends.
- `send_email` dispatches to configured backend.
- Notification CRUD, read/unread, unread count, mark-all-read.
- Preference get/update.
- Bill due, bill overdue, and subscription renewal reminder generation.
- Duplicate reminder prevention.
- Email notification marked sent/skipped based on preference.
- Tenant isolation (Tenant A cannot see Tenant B notifications).
- `run-reminders` requires tenant admin.
- RLS remains active on `notifications`.

---

## Known Limitations

- Email sending is console-only by default; production SMTP requires environment variables.
- No HTML email templates yet; bodies are plain text.
- No production Celery scheduling wired; `scripts/run_notification_reminders.py` is provided for dev/manual runs.
- SMS/WhatsApp/push channels are not implemented.
- `mark-paid` for bills/subscriptions still updates status only; accounting-engine integration is deferred to **BILL-801A**.
- Dashboard widget UI that surfaces commitments and notifications is deferred to **DB-1104A**.

---

## Recommended Next Card

**DB-1104A — Bills and Subscriptions Dashboard Widget UI**

The backend now exposes commitments and notifications. The next step is to surface upcoming bills, overdue bills, subscription renewals, monthly totals, and recent unread notifications on the main dashboard, consuming the existing APIs without adding new models or migrations.
