# RLS_VERIFICATION

Review of the Step 2 policies (`0008_rls_and_grants.sql`) against the Step 5 requirements, plus the corrective migration `0010_rbac_hardening.sql`. Verified by running `database/tests/test_rbac.py` and the Step 2 suite on a fresh PostgreSQL 16 with all migrations. **Not verified on a real Supabase project.**

## Findings
| Requirement | Step 2 state | Result |
|---|---|---|
| RLS enabled on every table | all 14 tables | ✔ (test: no table without RLS) |
| Anonymous access | no grants/policies for `anon`; helper functions not executable by `anon` | ✔ tested |
| Owner: all branches/tables | owner policies on all tables | ✔ |
| Branch user: own profile | `profiles_select` own row | ✔ |
| Branch user: own branch + lookups | `branches_select` own branch; `expense_categories` any active user | ✔ |
| Branch user: own-branch reports read/insert only | `dr_select`, `dr_insert_branch`; grants SELECT, INSERT only | ✔ |
| No update/delete of submitted reports | no grant, no policy, for anyone | ✔ tested for Branch User and Owner |
| No owner-only financial/employee data | owner-only policies on 9 tables | ✔ every policy on those tables contains `is_owner()`; behaviour tested on suppliers, employees, tasks |
| Owner-only functions | `app_balances`, `missing_report_count`, `void_*`, rental functions check `is_owner()` | ✔ tested for `void_daily_report`, `app_balances`, `missing_report_count` |
| Inactive accounts | helpers filter `is_active` → no role, no branch, no data | ✔ tested (branch and owner) |
| Recursion | helpers are SECURITY DEFINER with fixed `search_path`, read `profiles` bypassing its RLS | ✔ no recursion in any test |
| No self role change (branch user) | no UPDATE policy for non-owners (0 rows) | ✔ tested role, branch, active |
| **No self role/branch/status change by an owner** | **gap**: an owner could edit their own row (only the last-owner guard limited it) | **fixed in 0010** (`profiles_guard_self_change`) |
| **`user_id` immutable** | gap | **fixed in 0010** |
| **Failed-access audit** | `audit_log` only accepted INSERT/UPDATE/DELETE written by triggers | **extended in 0010**: action `ACCESS_DENIED`, written only by `app.log_access_denied()` |
| Single definition of branch access | implicit in policies | **added** `app.can_access_branch(uuid)` (used by tests; available to future policies) |
| Audit immutability | append-only trigger, no write grants | ✔ tested (users and superuser cannot update/delete) |

Intentional behaviour worth knowing: a user whose profile is **inactive can still read their own profile row** (policy `user_id = auth.uid()`), which is what lets the app say "Account inactive" instead of a generic failure. They get nothing else.

## Migration 0010 (additive; no policy removed, RLS stays enabled)
1. `audit_log.audit_action_chk` now allows `'ACCESS_DENIED'`.
2. `app.log_access_denied(module, action, detail)` – SECURITY DEFINER; actor is `auth.uid()` (not a parameter); records only existing profiles (no anonymous spam); truncates fields; drops oversized detail; stores at most 30 events per actor per minute; executable by `authenticated` only (not `anon`/`public`).
3. `app.guard_profile_self_change()` trigger on `profiles` – nobody may change their own `role`, `branch_id` or `is_active` when acting as an authenticated user (`auth.uid()` set), and `user_id` can never change. Operator sessions (SQL editor, provisioning script: no `auth.uid()`) are unaffected, as are the existing last-owner guard and RLS owner-only writes.
4. `app.can_access_branch(uuid)` – true for an active owner or an active branch user on that branch; false for null, inactive, anonymous.

Apply to each Supabase project after 0001–0009: paste into the SQL editor or follow `docs/database/MIGRATION_GUIDE.md`. It is not re-runnable (the constraint is dropped and recreated), so apply once.

## Audit coverage
| Event | Recorded by | Contents |
|---|---|---|
| Role change, branch reassignment, activation/deactivation, profile creation | `profiles_audit` trigger | actor, old/new values, optional reason (`set_config('app.audit_reason', …, true)`) |
| Failed privileged access (signed-in users) | `app.log_access_denied` from the API | actor, module, action, requested branch id; no tokens, passwords, secrets |
| Attempts by anonymous users or invalid tokens | **application logs only** (no actor to attribute) | |
| Permission matrix changes | version control | code change, not runtime |
Ordinary users cannot read the audit log (only the Owner can) or write it directly.

## How to re-verify
```bash
cd database/tests && pip install -r requirements-test.txt
TEST_PG_ADMIN_DSN="host=… user=postgres dbname=postgres" python -m pytest     # 152 tests incl. test_rbac.py
```
On a real project, also run in the SQL editor: `select tablename from pg_tables where schemaname='public' and not rowsecurity;` (must return no rows) and `select * from pg_policies where roles @> '{anon}';` (must return none).
