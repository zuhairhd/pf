# DB-1107B — Allowance Payment Dashboard Action Form Implementation Report

## Summary

Added an inline, HTMX-driven payment form to the Chores & Allowance dashboard widget, so HEAD/PARENT users can post an approved allowance payment without leaving the dashboard. The form requires an explicit payment (Asset) account and expense account selection — the dashboard never guesses or auto-fills accounts. Submitting the form posts through the unchanged `FamilyChoreService.post_payment()` (FAM-1305), which in turn goes exclusively through `AccountingService`. The widget also gained a "Ready to Pay" list (replacing the plain badge with actionable items) and a small "Recent Payments" history showing Paid/Reversed status and journal entry references.

No database schema changes were needed. Alembic head remains `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `app/templates/dashboard/partials/family_chore_payment_form.html` — the account-picker payment form (and its error/closed states).
- `app/templates/dashboard/partials/family_chore_ready_to_pay.html` — the "ready to pay" list (with per-item "Post Payment" buttons and inline form containers) plus a small "Recent Payments" history block.
- `app/tests/integration/test_dashboard_allowance_payment_form.py` — 29 new tests.

**Modified:**
- `app/schemas/family_chore.py` — added `DashboardAccountOption`, `DashboardReadyToPayItem`, `DashboardPaymentHistoryItem`; `FamilyChoresDashboardResponse` gained `ready_to_pay: List[DashboardReadyToPayItem]` and `recent_payments: List[DashboardPaymentHistoryItem]`.
- `app/services/family_chore_service.py` — added `list_approved_unpaid_completions_for_user()` (the full-item version of the existing count) and `list_recent_paid_completions_for_user(limit=5)`; `count_approved_unpaid_completions()` now delegates to the new list method instead of duplicating the query.
- `app/routers/dashboard.py` — `_build_family_chores_dashboard()` now also returns `ready_to_pay` and `recent_payments`; added `_dashboard_account_options()`, `_dashboard_ready_to_pay_item()`, `_dashboard_chore_error_status()` helpers, and two new routes (see below).
- `app/templates/dashboard/partials/family_chores_widget.html` — the old "N ready to pay" link/badge is replaced by a full "Ready to Pay" section (HEAD/PARENT only, gated on `permissions.can_post_payment`).

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| GET | `/dashboard/partials/family-chore-completions/{completion_id}/payment-form` | *(new)* Renders the inline payment form (account selects, date, notes) for one approved-unpaid completion. Read-only. HEAD/PARENT only. |
| POST | `/dashboard/partials/family-chore-completions/{completion_id}/post-payment` | *(new)* Submits the chosen accounts and posts the payment through `FamilyChoreService.post_payment()`. On success, refreshes the whole widget (via `HX-Retarget`/`HX-Reswap` response headers); on error, re-renders just the inline form with a message. |
| GET | `/dashboard/partials/family-chores` | *(updated)* Now also renders the "Ready to Pay" and "Recent Payments" sections. |

Both new routes require `require_tenant_member` and use `get_db_with_tenant_context`, matching every other dashboard route. Permission is additionally re-checked inside the handler via `FamilyChoreService.can_user_post_payment()` — a crafted request from a non-HEAD/PARENT user is rejected with 403 even if the button was never rendered for them.

---

## Templates Added / Updated

See "Files Changed." `family_chores_widget.html` keeps every other existing section (summary cards, overdue badge, chores list, Pending Approvals, Allowance Summary) exactly as before — only the "ready to pay" badge/link was upgraded into a full section.

---

## Form Behavior

The form (`family_chore_payment_form.html`) shows, for one completion:
- Chore title and, where safe, the assigned member's name.
- Earned amount (currency-formatted).
- A `<select>` of payment (Asset) accounts and a `<select>` of expense accounts, both **required** — the browser will not submit without a selection, and the server independently rejects a missing selection too (defense in depth).
- An optional payment date input and an optional notes input.
- A "Post Payment" submit button and a "Cancel" button that clears the inline form without submitting anything.

If the completion is not eligible (not approved, already paid, or `earned_amount <= 0`) or the requester lacks permission, the GET route renders the same partial with only an inline error message and no form — the form is never shown for an un-payable completion.

---

## Account Picker Behavior

- `_dashboard_account_options()` calls the unchanged `FamilyAccountAccessService.list_visible_accounts()` — no new visibility logic was written.
- Payment options are filtered to `account_type == "Asset"`; expense options to `account_type == "Expense"`. This type filtering is genuinely testable and verified: an Expense-type account never appears in the payment `<select>`, and an Asset-type account never appears in the expense `<select>`.
- `list_visible_accounts()` is tenant-scoped, so a cross-tenant account's name can never appear in the picker — verified by `test_cross_tenant_account_names_do_not_appear_in_form`.
- As documented in FAM-1305, HEAD/PARENT (the only roles that can open this form) already have unrestricted visibility to every account in their own tenant via `FamilyAccountAccessService`, so — exactly like the FAM-1305 posting endpoint itself — a HEAD/PARENT's account picker will list every tenant account, including one owned privately by another family member. This is documented, existing, intentional behavior (FAM-1301), not a gap introduced here. See **Known Limitations**.

---

## HTMX Behavior

- **Open form**: each "ready to pay" item's "Post Payment" button (`hx-get=".../payment-form"`, `hx-target="#payment-form-{completion_id}"`, `hx-swap="innerHTML"`) loads the form into a per-item placeholder `<div>`, exactly mirroring the existing `family_budget_card.html` "Categories" expand pattern from DB-1106A.
- **Cancel**: a plain button clears the same placeholder's `innerHTML` via a tiny, safe, no-network `onclick` (no established HTMX-only "collapse" pattern exists elsewhere in this codebase to reuse).
- **Submit (success)**: the form (`hx-post=".../post-payment"`, `hx-target="#payment-form-{completion_id}"`, `hx-swap="innerHTML"`) posts the selections. On success, the response sets `HX-Retarget: #family-chores-widget` and `HX-Reswap: outerHTML` headers and returns the fully refreshed widget — HTMX honors these headers and swaps the *entire* widget in place instead of just the small form container, so the paid completion immediately disappears from "Ready to Pay" and the allowance summary/"Recent Payments" reflect the new Paid total.
- **Submit (error)**: no retarget headers are set; the response re-renders just the inline form (same target/swap as the GET) with the error message and the same account options, so the user can immediately correct their selection without losing their place on the page.
- Repeated dashboard submissions never duplicate a journal entry (see Idempotency below).

---

## Payment Status Display

- **Ready to Pay** section: one card per approved-unpaid completion with a "Ready to pay" badge and, for HEAD/PARENT, a "Post Payment" button.
- **Recent Payments** (small history list, up to 5 most recent, HEAD/PARENT and self-scoped for other roles): shows a green "Paid" badge with `(JE #{payment_journal_entry_id})`, or a grey "Reversed" badge with `(JE #{payment_reversal_journal_entry_id})` — the journal entry ID is shown as a safe reference, not the full journal entry detail.
- Pending-approval and rejected completions are unaffected — their existing display (Pending Approvals section, allowance summary Pending/Rejected figures) is untouched.

---

## Idempotency Behavior

Unchanged from FAM-1305, reused as-is: `FamilyChoreService.post_payment()` checks `completion.payment_journal_entry_id` first and returns the completion unchanged (no new journal entry) if already paid. The dashboard form calls this same method, so:
- Resubmitting the same form (e.g., a double-click or a retried request) never creates a second journal entry — verified by `test_repeated_dashboard_post_does_not_duplicate_journal_entry`.
- Opening/reloading the form, or submitting it again after the completion is already paid (e.g., paid via the plain API in another tab), returns a normal success response (widget refresh) rather than an error — verified by `test_already_paid_completion_returns_safe_response`.

---

## Permission Behavior

- `can_user_post_payment()` (HEAD/PARENT only, unchanged from FAM-1305) gates both new routes independently of what the UI renders:
  - GET `.../payment-form` returns a 403 inline-error partial (never the form) for TEEN/CHILD/VIEWER/ADULT.
  - POST `.../post-payment` returns 403 for the same roles even with a well-formed, valid request body.
- The "Ready to Pay" section itself only renders for HEAD/PARENT (`family_chores.permissions.can_post_payment`); other roles never see the section, the badge, or a "Post Payment" button at all.
- Verified by `test_teen_cannot_open_payment_form`, `test_child_cannot_open_payment_form`, `test_viewer_cannot_open_payment_form`, `test_teen_cannot_post_payment_from_dashboard_form`, `test_ready_to_pay_button_does_not_appear_for_teen`, `test_ready_to_pay_button_does_not_appear_for_viewer`.

---

## RLS / Tenant Safety

- Both new routes require `require_tenant_member` and use `get_db_with_tenant_context`.
- The completion lookup and both account lookups inside `post_payment()` are tenant-scoped (unchanged from FAM-1305); a completion or account belonging to another tenant resolves to "not found" (404) — never a silent cross-tenant read or write.
- `family_chore_completions`, `journal_entries`, and `journal_lines` all retain RLS + FORCE RLS — verified by `test_rls_active_on_payment_related_tables_via_dashboard_form`.
- Verified by `test_tenant_a_cannot_open_payment_form_for_tenant_b_completion` and `test_tenant_a_cannot_post_payment_for_tenant_b_completion` (both 404).

---

## Read-Only Dashboard Safety

- `test_viewing_dashboard_and_opening_form_creates_no_journal_entries` confirms that loading the dashboard page, the JSON API, the HTMX widget, and opening the payment form (GET) all leave `Account`/`Goal`/`JournalEntry` row counts unchanged.
- Only the explicit `POST .../post-payment` route can create a journal entry, and it only does so through `FamilyChoreService.post_payment()` → `AccountingService.create_journal_entry()` — never a direct insert, never an unbalanced entry (the underlying `AccountingService.create_journal_entry()` still enforces debit == credit).
- No reversal UI was added in this card (see Known Limitations) — nothing in this card can delete or mutate a posted journal entry.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **583 passed, 1 skipped** (up from the FAM-1305 baseline of 554 passed, 1 skipped — 29 new tests, zero regressions)

`app/tests/integration/test_dashboard_allowance_payment_form.py` covers:
- Form rendering: auth required, HEAD/PARENT can open the form, TEEN/CHILD/VIEWER cannot, Expense accounts never appear in the payment select and vice versa, cross-tenant account names never appear.
- Posting: HEAD/PARENT can post from the dashboard form, creates a balanced journal entry, stores `payment_journal_entry_id`, marks `payment_status = paid`, repeated submission does not duplicate the journal entry, an already-paid completion returns a safe (non-erroring) response, an unapproved completion is rejected, missing account fields are rejected, non-Asset/non-Expense accounts are rejected, cross-tenant accounts are rejected, TEEN cannot post via the form.
- Dashboard: the "Post Payment" button/"Ready to Pay" section appears only for HEAD/PARENT, the widget updates after payment (item leaves "ready to pay"), "Paid" status appears after payment, viewing the dashboard and opening the form creates no journal entries.
- Tenant/RLS: Tenant A cannot open or post a payment for Tenant B's completion; RLS remains active on `family_chore_completions`, `journal_entries`, `journal_lines`.

Regression: `test_dashboard_family_chores.py`, `test_family_allowance_payment.py`, `test_family_chores.py`, `test_dashboard_widget.py`, and `test_smoke.py` all pass in full, alongside the complete suite.

---

## Known Limitations

- **Account picker cannot exclude "inaccessible private" accounts for the only role permitted to use it.** Identical to the limitation already documented in FAM-1305: only HEAD/PARENT can open this form, and `FamilyAccountAccessService` already grants HEAD/PARENT unrestricted visibility to every account in the tenant. The picker still reuses `list_visible_accounts()` unchanged (rather than bypassing it), so if account-visibility rules for elevated roles are ever tightened, the picker automatically inherits the stricter behavior — but under the current permission model it cannot be independently demonstrated to exclude a private account.
- **No reversal UI was added.** Per the card's own guidance ("do not add reversal UI unless simple and safe"), reversal remains API-only (`POST /family/chore-completions/{id}/reverse-payment`, FAM-1305). Follow-up: **DB-1107C — Allowance Payment Reversal Dashboard Action**.
- The "Recent Payments" list is capped at 5 items with no pagination or full history browsing.
- The payment date/notes inputs are plain HTML inputs with only client-side `type="date"`/`maxlength` hints; server-side validation only checks the date parses (`date.fromisoformat`) and otherwise defers to `FamilyChoreService.post_payment()`'s existing rules.

---

## Recommended Next Card

**DB-1107C — Allowance Payment Reversal Dashboard Action**

With posting now fully available from the dashboard, the natural next step is a simple, clearly-confirmed "Reverse Payment" action in the "Recent Payments" list (HEAD/PARENT only), reusing `FamilyChoreService.reverse_payment()` unchanged — completing the dashboard's coverage of the full FAM-1305 payment lifecycle (post and reverse) without ever bypassing `AccountingService`.
