# Step 11 — Task Management, Notifications & Alerts

Scope: Task Management, task status / overdue tracking, the centralized Alerts (Notification Center) and the Owner Dashboard alert
integration. **Not built**: Reports & Analytics, customer orders, any WhatsApp / SMS / email delivery. Steps 1–10 are preserved; the
existing code touched is listed in section 11.

> Verification status: verified against a real PostgreSQL 16 with RLS, the real FastAPI app and the real React app.
> **Supabase Auth was simulated** (`e2e/fake_gotrue.py`). A real Supabase project was never available, so nothing here claims
> behaviour on a real project.
> **No scheduler is configured or tested.** Alerts are calculated **on demand** (section 6). Nothing is sent outside the app.

## 1. Task management (Owner only)
Permission module `tasks`: the Owner holds read / create / update / export; the Branch User holds **nothing** (decision D11 stays
open, section 10). Every task endpoint answers 403 to a Branch User (with an `ACCESS_DENIED` audit row), 401 to anonymous callers;
the menu entry and the pages are hidden, and RLS blocks the table for non-Owners as well.

| Field | Rule |
|---|---|
| Title | required, 200 characters |
| Description / Notes | optional, 2000 characters each |
| Branch | one active branch, or **All Branches** (`branch_id` null) |
| Due date | optional date |
| Assigned to | optional active user. **New tasks start Unassigned** (the approved prototype behaviour) |
| Status | `To Do` / `In Progress` / `Done` |
| Created by / Created date | stamped by the database from the signed-in user; not settable through the API |
| Completion date / completed by | stamped by the database trigger when the status becomes Done; cleared when the task is reopened; kept on Done → Done |
| Priority | **not built**: not part of the approved requirements (section 10, T2) |

Features: create, detail, edit (title, description, branch, due date, assignee, notes; optional reason), change status (any state to
any other state; the same state again is refused with 409 `status_unchanged`), "Mark completed", full change history (from the
append-only audit log: who, when, what changed, reason), search (title and description), filters (branch / All Branches only, status,
assignee / unassigned, due date range, quick views), sort (due date, created, title, status; ascending or descending), pagination.
Tasks cannot be deleted (T5).

Summary cards (`GET /tasks/summary`): Total, To Do, In Progress, Completed, Overdue, Due Today, Due Within 7 Days.

## 2. Task permission matrix
| Action | Owner | Branch User |
|---|---|---|
| View list / detail / history / summary | Yes | No (403) |
| Create (branch or All Branches) | Yes | No |
| Edit, assign, reassign | Yes | No |
| Change status, mark completed | Yes | No |
| See tasks of other branches | Yes (all) | No (nothing at all) |

Branch ownership and the assignee can only be set through `PUT /tasks/{id}` by a user holding `tasks:update`; a Branch User has no
grant, so the API cannot be used to move, assign or create tasks. Nothing undocumented was granted. Whether a Branch User should see
or update tasks assigned to them is **unresolved** (D11 / D22) and is recorded in section 10 (T1).

## 3. Overdue logic
A task is **overdue** when its due date is before today's date in **Asia/Dubai** and its status is **not Done**. A Done task is never
overdue. A task without a due date is never overdue. Timing values (calculated by the server, never by the browser):
`overdue` (days_to_due < 0), `due_today` (0), `upcoming` (> 0), `no_due_date`, `completed`. The list shows the word and colour:
Overdue / Due Today / Upcoming / Completed. "Due within 7 days" is today up to today + 7 days and **includes today** (T6).
The same definition is used by the task summary, the task list views, the Alerts, and the Step 7 Owner Dashboard counts.

## 4. Alert types and severity
Alerts are **not a second alert system**. The conditions are still owned by the modules that existed before (Step 7 missing
reports, Step 9 compliance, Step 10 rentals and PDC); this step adds supplier dues and tasks, applies one severity scale, and keeps one
row per occurrence so it can be read / acknowledged and kept in history. No new compliance or financial threshold was invented.

| Module | Kind | Condition (unchanged from the owning module) | Severity |
|---|---|---|---|
| Daily Reports | `report_missing` | days this month (to today) without a daily report, one alert per branch (Step 7 definition and reporting start) | Warning |
| Visas & Passports | `visa_expired`, `visa_expiring` (≤ 30 days), `passport_expired`, `passport_expiring` (≤ 30 days) | Step 9 | expired and expiring: Critical (Step 9 "danger") |
| Employees | `leave_limit_approaching` (≤ 30 days to the six-month limit), `visa_cancelled_by_leave` | Step 9 six-month rule | approaching: Warning; cancelled: Critical |
| Trade Licenses | `license_expired`, `license_expiring` (≤ 30 days), `license_renewal_due` (31–90 days) | Step 9 | expired and ≤ 30 days: Critical; renewal approaching: Warning |
| Rental Agreements | `rental_expired`, `rental_ending` (≤ 30 days), `rental_renewal_upcoming` (31–90 days) | Step 10 | per Step 10 mapping (danger → Critical, warning → Warning) |
| PDC Cheques | `cheque_overdue`, `cheque_due_7`, `cheque_due_30`, `cheque_bounced` | Step 10 | overdue and bounced: Critical; due soon: Warning |
| Suppliers | `supplier_dues` | an active supplier with an outstanding balance > 0 (`v_supplier_outstanding`) | Informational |
| Tasks | `task_overdue`, `task_due_today` | open task past due / due today | Warning |
| Tasks | `task_due_7` | open task due in 1–7 days | Informational |

Mapping from the existing scales: Step 9 / 10 `danger` → **Critical**, `warning` → **Warning**, `info` → **Informational**. The Owner
Dashboard "Needs attention" list is unchanged and now also shows `tasks_due_today` and `tasks_due_7`; its existing KPIs and every
financial calculation are untouched.

Each alert carries: Alert ID, type, title, description (detail), related module, related record id, branch, alert date (the Dubai
date it was first seen), due date, severity, current status, and a link to the related record.

## 5. Alert states and history
`unread` → `read` → `acknowledged`, or `resolved` (the underlying issue no longer exists). Rules:
- **Read** and **Acknowledged** are recorded with the user and time. Acknowledging also marks it read.
- Active list = not acknowledged and not resolved, most important first (Critical, Warning, Informational, then soonest due date).
- **History** = acknowledged or resolved alerts. History is never deleted (no delete grant on the table).
- An acknowledged alert is **not** re-created while the condition persists; when the condition is fixed it becomes resolved.
- A resolved alert cannot be read or acknowledged (409 `alert_resolved`).
- If a condition later returns (for example a cheque overdue again) it is a new occurrence and a new alert.
- Only the Owner can read the feed or change a state (module `alerts`: Owner read / update; Branch User nothing).

## 6. Generation and refresh behaviour
- **On demand, no scheduler.** Every read of the alerts API (`/alerts`, `/alerts/history`, `/alerts/summary`, `/alerts/unread-count`) first runs a synchronisation: it collects the current conditions from the real records, **inserts**
  conditions not yet stored, **updates** stored ones whose text / severity / due date changed, and **resolves** stored ones that no
  longer exist. `POST /alerts/refresh` does the same on request. It writes only when something changed.
- **No duplicates**: a partial unique index on the open alert key (`kind:record id`) plus an advisory lock around the synchronisation
  means repeated requests, concurrent requests and dashboard refreshes cannot create a second row for the same record and condition.
- The web app re-reads the summary every two minutes while open and after any task change; the bell, the Notification Center and the
  Owner Dashboard widget use the same `/alerts/summary` response, so their numbers always agree.
- **Scheduling requirement**: because time moves a condition without any edit (a cheque becomes overdue at midnight Dubai time),
  alerts are only as fresh as the last time the Owner opened the app. A scheduler calling `POST /alerts/refresh` with an Owner token
  (or a service-side job) would be needed for alerts that must exist while nobody is signed in. **None is configured, so no claim is
  made that scheduled notifications work.** External delivery (WhatsApp, SMS, email) is not built and not approved for this phase.

## 7. API endpoints (all under `/api/v1`, JWT required)
| Method and path | Purpose | Access |
|---|---|---|
| `GET /tasks` | list: `q`, `branch_id`, `all_branches`, `status`, `assignee_id`, `unassigned`, `due_from`, `due_to`, `view` (overdue / today / week / upcoming / open / completed), `sort` (due / created / title / status), `desc`, `page`, `page_size` | Owner |
| `GET /tasks/summary` | dashboard cards | Owner |
| `GET /tasks/overdue`, `GET /tasks/upcoming` | overdue; due today .. 7 days | Owner |
| `GET /tasks/assignees` | active users a task can be assigned to | Owner |
| `POST /tasks` | create | Owner |
| `GET /tasks/{id}`, `GET /tasks/{id}/history` | detail with change history | Owner |
| `PUT /tasks/{id}` | edit, branch, assign / reassign | Owner |
| `POST /tasks/{id}/status` | change status / mark completed | Owner |
| `GET /alerts` | active alerts (filters `q`, `kind`, `severity`, `branch_id`, `module`, `status` unread / read; paging) | Owner |
| `GET /alerts/history` | acknowledged and resolved alerts (`status` acknowledged / resolved) | Owner |
| `GET /alerts/summary` | Total Active, Critical, Warning, Informational, unread, acknowledged, recent (top 5), per-module counts | Owner |
| `GET /alerts/unread-count`, `GET /alerts/facets` | bell count; filter options | Owner |
| `POST /alerts/{id}/read`, `/acknowledge` | state change | Owner |
| `POST /alerts/read-all`, `POST /alerts/refresh` | mark all read; recalculate now | Owner |

Errors use the standard envelope (401 not signed in, 403 no grant, 404, 409, 422). No service-role key is used or exposed.

## 8. Database changes (migration `0015_tasks_alerts.sql`, additive, apply once after 0014)
- `tasks`: new columns `description`, `notes`, `completed_at`, `completed_by`; Done rows backfilled with `completed_at = updated_at`;
  constraint "Done if and only if completed_at is set"; indexes on branch and assignee; trigger `app.tasks_before()` stamps / clears
  the completion fields and requires the assignee to be an active user.
- New table `public.alerts` (key, kind, module, severity, title, detail, record id, branch, due date, link, first / last seen,
  resolved, read / acknowledged by and at), unique partial index on the open key, RLS: Owner only, grants select / insert / update
  (no delete). The alerts table is deliberately **not** audited row by row (synchronisation would flood the audit log); read and
  acknowledge are recorded on the row itself (who and when).
- Tasks remain audited by the existing append-only audit trigger.

## 9. Tests (this step)
Backend: 22 API tests (task rules, permissions, overdue, history, audit; every alert kind that has data; duplicate prevention;
read / acknowledge; resolution after the underlying record is fixed; filters; dashboard consistency; Owner-only) + 7 unit tests of
the timing rule. Frontend: 13 tests (tasks page, create, detail, status, notification bell, centre, history, error state, Branch
User). End to end (simulated Auth): API access control, overdue → one alert → completed → resolved, UI flows at 390 / 768 / 1440 px.

## 10. Unresolved decisions (recorded, not invented)
| # | Question | Current behaviour |
|---|---|---|
| T1 | D11 / D22: may a Branch User see or update tasks assigned to them, or their branch's tasks? | **No.** Owner only. Needs the Owner's decision before any Branch User task access is added |
| T2 | Priority field | Not built (not in the approved requirements) |
| T3 | Who may be an assignee | Any active user, including Branch Users. Assigning a task does not give that user access to it (T1) |
| T4 | "Supplier dues requiring attention" has no approved rule | Every supplier with an outstanding balance is one Informational alert. No overdue / amount threshold was invented |
| T5 | Delete / archive tasks | Not provided. Tasks are closed with Done |
| T6 | "Due within 7 days" | Includes today; the dashboard's `tasks_due_7` counts days 1–7 and `tasks_due_today` counts today separately |
| T7 | Missing report window | Month to date up to today, one alert per branch, using the Step 7 definition and reporting start |
| T8 | Acknowledging an alert | Removes it from the active list and the bell; it does not change the underlying Needs Attention counts, which always reflect the real records |
| T9 | Scheduled generation | No scheduler (section 6); freshness depends on the app being used |
| T10 | Export of tasks | The matrix lists export for the Owner; no export is built in this step |

## 11. Existing code touched
`core/permissions.py` (new `alerts` module), `schemas/hr.py` + `services/compliance_service.py` (additive `branch_name` / `record_id`
on the compliance alert), `repositories/report_repository.py` and `services/dashboard_service.py` (two additive Needs Attention
counts and links), `api/v1/router.py`, `config/navigation.ts` (Tasks live, Notifications), `routes/index.tsx`,
`components/layout/notification-menu.tsx` (now reads the central feed), `pages/dashboard/OwnerDashboard.tsx` (Alerts widget), tests
that stubbed the two old bell feeds, `test_permission_matrix.py`, `database/tests/test_database.py`, `e2e/run_e2e.py`.
