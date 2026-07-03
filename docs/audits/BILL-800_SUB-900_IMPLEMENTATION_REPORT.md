# BILL-800 / SUB-900 — Bills and Subscriptions Routers Implementation Report

**Project:** C:\dev\PF  
**Card:** BILL-800 / SUB-900 — Build Bills and Subscriptions Routers  
**Date:** 2026-07-03  
**Alembic Head:** c7ec07582862  
**Test Results:** 113 passed, 1 skipped

---

## 1. Summary

Implemented the user-facing Bills and Subscriptions foundation for the Financial Life MVP. The existing `Bill` and `Subscription` models already had tenant scoping and RLS; this card added the missing CRUD routers, service layer, dashboard commitment summaries, and tests. Payment posting through the accounting engine was intentionally deferred to keep the card focused and safe.

---

## 2. Files Changed

### New Files

- `app/routers/bills.py` — Bill CRUD and status routes.
- `app/routers/subscriptions.py` — Subscription CRUD and status routes.
- `app/services/bill_subscription_service.py` — `BillService`, `SubscriptionService`, `CommitmentService`.
- `app/schemas/bill_subscription.py` — Pydantic schemas for bills, subscriptions, and commitment summaries.
- `app/tests/integration/test_bills_subscriptions.py` — 24 integration tests.
- `alembic/versions/c7ec07582862_add_bill_payment_tracking_and_.py` — Schema migration.

### Modified Files

- `app/models/subscription.py` — Added `is_paid`/`paid_at` to `Bill`; added `status` string column to `Subscription`.
- `app/main.py` — Registered `/bills` and `/subscriptions` routers.
- `app/routers/dashboard.py` — Added `/dashboard/api/commitments` endpoint.
- `docs/audits/PLAN_V2_CARD_STATUS.md` — Marked BILL-800/SUB-900 Done.
- `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md` — Marked Card 10 Done; recommended NOTIF-1600 next.

---

## 3. Models Used or Changed

- `app/models/subscription.py::Bill`  
  - Added `is_paid: bool` (default false) and `paid_at: DateTime`.
- `app/models/subscription.py::Subscription`  
  - Added `status: String(20)` (default `"active"`) to support `active`, `paused`, `cancelled`.
  - Kept `is_active` for backwards compatibility with existing queries.

Both models already inherit `TenantMixin` and already had RLS + FORCE RLS enabled in the database.

---

## 4. Alembic Revision

**Revision ID:** `c7ec07582862`  
**Down Revision:** `9ee380da96d5`  
**Changes:**
- `bills.is_paid` (Boolean, NOT NULL, server default false)
- `bills.paid_at` (DateTime, nullable)
- `subscriptions.status` (String(20), NOT NULL, server default 'active')

A plain string column was chosen for `subscriptions.status` to avoid conflicting with the existing PostgreSQL `subscriptionstatus` enum used by `TenantSubscription`.

---

## 5. Bill Routes Added

| Method | Path | Description |
|--------|------|-------------|
| POST | `/bills` | Create a bill |
| GET | `/bills` | List bills (optional `?status=` filter) |
| GET | `/bills/{bill_id}` | Get a single bill |
| PATCH | `/bills/{bill_id}` | Update a bill |
| DELETE | `/bills/{bill_id}` | Delete a bill |
| POST | `/bills/{bill_id}/mark-paid` | Mark bill as paid |
| POST | `/bills/{bill_id}/mark-unpaid` | Revert bill to unpaid |
| POST | `/bills/{bill_id}/cancel` | Cancel a bill |
| GET | `/bills/upcoming` | Bills due today or later |
| GET | `/bills/overdue` | Bills past due date and unpaid |

Computed bill status: `upcoming | paid | overdue | cancelled`.

---

## 6. Subscription Routes Added

| Method | Path | Description |
|--------|------|-------------|
| POST | `/subscriptions` | Create a subscription |
| GET | `/subscriptions` | List subscriptions (optional `?status=` filter) |
| GET | `/subscriptions/{subscription_id}` | Get a single subscription |
| PATCH | `/subscriptions/{subscription_id}` | Update a subscription |
| DELETE | `/subscriptions/{subscription_id}` | Delete a subscription |
| POST | `/subscriptions/{subscription_id}/mark-paid` | Record paid renewal and advance billing date |
| POST | `/subscriptions/{subscription_id}/cancel` | Cancel subscription |
| POST | `/subscriptions/{subscription_id}/pause` | Pause subscription |
| POST | `/subscriptions/{subscription_id}/activate` | Resume subscription |
| GET | `/subscriptions/active` | Active subscriptions |
| GET | `/subscriptions/cancelled` | Cancelled subscriptions |
| GET | `/subscriptions/upcoming-renewals` | Renewals in next 30 days |

Computed fields returned in every response:
- `days_until_renewal`
- `monthly_equivalent_amount`
- `yearly_equivalent_amount`

---

## 7. Dashboard Service Outputs

Added `CommitmentService` and `GET /dashboard/api/commitments` returning:

- `upcoming_bills_count`
- `upcoming_bills_total`
- `overdue_bills_count`
- `overdue_bills_total`
- `upcoming_renewals_count`
- `upcoming_renewals_total`
- `monthly_subscription_total`
- `total_fixed_commitments_this_month`

The endpoint is tenant-scoped and protected by the same RLS context as other routes.

---

## 8. Payment Posting Behavior

- **Deferred.** `POST /bills/{id}/mark-paid` updates `is_paid` and `paid_at` only.
- **Deferred.** `POST /subscriptions/{id}/mark-paid` advances `next_billing_date` by one period.
- No journal entries or transactions are created in this card.
- Follow-up card documented: **BILL-801A — Bill Payment Posting Through Accounting Engine**.

---

## 9. RLS Status

- `bills` table: RLS enabled, FORCE RLS enabled.
- `subscriptions` table: RLS enabled, FORCE RLS enabled.
- All routes use `get_db_with_tenant_context` and `require_tenant_member`, which set `app.current_tenant_id` from the JWT.
- Tenant isolation tests confirm Tenant A cannot see Tenant B bills or subscriptions.

---

## 10. Test Results

```bash
venv/Scripts/python -m pytest app/tests/integration/test_bills_subscriptions.py -v
# 24 passed, 3 warnings

venv/Scripts/python -m pytest -q
# 113 passed, 1 skipped, 3 warnings
```

### Tests Added

- Bill CRUD (create, list, get, update, delete)
- Bill status transitions (mark-paid, mark-unpaid, cancel)
- Overdue bills query
- Subscription CRUD
- Subscription status transitions (mark-paid, cancel, pause, activate)
- Monthly/yearly equivalent amount calculations
- Tenant isolation for bills and subscriptions
- Anonymous request rejection
- RLS active on `bills` and `subscriptions`
- Dashboard commitments summary

---

## 11. Known Limitations

- Payment posting does not create journal entries; deferred to BILL-801A.
- Bill reminders and subscription renewal alerts are not scheduled; deferred to NOTIF-1600.
- Dashboard output is API-only; widget UI templates deferred to DB-1104A.
- Subscription status uses a string column rather than a dedicated enum to avoid collision with the existing `subscriptionstatus` enum.

---

## 12. Recommended Next Card

**NOTIF-1600 — Email Notifications and Bill/Subscription Reminders**

This card will add SMTP/console notification delivery and scheduled reminders for upcoming bills and subscription renewals, completing the deferred reminder behavior from BILL-800 / SUB-900.

---

*End of BILL-800_SUB-900_IMPLEMENTATION_REPORT.md*
