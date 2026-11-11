# Step 10 — Rental Agreements & PDC Cheque Management

Scope: Rental Agreements, PDC cheque generation and management, renewal, rental/PDC alerts, and the integration of **cleared**
cheques with Cash & Banks. **Not built** (later steps): Task Management, Reports & Analytics, customer orders.
Steps 1–9 are preserved; the only existing code touched is listed in section 11.

> Verification status: verified against a real PostgreSQL 16 with RLS, the real FastAPI app and the real React app.
> **Supabase Auth was simulated** (`e2e/fake_gotrue.py`). A real Supabase project was never available, so email delivery,
> dashboard settings and key handling on a real project are untested. Nothing here claims otherwise.
> No external WhatsApp / SMS / email notification exists or was added: alerts are on-screen only.

## 1. Rental module (Owner only, all configured branches)
One permission module, `rentals_cheques`, covers both Rental Agreements and PDC Cheques. The Owner holds read / create / update /
export; the Branch User holds nothing (every endpoint answers 403 with an `ACCESS_DENIED` audit row; the pages and menu entries are
hidden; RLS also blocks the tables for non-Owners).

| Field | Rule |
|---|---|
| Branch | one of the configured branches (active) |
| Landlord name | required, 150 characters |
| Rental unit / property details | optional, 200 characters |
| Start date / end date | end must be after start. Default end = **start + 12 months − 1 day** (28 Feb is the end of a 1 Mar start; month ends are clamped) |
| Annual rent (AED) | more than 0, two decimals |
| Number of cheques | 1 to 12 |
| First cheque date / first cheque number | required; the number must **end in digits** so the following numbers can continue it |
| Bank | ENBD or ADCB |
| Notes | optional, 1000 characters |

Capabilities: add (preview → confirm), view details, update, branch-wise listing, search (branch, landlord, rental unit),
filter by branch and status, sort (end date, start date, branch, landlord, rent), upcoming expiries (next 90 days, soonest first),
linked PDC schedule, renewal chain.

**Agreement status** is derived from dates on every read (never stored as a label that can go stale): *Scheduled* (starts in the
future), *Active*, *Expiring* (ends within 30 days), *Expired* (ended and not renewed), *Renewed*, *Terminated* (reserved; no screen
sets it yet). Python (`core/rentals.py`) and SQL (`AGREEMENT_STATUS`) implement the same rule and a test compares them.

**Update rules (approved audit rules).** Only an agreement that is stored *Active* can be edited. Branch or date changes need a reason
(3+ characters). **Annual rent, number of cheques, bank, first cheque date/number cannot be edited** after creation (the API rejects
unknown fields): the schedule would no longer match. Money changes go through cheque replacement or renewal. Every change is in the
append-only `audit_log` (old/new values, user, time, reason) and is shown as readable lines in the Change history.

## 2. Cheque generation — formulas (documented and tested)
Let `R` = annual rent, `n` = number of cheques, `k` = 0 … n−1.

| Item | Rule |
|---|---|
| Regular amount | `round_half_up(R ÷ n)` to a **whole dirham** |
| Last cheque | `R − (n−1) × regular amount` (takes the remainder, may be a few dirhams different) |
| Total | always exactly `R`; every amount must be more than 0, otherwise 422 (rent too small to split) |
| Indexing convention | **`k` is 0-based**: cheque 0 is on the First Cheque Date |
| Cheque k date | `First Cheque Date + round_half_up(12 × k ÷ n)` months, always computed **from the first date** (never chained) and clamped to the month end (31 Jan + 1 month = 28/29 Feb; + 2 months = 31 Mar) |
| Cheque k number | the first number with its trailing digits increased by `k`; leading zeros and any prefix are kept (`000099` → `000100`; `AB0009` + 2 → `AB0011`) |

Worked examples (tests assert them): 100 000 ÷ 12 → eleven cheques of 8 333 and a last cheque of 8 337; 100 000 ÷ 3 → 33 333, 33 333,
33 334; for n = 8 the month offsets are 0, 2, 3, 5, 6, 8, 9, 11; for n = 4: 0, 3, 6, 9.

**Review before confirming.** `POST /rentals/schedule-preview` returns the lines, total rent, total cheque value, count and a
`matches` flag; nothing is saved. The form then sends exactly the reviewed lines back with `POST /rentals`, and the server
re-validates them: count equals the chosen number, total equals the annual rent, no duplicate number on the same bank, no duplicate
inside the schedule. Changing any field after a preview forces a new preview. Agreement and all cheques are inserted in one
transaction.

## 3. PDC cheques
Each cheque has branch (through its agreement), agreement, landlord, number, date, amount, bank, status (Pending / Cleared /
Bounced), cleared date, bounced date, notes. Cheque numbers are unique **per bank** across the whole system (a bounced cheque's
number is never reused) and per agreement.

PDC Cheques screen: summary cards (Total Pending, Pending Due Within 30 Days, Overdue Pending, Cleared, Bounced, Total Pending Amount,
Total Bounced Amount) plus the **Next Upcoming Cheque**; columns Cheque Date, Number, Branch, Landlord, Rental Agreement, Bank, Amount,
Status, Actions; search (number, branch, landlord); filters (branch, bank, status, date range); sort; quick views *Overdue pending*,
*Upcoming pending*, *Bounced, not replaced*; cheque detail page with history.

| Card | Definition |
|---|---|
| Pending Due Within 30 Days | Pending, cheque date from today to today + 30 |
| Overdue Pending | Pending, cheque date before today (Dubai) |
| Total Pending / Bounced Amount | sum of Pending / of all Bounced cheques (the card also states how many bounced cheques have no replacement yet) |

### Mark Cleared
Pending → Cleared only. Confirmation dialog states the consequence (bank, amount, cheque date). The cleared date defaults to today
(Dubai), may not be in the future, and may not be before financial tracking started. The cheque's date, number, amount and bank are
never touched. The action takes the Step 8 finance lock and requires opening balances to be configured (409 `opening_not_configured`
otherwise). A repeated clear is refused (409 `cheque_not_pending`).

### Mark Bounced
Pending → Bounced only; confirmation, a reason (3+ characters) and a bounced date (default today). **No bank deduction.** The record is
kept as it was; a *Bounced cheque* alert appears under Needs Attention until it is replaced.

### Final records and replacement
**Cleared and Bounced cheques are final.** A database trigger (`app.pdc_guard`) refuses any change to status, number, bank, date,
amount, agreement or cleared/bounced dates after the cheque left Pending, and refuses every DELETE (`23514`). A cleared cheque cannot
become Bounced or Pending again. A bounced cheque is corrected by **Replace cheque**: a new Pending cheque on the same agreement with
the **same amount**, a new unique number, linked through `replaces_id`. A bounced cheque can be replaced once. The bounced record
stays, is flagged *Replaced by …* and is left out of the live schedule total (so the live total still equals the annual rent).
Pending cheques can be edited (number, date, bank, notes; reason required; **amount never**). A standalone "add a cheque" is only
available as a replacement, because adding a cheque to a fully distributed agreement would break "total = annual rent".

## 4. Renewal
`POST /rentals/{id}/renewal-preview` (nothing saved) then `POST /rentals/{id}/renew`.

| Item | Rule |
|---|---|
| New start | old end + 1 day |
| New end | new start + 12 months − 1 day |
| Rent, cheque count, bank | carried forward unless the Owner overrides them |
| First cheque date | defaults to the new start date (override allowed) |
| Cheque numbering | continues after the **highest number of the same prefix series** on the old agreement (`E2E000900` → `E2E000901`); the Owner may override |
| New cheques | generated by the section 2 rules; all Pending |
| Old agreement | status becomes *Renewed*; it and all of its cheques are preserved; **old Pending cheques stay Pending** (never auto-cleared or deleted) |
| Link | `renewed_from_id` on the new agreement; unique, so an agreement can be renewed once |
| Safeguards | only a stored-Active agreement; body must contain `confirm = true` and `expected_end_date` (stale/duplicate renewals → 409 `stale_renewal` / `already_renewed`); total must equal the new rent |

The dialog shows an old-vs-new table, the number of old Pending cheques that stay Pending, and the new schedule before the Owner
confirms. Renewal history (previous / this / next) is shown on every agreement.

## 5. Bank ledger integration (single source of truth)
There is **no second balance system.** Step 8's `public.app_cash_bank_ledger(from, to)` remains the only source; `app_balances`,
`app_branch_cash`, Cash & Banks and the Step 7 dashboard all sum from it. Migration 0014 replaces that function with a copy of the
0012 definition in which **only the cheque row changed** (it now carries the agreement's branch, a description
`Cheque <no> - <landlord>`, the user and the time of clearing).

| Case | Effect |
|---|---|
| Pending | nothing |
| Cleared ENBD / ADCB cheque | one ledger row: negative amount on that bank, dated the **cheque date** (the actual cleared date is stored separately in `cleared_on`) |
| Bounced | nothing (not a deduction) |
| Exactly once | the row is derived from `status = 'Cleared'`; a cheque cannot be cleared twice, cannot return to Pending and cannot be deleted, so a duplicate deduction is impossible by construction |
| Cheque dated before the tracking start | stored as Cleared but does not change balances (`affects_balance = false`, stated in the UI) |
| Cleared today, dated in the future | reduces the bank only from its cheque date (the future-dated balance includes it; today's does not) |
| Overdraft | the Step 8 no-overdraft policy applies: clearing is refused (422 `insufficient_funds`) if the bank would be negative on the cheque date or today |

## 6. Alerts (Owner only, on-screen only)
Calculated from real dates on every request, one alert per record and condition (`key = kind:record-id`), each with branch, landlord,
cheque number, amount, bank, due date and a link to the record (agreement → `/rentals/{id}`, cheque → `/pdc-cheques/{id}`).

| Kind | Condition | Severity |
|---|---|---|
| `rental_expired` | stored Active, end date before today | danger |
| `rental_ending` | ends in 0–30 days | warning |
| `rental_renewal_upcoming` | ends in 31–90 days | warning |
| `cheque_overdue` | Pending, date before today | danger |
| `cheque_due_7` | Pending, due in 0–7 days | danger |
| `cheque_due_30` | Pending, due in 8–30 days (so the two windows never overlap) | warning |
| `cheque_bounced` | Bounced and **not yet replaced** | danger |

Surfaces: `GET /rentals/alerts`, the notification bell (merged with the Step 9 compliance alerts) and the Owner Dashboard
*Needs attention* list (`rentals_ending_30`, `rentals_renewal_90`, `rentals_expired`, `cheques_bounced`, `pdc_overdue`, `pdc_due_7`,
`pdc_due_30`, each linking to the filtered screen).

## 7. API endpoints (all Owner only; FastAPI + Pydantic; every write in a transaction and audited; Dubai time)
| Method and path | Purpose |
|---|---|
| `GET /rentals/summary` | agreement cards + the cheque summary |
| `GET /rentals/alerts` | rental / PDC alert feed |
| `POST /rentals/schedule-preview` | generated schedule, nothing saved |
| `GET /rentals/upcoming-expiries?days=` | agreements ending soonest |
| `GET /rentals` | list: `q`, `branch_id`, `status`, `sort`, `desc`, `page`, `page_size` |
| `POST /rentals` | confirm the agreement and its reviewed schedule |
| `GET /rentals/{id}` | detail: agreement, schedule, renewal chain, history |
| `PUT /rentals/{id}` | update an active agreement |
| `GET /rentals/{id}/schedule` | linked cheques with totals and status counts |
| `GET /rentals/{id}/renewals` | renewal history chain |
| `POST /rentals/{id}/renewal-preview` | old-vs-new and the new schedule, nothing saved |
| `POST /rentals/{id}/renew` | confirmed renewal |
| `GET /pdc-cheques/summary` | the seven cards, unresolved bounced figures, next cheque |
| `GET /pdc-cheques` | list: `q`, `branch_id`, `bank`, `status`, `view`, `date_from`, `date_to`, `agreement_id`, `sort`, `desc`, paging |
| `GET /pdc-cheques/{id}` | cheque, agreement, history |
| `POST /pdc-cheques/{id}/clear` | `{cleared_date?, note?}` |
| `POST /pdc-cheques/{id}/bounce` | `{bounced_date?, reason}` |
| `POST /pdc-cheques/{id}/replace` | `{cheque_no, cheque_date?, bank?, notes?, reason}` |
| `PATCH /pdc-cheques/{id}` | edit a pending cheque (reason required) |

Errors use the standard envelope. Notable codes: `reason_required`, `duplicate_cheque`, `cheque_not_pending`, `cheque_not_bounced`,
`already_replaced`, `cheque_immutable`, `already_renewed`, `stale_renewal`, `not_renewable`, `agreement_closed`,
`confirmation_required`, `insufficient_funds`, `opening_not_configured`. The service-role key is never used by or exposed to the
frontend; the frontend talks to FastAPI only (Axios client + TanStack Query).

## 8. Database changes — migration `0014_rentals_pdc.sql` (additive; apply once, after 0013)
`rental_agreements`: `bank`, `cheque_count` (1–12), `first_cheque_date`, `first_cheque_no`, `notes` (≤1000); unique `renewed_from_id`.
`pdc_cheques`: `notes` (≤500), `cleared_on`, `bounced_on`, `bounced_at`, `cleared_by`, `bounced_by`, `replaces_id` (self FK, unique),
`client_key`; `cleared_on` backfilled from `cleared_at` (Dubai date); constraints `(status='Cleared') = (cleared_on is not null)`,
bounced-date consistency, no self replacement; unique `(bank, lower(btrim(cheque_no)))`. Functions: `app.pdc_before()` rewritten
(sets cleared/bounced stamps, refuses future dates), new `app.pdc_guard()` with triggers `pdc_guard` (update) and `pdc_no_delete`
(delete) — EXECUTE revoked from public roles — and `public.app_cash_bank_ledger` replaced as described in section 5.
No production data is modified except the `cleared_on` backfill of already-cleared rows. Existing audit triggers (0006) already cover
both tables. No new table and no RLS change (the Owner-only policies from 0005–0008 apply).

## 9. Permissions and audit
Owner only (`rentals_cheques`). Branch User: 403 on every endpoint, 401 anonymous, no rows through RLS, no menu entry, no route.
Audit rows (append-only): agreement INSERT/UPDATE, cheque INSERT, every Pending→Cleared / Pending→Bounced update with actor, time and
reason/note, replacement INSERT, renewal (new agreement INSERT + old agreement status UPDATE with the reason `Renewed: new agreement …`).
Denied attempts are logged as `ACCESS_DENIED`.

## 10. Unresolved / assumed decisions (not silently invented — please confirm)
| # | Decision taken for now | Why it needs confirmation |
|---|---|---|
| R1 | Regular cheque = rent ÷ n **rounded to a whole dirham (half up)**; last cheque takes the remainder | the brief says "rounded" without a precision or rule |
| R2 | `k` is **0-based** and offsets are `round_half_up(12k/n)`; dates are computed from the first date and clamped to the month end | indexing and month-end behaviour were open in BUSINESS_LOGIC |
| R3 | Cheque numbers need trailing digits; renewal continues after the highest number in the same prefix series; override allowed | numbering format is not defined |
| R4 | A cheque number is unique per bank across the system, bounced numbers are never reused | prevents duplicate/invalid cheques; stricter than the brief |
| R5 | **Cleared and Bounced are final** (BUSINESS_LOGIC said pending/bounced dates were editable). A bounced cheque is corrected by one linked replacement cheque of the same amount; standalone "add a cheque" exists only as a replacement | "never overwrite cleared/bounced records" and "total = rent" |
| R6 | Clearing is refused if the bank would go negative on the cheque date or today (Step 8 no-overdraft policy); the cleared date cannot precede the tracking start; a cheque dated before tracking start is stored but does not move balances | consistency with Step 8; owner may prefer to allow overdrafts |
| R7 | Displayed status is derived from dates; only stored-Active agreements are editable; rent / cheque count / bank are not editable after creation | keeps the schedule and the ledger consistent |
| R8 | One renewal per agreement; renewed first cheque date defaults to the new start date | the brief does not say when the first renewed cheque falls |
| R9 | Alert windows (ending 0–30 / renewal 31–90 / due 0–7 / due 8–30) and "bounced alert stops when replaced" | the brief lists the conditions but not the boundaries |
| R10 | *Terminated* exists as a status but no screen or endpoint sets it | early termination rules (refunds, remaining cheques) are undefined |
| R11 | Pending cheques left on a renewed agreement stay Pending and still appear in lists and alerts | the brief forbids auto-clearing/deleting; the Owner clears or bounces them |

## 11. Existing code changed (everything else is new)
`core/permissions` unchanged. Changed: `api/v1/router.py` (two routers), `repositories/report_repository.py`
(`AlertRepository.counts`: three added counts; `cheques_bounced` now means *unresolved* bounced; `pdc_due_7` now means 0–7 days —
overdue has its own count), `services/dashboard_service.py` (alert labels and links), `database/tests/test_database.py`
(`test_cleared_at_is_maintained` follows the new immutability rule), frontend `config/navigation.ts` (Rental Agreements live, PDC Cheques
added), `routes/index.tsx`, `components/layout/notification-menu.tsx` (merges the two alert feeds), tests `layout.test.tsx`
(placeholder stand-in is now `/tasks`) and `hr.test.tsx` (stubs the rentals alert endpoint; list label is "Alerts"), `e2e/run_e2e.py`.

## 12. Tests
Backend: `tests/test_step10_rentals_core.py` (calculations; no DB) and `tests/test_step10_rentals_api.py` (real app + PostgreSQL +
RLS) — creation/validation, end-date default, count, distribution, remainder, total = rent, month-end dates, number continuation,
duplicates, status transitions, exactly-once clearing, ENBD and ADCB, bounce without deduction, replacement, immutability (API and
direct SQL), renewal dates/schedule/history/one-renewal/stale/unconfirmed, alerts without duplicates, Step 7 dashboard and Step 8
Cash & Banks consistency, Owner-only on every endpoint, RLS, audit. Frontend: `src/test/rentals.test.tsx`. E2E scenarios
`STEP10 …` in `e2e/run_e2e.py`. Results are in the Step 10 completion report.
