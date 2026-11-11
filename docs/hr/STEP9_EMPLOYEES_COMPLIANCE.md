# Step 9 — Employees, Salaries, Leave, Visas & Passports, Trade Licenses

Scope: Employee Management (with salary information and the monthly payroll figure), Leave Management and the six-month rule,
Visas & Passports expiry tracking, Trade Licenses with renewal history, and the related alerts.
**Not built** (later steps): Rental Agreements, PDC Cheques, Task Management, and any unrelated finance workflow.
Steps 1–8 are preserved; the only existing code touched is listed in section 9.

> Verification status: verified against a real PostgreSQL 16 with RLS, the real FastAPI app and the real React app.
> **Supabase Auth was simulated** (`e2e/fake_gotrue.py`). A real Supabase project was never available, so email delivery,
> dashboard settings and key handling on a real project are untested. Nothing here claims otherwise.

## 1. Employee management (Owner only)
Fields stored: name, assigned branch, job role, monthly salary, passport expiry, visa expiry, status, leave start, notes, visa
cancelled flag and date, created/updated timestamps and user. **No passport number or Emirates ID number is collected or stored**
(no such column exists; the API rejects unknown fields; a database test asserts it).

| Capability | How |
|---|---|
| Add / view / update | `POST /employees`, `GET /employees/{id}`, `PUT /employees/{id}` |
| Search, filter, sort, paginate | name search; branch and status filters; sort by name, branch, role, salary, status, created; 25 per page |
| Change status | `POST /employees/{id}/status` (On Leave / Active / Visa Cancelled) with confirmation dialog and a mandatory reason |
| Assign or change branch | through update; needs a reason; kept in history |
| History | every change is in the append-only `audit_log` (old and new values, user, time, reason); shown as readable lines, never raw JSON |
| Removal | **no hard delete**. Employees are archived with a reason (`POST /employees/{id}/archive`) and disappear from lists, payroll and alerts |

Summary cards (`GET /employees/summary`): Total Active Employees, Currently on Leave, Close to Six-Month Limit (limit within 30 days),
Visa Cancelled, Monthly Payroll Total.

**Monthly Payroll Total** = sum of the *current* salaries of employees who are stored *Active*, not (effectively) visa-cancelled and
not archived. It is a calculation from current records and is **not proof of payment** (the card says so). Employees on leave are
excluded (decision D6, section 8).

## 2. Status model
The approved schema (migration 0005) stores `status` ∈ {Active, Leave} plus a `visa_cancelled` flag; it was **not** rewritten. The API
derives the displayed status from dates:

| Displayed status | Rule |
|---|---|
| Visa Cancelled | `visa_cancelled` flag set, **or** stored Leave and today (Dubai) is after `leave_start` + 6 calendar months |
| On Leave | stored Leave (and not cancelled) |
| Active | otherwise |

The stored status is also returned (`stored_status`) so the difference is visible. Statuses are never typed by a user.

## 3. Leave and the six-month rule
* **Six calendar months, never 180 days.** `leave_limit_date = leave_start + 6 calendar months`, clamped to the last day of a shorter
  month (31 Aug + 6 months = 28 Feb, or 29 Feb in a leap year). SQL (`date + interval '6 months'`) and Python give identical results;
  a test compares them for month-end and leap-day starts.
* **Boundary.** The limit date is the **last allowed day**. Remaining days = limit date − today.

| Remaining days | Leave state | Indicator |
|---|---|---|
| > 30 | on_leave | On Leave |
| 1 – 30 | approaching_limit | Approaching Six-Month Limit |
| 0 | limit_reached | Six-Month Limit Reached |
| < 0 | visa_cancelled | Visa Cancelled |

* **On Leave requires a leave start date**, which may not be in the future (Dubai date). The database also enforces
  `(status = 'Leave') = (leave_start is not null)`.
* **Screen** shows leave start, current duration (days), limit date, days remaining and the leave status.
* **Return to work** (`POST /employees/{id}/return`, optional return date, reason required):
  * on or before the limit date → Active, leave cleared, visa kept;
  * after the limit date → Active, `visa_cancelled = true`, `visa_cancelled_date` = the limit date. **Permanent.**
* A cancelled visa cannot be reinstated, put on leave again, or have its expiry edited (409/422). There is no undo endpoint.
* `PATCH /employees/{id}/leave` corrects a wrongly typed leave start (reason required, future dates refused).
* **Traceability:** leave starts, returns and corrections are employee UPDATEs, so each is in `audit_log` with who, when and why.
  No separate leave table is needed.

## 4. Visas & Passports
Dedicated screen with separate Visa and Passport sections: employee, branch, expiry date, status, days remaining, employment status.
Statuses are calculated from the real dates in Dubai time on every request.

| | Red (danger) | Amber (warning) | Normal |
|---|---|---|---|
| Visa | expired, or ≤ 30 days | ≤ 90 days | > 90 days |
| Passport | expired, or ≤ 30 days | ≤ 180 days | > 180 days |

API status names: `expired`, `urgent` (0–30 days), `upcoming` (amber range), `normal`, `not_recorded`, `cancelled` (visas only).
Colour is always paired with a word and day count. Summary cards: visas expired / ≤30 / 31–90 / cancelled; passports expired / ≤30 /
under 6 months (≤180 days) / not recorded. Lists filter by branch and expiry period, search by name, and sort by nearest or latest expiry.
Expiry updates (`PATCH /visas-passports/employees/{id}/visa-expiry|passport-expiry`) store only a date; old and new dates are kept
(`GET /visas-passports/employees/{id}/history`, derived from the audit log). Branch Users get 403 on every endpoint and the pages
never request the data for them.

## 5. Trade licenses
Fields: branch, license number, issuing authority, expiry date, renewal fee, notes. Add, view, update, list (search by branch, number or
authority; filter by branch and expiry status; sort by expiry, branch, number or fee), renewal history, archive (no hard delete).

* **Status** from the expiry date: expired (< today), urgent (≤ 30 days, red), upcoming (31–90 days, amber), normal. The licence colour
  thresholds are *not approved* — see D26.
* **Mark renewed** (`POST /trade-licenses/{id}/renew`): new expiry = **previous expiry + 1 year** (29 Feb → 28 Feb), even when the
  licence had already expired. It writes an immutable `license_renewals` row (renewal date, user, previous expiry, new expiry, fee, note),
  updates the licence expiry and audit-logs the change, all in one transaction. The previous expiry is preserved in the history.
* **No accidental repeat.** The request carries `expected_expiry` (what the Owner saw and confirmed). If the licence has already moved on,
  the server answers 409 `stale_renewal`. The dialog also sends a one-time `client_key`; a replay gets 409 `duplicate_transaction`. The
  licence row is locked during the renewal, so two simultaneous clicks cannot both succeed. The UI shows old → new expiry in a
  confirmation dialog and disables the button while saving.
* **Fee.** Defaults to the licence's renewal fee; the Owner can override it for that renewal.
* **Summary cards** (`GET /trade-licenses/summary`): Total, Expired, Expiring ≤ 30 days, Expiring ≤ 60 days, Renewal Fees Due.
  **Renewal Fees Due** = sum of `renewal_fee` for non-archived licences that are expired or expire within 90 days (approved rule).

## 6. Alerts and attention items
`GET /compliance/alerts` returns one alert per **record and condition**, calculated from the real records on each request (nothing is
stored, so nothing can go stale or be duplicated). Each has a stable `key` (`kind:record-id`), severity, title, due date, days remaining
and an in-app link to the employee or licence.

| Kind | Condition | Severity |
|---|---|---|
| visa_expired | visa expiry < today (not cancelled) | danger |
| visa_expiring | visa expires within 0–30 days | danger |
| passport_expired / passport_expiring | passport expiry < today / within 0–30 days | danger |
| leave_limit_approaching | six-month limit within 0–30 days | warning |
| visa_cancelled_by_leave | limit passed, visa not yet recorded as cancelled | danger |
| license_expired / license_expiring | licence expired / within 0–30 days | danger |
| license_renewal_due | licence expires in 31–90 days | warning |

Archived records and cancelled visas produce no expiry alerts. Surfaces: the notification bell (count badge, list, links; Owner only,
Branch Users never call the endpoint), and the existing Step 7 Needs Attention list on the dashboard, whose aggregate counts now ignore
archived records, add "licence renewals due in 31–90 days" and link to the relevant page. **No WhatsApp, SMS or email is sent.**

## 7. API (all under `/api/v1`, JWT required, Owner only)
| Method and path | Purpose |
|---|---|
| GET `/employees/summary` | summary cards and payroll total |
| GET `/employees/leave/summary` | leave counts and watch list (approaching, reached, passed) |
| GET `/employees` | list: `q`, `branch_id`, `status`, `include_archived`, `sort`, `desc`, `page`, `page_size` |
| POST `/employees` | create |
| GET `/employees/{id}` | detail plus change history |
| PUT `/employees/{id}` | update (reason required when salary, branch, visa or passport expiry change) |
| POST `/employees/{id}/status` | start leave / return / cancel visa (reason required) |
| POST `/employees/{id}/return` | return to work |
| PATCH `/employees/{id}/leave` | correct leave start |
| POST `/employees/{id}/archive` | archive (204) |
| GET `/visas-passports/summary`, `/visas`, `/passports` | expiry summary and lists (`q`, `branch_id`, `bucket`, `sort`, `desc`, paging) |
| PATCH `/visas-passports/employees/{id}/visa-expiry`, `/passport-expiry` | update an expiry date |
| GET `/visas-passports/employees/{id}/history` | expiry change history |
| GET `/trade-licenses/summary`, GET/POST `/trade-licenses`, GET/PUT `/trade-licenses/{id}` | summary, list (`q`, `branch_id`, `status`, `sort`, paging), create, detail (renewals + history), update |
| POST `/trade-licenses/{id}/renew` | mark renewed |
| GET `/trade-licenses/{id}/renewals` | renewal history |
| POST `/trade-licenses/{id}/archive` | archive (204) |
| GET `/compliance/alerts` | alert feed |

Pydantic validation rejects unknown fields, negative salaries/fees, blank names and numbers, unrealistic dates (outside 2000–2100) and
reasons shorter than 3 characters. Money is `Decimal`, sent as 2-place strings. All writes are single transactions; business dates use
`Asia/Dubai`. Errors use the standard envelope (`reason_required`, `leave_start_required`, `not_on_leave`, `visa_cancelled`,
`visa_already_cancelled`, `employee_archived`, `stale_renewal`, `duplicate_transaction`, `duplicate_license`, `license_archived`).

## 8. Unresolved decisions (recorded, not silently invented)
| # | Decision made so the step could be built | Needs the Owner's confirmation |
|---|---|---|
| D8 | The visa cancellation flag is **persisted when the employee returns after the limit**; before that it is derived from dates on every request (no scheduled job). A visa whose limit passed while the employee never returned shows Visa Cancelled but the flag stays unset until a return or a manual cancellation. | Persist by job instead? |
| D9 | Leave history and licence-renewal history are kept (leave via `audit_log`, renewals in `license_renewals`). | Confirmed by the Step 9 brief for licences; leave history assumed |
| D24 | Limit boundary: the limit date is the last allowed day; cancelled from the next day; "Limit Reached" = 0 days remaining; "Approaching" = 1–30. | Confirm the day count |
| D25 | Visa cancellation is **permanent with no undo** in the application. A wrong manual cancellation needs a database correction. | Add a restricted "reinstate" action? |
| D6 | Payroll counts only Active, non-cancelled, non-archived employees; **leave is unpaid**. | Is any leave paid? |
| D26 | Licence colour thresholds (red ≤ 30 days or expired, amber ≤ 90) mirror the visa ones; they were not approved. "Fees due" uses the approved 90-day window and includes already-expired licences. | Confirm thresholds |
| D27 | Licence numbers are unique among non-archived licences (case and spacing ignored). | Can two licences share a number? |
| D28 | Renewing does **not** post an expense; the Owner records the payment under Expenses. | Auto-post to the ledger? |
| D29 | Renewal adds one year to the *old* expiry (not to today), so renewing a licence that lapsed long ago can still leave it expired. | Confirm |
| D30 | Employee data corrections: sensitive edits require a reason; employees and licences are archived, never deleted. | Confirm retention |
| D31 | Alert definitions per condition (table in section 6), and `visa_expiring` covers 0–30 days only (expired is a separate alert). | Confirm wording and ranges |

## 9. Database changes — `database/migrations/0013_employee_compliance.sql`
Apply once, after 0012. Additive; no data rewritten.
* `employees`: + `notes` (≤ 1000), `visa_cancelled_date` (only with the flag), `archived_at`, `archived_by`, `archive_reason` (set together); index on active employees per branch.
* `trade_licenses`: + `notes`, `archived_at`, `archived_by`, `archive_reason`; unique index on `lower(btrim(license_no))` for non-archived rows.
* New table `license_renewals`: license FK, `renewed_on` (default Dubai today, never in the future), `previous_expiry`, `new_expiry` (> previous), `renewal_fee` (≥ 0), `note`, `client_key` (unique when present), created at/by. Immutable (guard trigger blocks UPDATE and DELETE), audit-logged, Owner-only RLS, select/insert grants only.
* Existing audit triggers, owner-only RLS and no-DELETE grants on `employees` and `trade_licenses` (migration 0006) are unchanged.

Existing code changed: `core/calculations.py` (added functions), `repositories/report_repository.py` and `services/dashboard_service.py`
(alert counts ignore archived rows, one new count, `href` on alerts), `schemas/dashboard.ts`, the notification menu, three navigation
entries (placeholder → live), routes, and three layout tests that used the Employees placeholder as a stand-in.

## 10. Permissions and audit
Owner holds EMPLOYEES (read, create, update, export), VISAS_PASSPORTS (read, update, export) and TRADE_LICENSES (read, create, update,
export); the Branch User holds none (default deny). The server returns 403 plus an `ACCESS_DENIED` audit row for a Branch User, 401
without a token; RLS on `employees`, `trade_licenses` and `license_renewals` is a second, independent layer (tested as the
restricted `authenticated` role). The frontend hides the menu and shows Access denied without calling the API. The service-role key
is not used by any of this code and is not in the frontend. Every create/update/archive/renewal is recorded in `audit_log` with the
acting user and reason.

## 11. Tests
* Backend `tests/test_step9_hr_api.py` (35 tests, own disposable database): calendar months, month-end and leap year, boundaries,
  thresholds, SQL/Python agreement, employee create/update/validation, no identity-number columns, status rules, leave correction,
  return before / on / after the limit, permanent cancellation, payroll and summary cards, list filters, archive, audit trail,
  visa/passport buckets and history, licence status, summary and fees due, renewal (+1 year, history preserved, immutability,
  stale and replayed requests, leap day, long-expired), alerts (no duplicates, links, archived excluded), Owner-only on every
  endpoint, anonymous 401, RLS, dashboard consistency.
* Frontend `src/test/hr.test.tsx`: helpers and form schemas, summary cards, lists and filters, forms and confirmations, leave and
  permanent-cancellation warnings, expiry update, renewal confirmation, stale-renewal error, alerts in the bell, Branch User denial.
* E2E (`run_step9_scenarios`): real API rows and the real browser, including permissions and layout at 390, 768 and 1440 px.
