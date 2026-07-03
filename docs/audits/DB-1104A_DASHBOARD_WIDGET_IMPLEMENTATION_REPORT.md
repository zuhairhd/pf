# DB-1104A — Bills and Subscriptions Dashboard Widget UI

## Summary

Built a user-facing dashboard widget that surfaces upcoming bills, overdue bills, upcoming subscription renewals, monthly subscription total, and total fixed commitments. The widget reuses the existing `/dashboard/api/commitments` endpoint, adds HTMX-enabled partial routes for refresh and quick actions, and includes empty states for tenants with no data.

No new database models or migrations were required. RLS and FORCE RLS remain active on all tenant-scoped tables.

---

## Files Changed

- `app/routers/dashboard.py` — updated `/dashboard/` to load commitments; extended `/dashboard/api/commitments`; added HTMX partial routes for the widget, mark-paid, and run-reminders.
- `app/schemas/bill_subscription.py` — extended `CommitmentSummary` to include serialized `upcoming_bills`, `overdue_bills`, `upcoming_renewals`, and `currency`.
- `app/templates/dashboard/index.html` — included the commitments widget.
- `app/templates/dashboard/partials/commitments_widget.html` — new main widget template.
- `app/templates/dashboard/partials/upcoming_bills.html` — new upcoming bills list.
- `app/templates/dashboard/partials/overdue_bills.html` — new overdue bills list.
- `app/templates/dashboard/partials/upcoming_subscriptions.html` — new upcoming renewals list.
- `app/templates/base.html` — added Bills, Subscriptions, and Notifications navigation links.
- `app/static/css/style.css` — added commitments widget and `btn-xs` styles.
- `app/tests/integration/test_dashboard_widget.py` — new integration tests.

---

## Routes Added

HTML/widget routes under `/dashboard`:

- `GET /dashboard/` — main dashboard page (now requires auth/tenant membership and renders the widget server-side).
- `GET /dashboard/partials/commitments` — returns the widget HTML for HTMX refresh.
- `POST /dashboard/partials/bills/{bill_id}/mark-paid` — marks a bill paid and returns refreshed widget HTML.
- `POST /dashboard/partials/run-reminders` — runs bill/subscription reminders and returns refreshed widget HTML (tenant admin+).

API route:

- `GET /dashboard/api/commitments` — returns `CommitmentSummary` with counts, totals, currency, and serialized lists.

---

## `/dashboard/api/commitments` Behavior

The endpoint now returns:

```json
{
  "upcoming_bills_count": 1,
  "upcoming_bills_total": "45.000",
  "overdue_bills_count": 0,
  "overdue_bills_total": "0.000",
  "upcoming_renewals_count": 1,
  "upcoming_renewals_total": "15.000",
  "monthly_subscription_total": "15.000",
  "total_fixed_commitments_this_month": "60.000",
  "upcoming_bills": [...],
  "overdue_bills": [...],
  "upcoming_renewals": [...],
  "currency": "OMR"
}
```

The lists contain full `BillResponse` and `SubscriptionResponse` objects, so the UI can display names, providers, due dates, amounts, and frequencies.

---

## HTMX Behavior

- **Refresh button** on the widget uses `hx-get="/dashboard/partials/commitments"` and swaps the whole widget.
- **Mark Paid** buttons use `hx-post="/dashboard/partials/bills/{id}/mark-paid"` with `hx-target="#commitments-widget"` and `hx-swap="outerHTML"`, so the widget updates without a full page reload.
- **Run Reminders** button is shown only for tenant admins and posts to `/dashboard/partials/run-reminders` with the same swap behavior.

The main dashboard page is still server-rendered; HTMX is used only for the widget interactions.

---

## Empty and Error States

- **No upcoming bills:** shows a friendly "No upcoming bills for the next 7 days" message.
- **No overdue bills:** shows "No overdue bills. Great job!".
- **No renewals:** shows "No subscription renewals in the next 30 days.".
- **Pre-existing health score error:** the dashboard catches the `HealthScoreService`/`Account.current_balance` mismatch and renders with `health_score=None` rather than returning a 500 error.

---

## Tenant and RLS Safety

- `/dashboard/` now requires `require_tenant_member`, so unauthenticated users get 401/403.
- All dashboard data is loaded with `get_db_with_tenant_context`, which sets `SET LOCAL app.current_tenant_id`.
- `CommitmentService` filters by `tenant_id`.
- Tests confirm Tenant A's bills/subscriptions do not appear on Tenant B's dashboard or API.
- `bills` and `subscriptions` tables remain protected by RLS + FORCE RLS.

---

## Test Results

- Dashboard widget tests: **13 passed**.
- Full test suite: **146 passed, 1 skipped**.

Key coverage:
- Dashboard requires authentication.
- Dashboard renders for authenticated tenant users.
- Upcoming bills, overdue bills, and upcoming subscriptions appear in the widget.
- Empty states render when no data exists.
- `/dashboard/api/commitments` requires auth and respects tenant isolation.
- Mark-paid quick action works and refreshes the widget.
- Run-reminders quick action works for admins and is rejected for viewers.
- RLS remains active on `bills` and `subscriptions`.

---

## Known Limitations

- HTMX POST requests require the JWT `Authorization` header to be set by the client; there is no cookie-based auth yet, so browser-only use of the quick actions needs a small frontend token injection follow-up.
- The pre-existing `HealthScoreService` references `Account.current_balance`, which does not exist on the `Account` model. The dashboard now catches this error, but the health score widget is non-functional until `Account.current_balance` is added or the service is updated.
- Bills and subscriptions do not yet have dedicated list/detail HTML pages; the dashboard widget provides the primary UI for this card.
- Mark-paid updates bill status only; it does not post journal entries yet.

---

## Recommended Next Card

**BILL-801A — Bill Payment Posting Through Accounting Engine**

Now that bills/subscriptions are visible and can be marked paid, the next step is to post actual journal entries through the double-entry accounting engine when a payment is recorded.
