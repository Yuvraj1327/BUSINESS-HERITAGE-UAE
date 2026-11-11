# Activity History

Owner-only view (`/activity-history`, API `GET /api/v1/reports/activity`) over the append-only `public.audit_log`.

## Where the entries come from
Row-level triggers (`app.audit_row_change`, migrations 0006, 0012, 0013, 0017) write one audit row per INSERT/UPDATE/DELETE
on the audited business tables. The actor is `auth.uid()`, taken from the verified JWT claims that the API sets on every
request session (`database/session.py`). The API never writes with a shared or service account, so actions made in the
app always carry the real signed-in user. Authorization failures are logged as `ACCESS_DENIED` through
`app.log_access_denied` (also the real user).

**The 11 initial entries** (10 `branches` INSERTs + 1 `profiles` INSERT) are the bootstrap, not business activity:
- 10 branches: the seed in `0009_seed_reference_data.sql`, run by the migration role. No signed-in user, so `actor_user_id` is NULL.
- 1 profile: the first Owner row inserted by an operator in the SQL editor (`OWNER_ACCOUNT_SETUP.md`, step A.3). Also NULL actor.

They are genuine, correct records and must stay; nothing was added, edited or deleted to produce this view.

## How the page presents them
| `actor_user_id` | Shown as | Source |
| --- | --- | --- |
| NULL, INSERT on `branches` / `profiles` | **System / Initial Setup** | System |
| NULL, anything else (e.g. an operator edit in the SQL editor) | System (no signed-in user) | System |
| a user with a profile | the user's full name | User |
| an id with no matching profile | Unknown user (never disguised as System) | User |

Filters: **All Activity / User Activity / System Activity** (API `source=user|system`, applies to the export too),
plus the existing date range, user, module, action and record-reference filters. The user filter is disabled while
System Activity is selected. Result table has a new **Source** column.

Limitation: "Initial Setup" is inferred (NULL actor + INSERT on branches/profiles); the audit log has no separate
"bootstrap" flag, and adding one would mean altering the trigger, which this change deliberately did not do.

## Append-only guarantee
Unchanged: triggers `audit_no_update_delete` / `audit_no_truncate` reject any UPDATE, DELETE or TRUNCATE on `audit_log`.
This change only reads; labelling happens at query/presentation time. No migration was added.

## Ensuring future actions have the right actor
- Every request session runs `SET LOCAL ROLE authenticated` + the caller's claims, so `auth.uid()` is always set for app writes.
- Owner-created Branch Users (`POST /users`) are audited as the creating Owner; `profiles.created_by` defaults to `auth.uid()`.
- Only operator tooling (SQL editor, `scripts/provision_account.py`, migrations) produces NULL-actor rows; they show as System.
- Tables with audit triggers cover reports, expenses, suppliers and their ledgers, cash transfers, POS settlements,
  opening balances, employees, trade licences, rentals, PDC cheques, tasks, customers, orders, order payments,
  branches and profiles.

## Tests
- `backend/tests/test_activity_actor_label.py` (pure): labelling rules.
- `backend/tests/test_step12_reports_api.py::test_activity_source_filter_and_system_label` (needs PostgreSQL): user + system = all, labels, invalid source rejected.
- `frontend/src/test/analytics.test.tsx`: All/User/System buttons send the right `source` parameter.
