# BRANCH_ISOLATION

A Branch User must never see or change another branch's data. This is enforced in the database first and again in the API; the UI only hides things.

## Rule
Owner: all ten branches. Branch User: only `profiles.branch_id` (set by the Owner, never by the user). Anonymous, inactive and profile-less users: no branch.

## Database (authoritative)
- `app.branch_id()` / `app.is_owner()` / `app.can_access_branch(uuid)` (SECURITY DEFINER, pinned `search_path`, active profiles only, derived from `auth.uid()`).
- Policies: `branches_select` (own branch), `dr_select` (own-branch reports), `dr_insert_branch` (own branch **and** `created_by = auth.uid()`), `profiles_select` (own row). Branch users have no policy on any other table.
- Daily reports: SELECT and INSERT grants only. No UPDATE or DELETE grant exists for anyone; owner corrections go through the audited `void_daily_report()` function.
- `v_daily_reports_reconciled` is `security_invoker`, so it inherits these policies.

## API (`backend/app/api/authz.py`)
`BranchScope` is built from the trusted Principal and the module's grant:
- `scope.resolve(requested)` – Owner: the requested branch or "all". Branch user: always their own branch; a **different** requested id raises 403 `branch_access_denied`; a branch user without a branch can never widen to "all".
- `scope.ensure(branch_id)` – for ids from bodies or from loaded rows.
- `scope.apply(stmt, column, requested)` – adds `WHERE branch_id = …` to a SQLAlchemy query.
- `require_branch_access(...)` – dependency that checks a `{branch_id}` path/query parameter before the handler runs.

Where a branch id can arrive, and what happens:
| Channel | Result for a Branch User asking for another branch |
|---|---|
| path `/branches/{id}` | 403 `branch_access_denied` (before the handler) |
| query `?branch_id=` | 403 `branch_access_denied` |
| request body `branch_id` | 403 via `scope.ensure` |
| direct record id of another branch's row | RLS hides the row → 404, identical to a non-existent id |
| nonexistent branch id | 403 (same as "other branch": ids cannot be probed) |
| `X-Branch-Id` / `X-Role` headers, token metadata | ignored |

Every denial of a signed-in user is written to the audit log (`ACCESS_DENIED`, with the module, action and requested branch id; never tokens).

## Rules for future module code (Steps 7–11)
1. Declare the module/action with `require_permission` or `get_branch_scope` on every route. No dependency = no protection, so review for it.
2. Never accept `branch_id` for a Branch User as authority: use `scope.resolve(...)`, and for INSERTs set `branch_id = principal.branch_id` server-side.
3. Load by id **through the user-context session** (so RLS applies) and still call `scope.ensure(row.branch_id)`.
4. Do not use the service-role key or a bypass role to serve requests.
5. Add tests in the style of `backend/tests/test_rbac_api.py` (own branch, other branch by path/query/body/record id, owner).

## What is tested
`backend/tests/test_rbac_api.py` (API + RLS through the real `app_api` connection), `backend/tests/test_permission_matrix.py` (`BranchScope` unit tests), `database/tests/test_rbac.py` (database level). See `RBAC_TEST_RESULTS.md`.
