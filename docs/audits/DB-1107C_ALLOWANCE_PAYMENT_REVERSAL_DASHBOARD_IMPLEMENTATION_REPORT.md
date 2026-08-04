# DB-1107C — Allowance Payment Reversal Dashboard Action Implementation Report

## Summary

Added a "Reverse Payment" action to the Chores & Allowance dashboard widget's Recent Payments list, so HEAD/PARENT users can undo a posted allowance payment without leaving the dashboard or using the API directly. The action reuses `FamilyChoreService.reverse_payment()` (FAM-1305) completely unchanged, which itself delegates entirely to `AccountingService.reverse_journal_entry()` (ACC-503A) — no new reversal logic was written anywhere. Following the card's own guidance ("prefer the project's existing HTMX style, do not overbuild"), the action uses the simplest safe pattern already established by the Approve/Submit-Completion quick actions from DB-1107A: a single `hx-post` button with an `hx-confirm` browser-native confirmation prompt, refreshing the whole widget on completion — no separate confirmation route or result template was needed.

No database schema changes were needed. Alembic head remains `bd89e4fcf4b9`.

---

## Files Changed

**New:**
- `app/tests/integration/test_dashboard_allowance_payment_reversal.py` — 21 new tests.

**Modified:**
- `app/schemas/family_chore.py` — `DashboardPaymentHistoryItem` gained `can_reverse: bool = False`.
- `app/routers/dashboard.py` — `_build_family_chores_dashboard()` now computes `can_reverse` per recent-payment item; added `POST /partials/family-chore-completions/{completion_id}/reverse-payment`.
- `app/templates/dashboard/partials/family_chore_ready_to_pay.html` — the "Recent Payments" list now shows a "Reverse" button for eligible Paid items.

`family_chores_widget.html` needed no changes — its existing generic `action_error` alert block (already used by Submit/Approve/Post-Payment) covers reversal errors too.

---

## Routes Added / Updated

| Method | Route | Description |
|---|---|---|
| POST | `/dashboard/partials/family-chore-completions/{completion_id}/reverse-payment` | *(new)* Reverses a posted allowance payment via `FamilyChoreService.reverse_payment()`. Refreshes the whole widget on any outcome (success or handled error). |
| GET | `/dashboard/partials/family-chores` | *(updated)* Recent Payments items now include a `can_reverse` flag driving the Reverse button. |

The new route requires `require_tenant_member` and uses `get_db_with_tenant_context`, matching every other dashboard route. Permission is re-checked inside `FamilyChoreService.reverse_payment()` itself (`require_post_payment()`, HEAD/PARENT only) — a crafted request from a non-elevated role is rejected regardless of what the UI renders.

---

## Templates Added / Updated

`family_chore_ready_to_pay.html`'s Recent Payments row gained, for each item where `item.can_reverse` is true, a "Reverse" button:

```html
<button class="btn btn-sm btn-outline-danger"
        hx-post="/dashboard/partials/family-chore-completions/{{ item.id }}/reverse-payment"
        hx-target="#family-chores-widget"
        hx-swap="outerHTML"
        hx-confirm="Reverse this allowance payment? This creates a reversing journal entry and cannot be undone.">
    <i class="bi bi-arrow-counterclockwise"></i> Reverse
</button>
```

No new template files were needed — `family_chore_reverse_confirm.html` and `family_chore_reverse_result.html` (offered as optional in the card) were deliberately not built, since the single-button + `hx-confirm` + whole-widget-refresh pattern already fully covers confirmation, submission, and result display with zero additional server round-trips or template files, and matches the codebase's existing Approve/Submit-Completion actions exactly.

---

## Reversal Dashboard Behavior

`can_reverse` is computed per recent-payment item in `_build_family_chores_dashboard()`:

```python
can_reverse=(
    can_post_payment
    and completion.payment_status == ChorePaymentStatus.PAID.value
    and bool(completion.payment_journal_entry_id)
    and not completion.payment_reversal_journal_entry_id
)
```

So the Reverse button only ever appears when **all** of the following hold: the viewer is HEAD/PARENT, the completion's `payment_status` is `paid`, a `payment_journal_entry_id` exists, and no `payment_reversal_journal_entry_id` exists yet. It never appears for unpaid, pending, rejected, already-reversed completions, or for TEEN/CHILD/VIEWER/ADULT — verified by `test_reversed_completion_does_not_show_reverse_button` and `test_unauthorized_role_does_not_see_reverse_button`.

---

## Confirmation Behavior

A single-click "Reverse" button carries an `hx-confirm` prompt ("Reverse this allowance payment? This creates a reversing journal entry and cannot be undone."), which HTMX intercepts with the browser's native `confirm()` dialog before issuing the POST — the request is never sent if the user cancels. This matches the exact same pattern already used by the widget's Approve and Archive quick actions (DB-1107A, DB-1106A), so no new confirmation UI pattern was introduced.

---

## HTMX Reversal Submission

- The button posts directly (`hx-target="#family-chores-widget"`, `hx-swap="outerHTML"`) — no intermediate per-item container is needed (unlike the post-payment form, reversal takes no user input beyond the confirmation, so there is nothing to keep "open" on error).
- On both success and handled error, the whole widget is re-rendered server-side and swapped in place, exactly mirroring the existing Submit-Completion and Approve-Completion routes: `action_error` is set on failure and rendered by the widget's existing generic error alert; the response status is `400` on any handled `FamilyChoreServiceError`, `200` otherwise.
- This route deliberately does **not** use the `HX-Retarget`/`HX-Reswap` header trick from the post-payment route, because its `hx-target` is already the whole widget — there is nothing to retarget away from.

---

## Idempotency Behavior

Entirely inherited from FAM-1305's `FamilyChoreService.reverse_payment()`, unchanged:
- If `completion.payment_reversal_journal_entry_id` is already set, the completion is returned unchanged and no new reversal is created.
- `AccountingService.reverse_journal_entry()` itself is also idempotent at the journal-entry level (it looks up any existing reversal by `reversed_entry_id`/reference before creating one).
- Repeated dashboard clicks on the same completion never create a second reversal journal entry — verified by `test_repeated_dashboard_reverse_does_not_duplicate` (asserts exactly one `JournalEntry` row for the reversal ID after two POSTs, and that `reversed_amount` in the allowance summary does not double-count).

---

## Permission Behavior

- `FamilyChoreService.reverse_payment()` calls `require_post_payment()` — HEAD/PARENT only, the exact same gate used for posting (FAM-1305). No new permission logic was written.
- TEEN, CHILD, and VIEWER all receive a handled `FamilyChoreServiceError` ("You do not have permission to post or reverse allowance payments") surfaced as `action_error` with a `400` response — verified by `test_teen_cannot_reverse_payment`, `test_child_cannot_reverse_payment`, `test_viewer_cannot_reverse_payment`.
- The Reverse button itself never renders for these roles (`can_reverse` depends on `can_post_payment`), so the only way to reach the permission check is a direct, crafted request — which is exactly what the tests exercise.

---

## RLS / Tenant Safety

- The route requires `require_tenant_member` and uses `get_db_with_tenant_context`.
- `reverse_payment()`'s completion lookup is tenant-scoped (`FamilyChoreCompletion.tenant_id == self.tenant_id`); a completion belonging to another tenant resolves to "not found," surfaced as a handled `action_error` (not a crash, not a leak).
- `family_chore_completions`, `journal_entries`, and `journal_lines` all retain RLS + FORCE RLS — verified by `test_rls_active_on_reversal_related_tables`.
- Verified by `test_cross_tenant_reverse_attempt_rejected_safely` (no reversal actually happens; the target tenant's completion stays `paid`), `test_tenant_a_cannot_reverse_tenant_b_completion_from_dashboard`, and `test_tenant_a_cannot_see_tenant_b_reverse_control` (the reverse-payment URL for Tenant A's completion never appears in Tenant B's rendered widget).

---

## Read-Only Dashboard Safety

- `test_dashboard_view_creates_no_reversal` confirms that repeatedly loading the dashboard page, the JSON API, and the HTMX widget (3x each) never changes a paid completion's `payment_status` or sets `payment_reversal_journal_entry_id` — only the explicit `POST .../reverse-payment` can do that.
- `test_dashboard_reverse_does_not_modify_accounts_or_goals` confirms `Account`/`Goal` row counts are unchanged by a reversal (only `FamilyChoreCompletion` and the new `JournalEntry`/`JournalLine` rows are affected, exactly as `AccountingService.reverse_journal_entry()` already guarantees).
- `test_original_payment_journal_entry_unchanged_after_dashboard_reversal` confirms the original payment journal entry's lines (debit expense, credit payment account) are byte-for-byte identical after a reversal — nothing is deleted or mutated, only a new offsetting entry is created.

---

## Test Results

- `python -m compileall app` — OK
- `alembic current` — `bd89e4fcf4b9` (unchanged; no migration needed)
- `alembic upgrade head` — OK (no-op)
- `python scripts/inspect_db.py` — OK, 46 tables unchanged
- `python scripts/seed_default_data.py --dev` — OK
- `python -m pytest -q` — **604 passed, 1 skipped** (up from the DB-1107B baseline of 583 passed, 1 skipped — 21 new tests, zero regressions)

`app/tests/integration/test_dashboard_allowance_payment_reversal.py` covers:
- Route/auth: auth required, HEAD/PARENT can reverse, TEEN/CHILD/VIEWER cannot (400), cross-tenant attempt rejected without performing a reversal.
- Template behavior: Reverse button appears only for HEAD/PARENT on a paid completion, disappears once reversed, never appears for unauthorized roles, "Reversed" status appears after the action.
- Reversal behavior: balanced reversal journal entry created, original entry's lines unchanged, `payment_reversal_journal_entry_id` stored, `payment_status` becomes `reversed`, repeated dashboard reversal does not duplicate, cannot reverse an unpaid completion, cannot reverse a completion that was never paid (e.g., rejected).
- Safety: viewing the dashboard creates no reversal, reversal touches no `Account`/`Goal` rows.
- Tenant/RLS: cross-tenant reversal rejected, cross-tenant reverse control never rendered, RLS active on `family_chore_completions`/`journal_entries`/`journal_lines`.

Regression: `test_dashboard_family_chores.py`, `test_family_allowance_payment.py`, `test_dashboard_allowance_payment_form.py`, `test_family_chores.py`, `test_dashboard_widget.py`, and `test_smoke.py` all pass in full, alongside the complete suite.

---

## Known Limitations

- The reverse-payment route returns a flat `400` for every handled error (permission denied, completion not found, already unpaid, cross-tenant), matching the exact precedent already set by the DB-1107A Submit-Completion/Approve-Completion quick actions in this same file — it does **not** distinguish 403/404 the way the more elaborate post-payment/payment-form routes do. This is an intentional consistency choice (see Reversal Dashboard Behavior), not an oversight; cross-tenant and permission failures are still safely rejected and never perform a reversal, just under a single status code.
- The Reverse action has no undo of its own — reversing a payment is itself irreversible from the dashboard (matching `AccountingService.reverse_journal_entry()`'s own guard against reversing a reversal). This is correct, intended accounting behavior, not a gap.
- The "Recent Payments" list a Reverse button can act on remains capped at the 5 most recent items (unchanged limitation from DB-1107B).

---

## Recommended Next Card

With FAM-1304 (chore/allowance tracking) → DB-1107A (dashboard visibility) → FAM-1305 (payment posting/reversal API) → DB-1107B (dashboard posting) → DB-1107C (dashboard reversal) now complete, the entire allowance-to-accounting lifecycle is available both via API and dashboard, HEAD/PARENT-only, idempotent, and fully tenant/RLS-isolated. Per `docs/audits/NEXT_RECOMMENDED_BUILD_ORDER.md` and `PLAN_V2.md`, the next unclaimed, well-scoped area is **REP-2000 — Basic Financial Reports** (balance sheet, income statement, trial balance, net worth), which the accounting engine has been ready to support since GOAL-1401A and BILL-801A but which has not yet been exposed as a dedicated report UI.
