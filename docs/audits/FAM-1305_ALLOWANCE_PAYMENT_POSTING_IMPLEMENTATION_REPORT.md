# FAM-1305 — Allowance Payment Posting Through Accounting Engine Implementation Report

## Summary

Implemented allowance payment posting for approved chore completions through the existing `AccountingService`, following the same pattern established by BILL-801A (bill/subscription mark-paid), ACC-503A (journal reversal), and GOAL-1401A (goal contribution posting). Posting an approved completion's `earned_amount` now creates a balanced double-entry journal entry (debit an Expense account, credit an Asset/payment account) instead of only leaving the amount as a numeric field. Posting is HEAD/PARENT-only, idempotent, tenant/account-validated, and safely reversible. Nothing bypasses `AccountingService`; nothing deletes or mutates a posted journal entry.

Alembic head moved from `356391296d35` to `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `alembic/versions/bd89e4fcf4b9_add_allowance_payment_posting_columns_.py` — migration.
- `app/tests/integration/test_family_allowance_payment.py` — 30 new tests.

**Modified:**
- `app/models/family_chore.py` — added `ChorePaymentStatus` enum and seven payment-posting columns + relationships to `FamilyChoreCompletion`.
- `app/schemas/family_chore.py` — extended `ChoreCompletionResponse` and `AllowanceMemberBreakdown`/`AllowanceSummaryResponse` (and their dashboard equivalents) with payment fields; added `ChorePaymentPostRequest`, `ChorePaymentPostResponse`, `ChorePaymentReverseResponse`.
- `app/services/family_chore_service.py` — added `can_user_post_payment()`/`require_post_payment()`, `_get_account()`/`_validate_payment_account()`/`_validate_expense_account()`, `post_payment()`, `reverse_payment()`, `count_approved_unpaid_completions()`; extended `get_allowance_summary()` with `approved_unpaid_amount`/`paid_amount`/`reversed_amount` (overall and per-member).
- `app/routers/family.py` — added `POST /chore-completions/{id}/post-payment` and `POST /chore-completions/{id}/reverse-payment`; `_to_completion_response()` now includes payment fields.
- `app/routers/dashboard.py` — `_build_family_chores_dashboard()` now includes the new allowance-summary fields, `ready_to_pay_count`, and `permissions.can_post_payment`.
- `app/templates/dashboard/partials/family_chores_widget.html` — added a "N ready to pay" badge/link (HEAD/PARENT only).
- `app/templates/dashboard/partials/family_allowance_summary.html` — added Approved Unpaid / Paid / Reversed stat cards and per-member columns.

---

## Model / Schema Changes

Added to `FamilyChoreCompletion`:

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `payment_status` | `String(20)` | No, default `"unpaid"` | `unpaid` / `paid` / `reversed` |
| `payment_account_id` | FK → `accounts.id` | Yes | Asset account credited |
| `expense_account_id` | FK → `accounts.id` | Yes | Expense account debited |
| `payment_journal_entry_id` | FK → `journal_entries.id` | Yes | Set once paid |
| `payment_reversal_journal_entry_id` | FK → `journal_entries.id` | Yes | Set once reversed |
| `paid_at` | `DateTime` | Yes | |
| `paid_by_user_id` | FK → `users.id` | Yes | |

`ChoreCompletionResponse` now surfaces all seven fields. New dashboard/API schemas (`ChorePaymentPostRequest`, `ChorePaymentPostResponse`, `ChorePaymentReverseResponse`) are kept separate from the FAM-1304 contract, matching the established "dashboard/action schemas separate from core resource schemas" convention.

---

## Alembic Revision

- **Revision ID:** `bd89e4fcf4b9`
- **Down revision:** `356391296d35`
- Adds only nullable/defaulted columns, indexes, and foreign keys to the existing `family_chore_completions` table. No table is dropped or recreated; existing rows are preserved and default to `payment_status = "unpaid"`. RLS + FORCE RLS on `family_chore_completions` (already active from FAM-1304) is untouched — adding columns does not require reapplying policies.

---

## Payment Posting Rules

- Only completions with `status == "approved"` and `earned_amount > 0` can be paid.
- Debit: `expense_account_id` (Expense account) for `earned_amount`.
- Credit: `payment_account_id` (Asset account) for `earned_amount`.
- Narration: `Allowance payment: {chore title}`.
- Reference: `ALLOW-{tenant_id}-{completion_id}` (deterministic, tenant-namespaced, matching `BILL-{tenant_id}-{bill_id}` / `GOAL-{tenant_id}-{goal_id}-{contribution_id}`).
- Date: `payment_date` if supplied, else today.
- Posting always goes through `AccountingService.create_journal_entry()` — `FamilyChoreService` never inserts a `JournalEntry`/`JournalLine` directly.

---

## Account Validation Behavior

- `payment_account_id` and `expense_account_id` are resolved with a tenant-scoped query (`Account.tenant_id == self.tenant_id`); a cross-tenant ID resolves to `None` → `"...account not found"` (404).
- `payment_account_id` must have `account_type == "Asset"`, else `"Payment account must be an Asset account"` (400).
- `expense_account_id` must have `account_type == "Expense"`, else `"Expense account must be an Expense account"` (400).
- Both accounts are additionally checked through `FamilyAccountAccessService.can_use_account_for_posting()` before posting.
- In practice, this last check can never reject a HEAD/PARENT (the only roles allowed to post allowance payments), because `FamilyAccountAccessService` already grants HEAD/PARENT full account access to every account in the tenant — the same rule bills, subscriptions, and budgets already rely on. The check is still present as defense-in-depth in case account-access rules are tightened for elevated roles in the future. See **Known Limitations**.

---

## Permission Behavior

- `FamilyChoreService.can_user_post_payment()` mirrors `can_user_approve_completion()`: **HEAD/PARENT only** (tenant OWNER/ADMIN without a `FamilyMember` row already resolve to HEAD via `FamilyAccountAccessService.get_role()`, matching every other chore permission check).
- ADULT/TEEN/CHILD/VIEWER always receive `403 "You do not have permission to post or reverse allowance payments"` — including the member who submitted/was assigned the chore themselves; submitting a completion never implies the right to pay it.
- The same permission gate covers both posting and reversal.
- Verified by `test_teen_cannot_post_payment`, `test_child_cannot_post_payment`, `test_viewer_cannot_post_payment`, `test_unrelated_adult_cannot_post_payment`, `test_parent_can_post_payment`, `test_head_can_pay_approved_completion`.

---

## Idempotency Behavior

- `post_payment()` checks `completion.payment_journal_entry_id` first; if already set, the completion is returned unchanged and **no new journal entry is created** — matching the bill/subscription `mark_paid()` pattern exactly.
- As a secondary safety net (in case two requests race before the completion row commits), the deterministic `ALLOW-{tenant_id}-{completion_id}` reference is also checked against existing `JournalEntry` rows before creating a new one.
- `reverse_payment()` checks `completion.payment_reversal_journal_entry_id` first; if already set, the completion is returned unchanged.
- Repeated dashboard/API calls never duplicate journal entries — verified by `test_repeated_payment_does_not_duplicate_journal_entry` and `test_repeated_reversal_does_not_duplicate`.

---

## Reversal Behavior

- `reverse_payment()` requires `completion.payment_journal_entry_id` to be set (`"This completion has not been paid"`, 400, otherwise).
- Reversal is delegated entirely to `AccountingService.reverse_journal_entry()` (ACC-503A) — the same idempotent, balanced-reversal engine bills/subscriptions already use. The original journal entry and its lines are never deleted or mutated; only reversal metadata (`reversed_at`, `reversal_entry_id`) is set on the original.
- On success, `completion.payment_reversal_journal_entry_id` is stored and `payment_status` becomes `"reversed"`.
- Verified by `test_reverse_payment_creates_balanced_reversal_journal_entry`, `test_original_payment_journal_entry_unchanged_after_reversal`, `test_cannot_reverse_unpaid_completion`, `test_tenant_a_cannot_reverse_tenant_b_payment`.

---

## Allowance Summary Changes

`get_allowance_summary()` (and the dashboard's `get_approved_allowance_this_month()`-augmented view) now returns, both overall and per-member:

- `pending_approval_amount` — unchanged (submitted, awaiting approval).
- `approved_earned_amount` — unchanged (all-time total ever approved, regardless of payment status).
- `approved_unpaid_amount` — **new**: approved completions with `payment_status == "unpaid"`.
- `paid_amount` — **new**: approved completions with `payment_status == "paid"`.
- `reversed_amount` — **new**: approved completions with `payment_status == "reversed"`.
- `rejected_amount` — unchanged (rejected completions; distinct concept from a reversed *payment*).

`approved_unpaid_amount + paid_amount + reversed_amount == approved_earned_amount` by construction. No existing FAM-1304 field's meaning changed, so no existing test needed updating.

---

## Dashboard Behavior

- The Chores & Allowance widget shows a **"N ready to pay"** badge (HEAD/PARENT only, only when `ready_to_pay_count > 0`) linking to `/family/chores` — it does **not** embed an account-selection payment form or post directly from the dashboard.
- `ready_to_pay_count` comes from a dedicated, role-scoped service method (`count_approved_unpaid_completions()`) — no payment-eligibility calculation is duplicated in the router.
- The allowance summary section gained Approved Unpaid / Paid / Reversed stat cards and matching per-member table columns.
- Verified by `test_dashboard_ready_to_pay_badge_shown_without_payment_form` (badge renders; `payment_account_id`, `expense_account_id`, and `post-payment` never appear in the widget HTML) and `test_dashboard_no_silent_account_guessing_for_teen` (`can_post_payment` is `false` for non-elevated roles).
- Follow-up recommended: **DB-1107B — Allowance Payment Dashboard Action Form**, to let HEAD/PARENT select payment/expense accounts and post directly from the dashboard.

---

## RLS / Tenant Safety

- All new routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other family route.
- `post_payment()`/`reverse_payment()` load the completion and both accounts through tenant-scoped queries; a completion or account belonging to another tenant resolves to "not found" (404), never a silent cross-tenant operation.
- `family_chore_completions`, `journal_entries`, and `journal_lines` all retain RLS + FORCE RLS unchanged — verified by `test_rls_active_on_payment_related_tables`.
- Verified by `test_tenant_a_cannot_pay_tenant_b_completion`, `test_tenant_a_cannot_use_tenant_b_accounts`, `test_tenant_a_cannot_reverse_tenant_b_payment`.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (head)
- `alembic history` — linear through `bd89e4fcf4b9`
- `alembic upgrade head` — OK
- `python scripts/inspect_db.py` — OK, 46 tables unchanged, new columns present on `family_chore_completions`
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **554 passed, 1 skipped** (up from the DB-1107A baseline of 524 passed, 1 skipped — 30 new tests, zero regressions)

`app/tests/integration/test_family_allowance_payment.py` covers: payment posting (approve→pay, balanced debit/credit, idempotency, unapproved/zero-amount rejection), account validation (cross-tenant rejection, non-Asset/non-Expense rejection, HEAD's existing full-account-access behavior), permissions (teen/child/viewer/unrelated-adult rejected, parent/head allowed), reversal (balanced reversal entry, original entry untouched, idempotent reversal, cannot reverse unpaid, cross-tenant reversal rejected), allowance summary (approved_unpaid/paid/reversed amounts, per-member scoping), dashboard safety (badge without a payment form, no permission leak to non-elevated roles), and tenant/RLS isolation.

Regression: `test_family_chores.py`, `test_dashboard_family_chores.py`, `test_dashboard_widget.py`, `test_bills_subscriptions.py`, `test_goal_contributions_accounting.py`, and `test_smoke.py` (including the Alembic-head-matches-DB smoke test) all pass, plus the full suite.

---

## Known Limitations

- **"Reject inaccessible private account" is not independently testable for allowance payments.** Only HEAD/PARENT may post/reverse allowance payments, and `FamilyAccountAccessService` already grants HEAD/PARENT unrestricted access to every account in the tenant (the same design used by bills, subscriptions, and budgets). The account-access check (`can_use_account_for_posting`) is implemented as defense-in-depth for consistency and in case this rule changes, but under the current permission model it can never actually reject a HEAD/PARENT poster. `test_head_can_use_any_tenant_account_for_payment` documents this real behavior instead of asserting a rejection that cannot occur.
- No dashboard UI for selecting payment/expense accounts and posting directly — the widget only shows a "ready to pay" badge/link to the full `/family/chores` page. Follow-up: **DB-1107B — Allowance Payment Dashboard Action Form**.
- Partial payment (paying less than the full `earned_amount`) is not supported — payment is always for the full approved amount, matching how bills/subscriptions post in full.
- No recurring/batch payment posting (e.g., "pay all ready-to-pay completions at once").

---

## Recommended Next Card

**DB-1107B — Allowance Payment Dashboard Action Form**

With payment posting and reversal now fully implemented, tested, and reachable via the API, the natural next step is a dashboard-embedded form (payment account + expense account selectors) so HEAD/PARENT can post an allowance payment without leaving the dashboard — while still never silently guessing which accounts to use.
