# RBAC_TEST_RESULTS

**Executed in this build; no real Supabase project was available.** API/database tests run against a real PostgreSQL 16 with migrations 0001–0010, connecting as the restricted `app_api` role (like production). Tokens are signed with locally generated keys; the Supabase Auth server is a Step 4 simulation in the end-to-end run. Users, branches and reports are throw-away test rows (`*.test` addresses, test-only values); nothing real was used.

## Commands and results
| Suite | Command | Result |
|---|---|---|
| Database (Step 2 + Step 5) | `cd database/tests && python -m pytest` | **152 passed** (111 earlier + 41 in `test_rbac.py`) |
| Backend | `cd backend && python -m pytest` | **235 passed, 1 skipped** (legacy `TEST_DATABASE_URL` ping test). New: `test_permission_matrix.py`, `test_rbac_api.py` |
| Backend quality | `ruff check .`, `ruff format --check .`, `python -m mypy app` | clean |
| Frontend | `npm run typecheck`, `lint`, `format:check`, `test` | clean; **56 tests passed** (new: `rbac.test.tsx`) |
| End to end | `python e2e/run_e2e.py` | **25/25 scenarios passed** (4 new RBAC scenarios), simulated Auth |
Mutation checks: removing the permission test in `RequirePermission` made 2 frontend tests fail; restored.

## The 16 required security test cases
| # | Case | API level | Database level | UI / E2E |
|---|---|---|---|---|
| 1 | Owner accesses all ten branches | `test_01_*` (list = 10, each id 200) | owner sees 10 branches (`test_owner_sees_all_ten_branches`) | E2E: owner sees 10 |
| 2 | Branch user accesses assigned branch | `test_02_*` | own branch visible, own report insert/read allowed | E2E: branch user gets only own branch |
| 3 | Branch user cannot access another branch | `test_03_*`: path, query, body, record id, nonexistent id, malformed id, no leakage in list | cross-branch select/insert denied (`TestBranchIsolationDb`) | E2E: 403 `branch_access_denied` |
| 4 | Cannot change own role | `test_04_05_*`: no route; DB through API session updates 0 rows | `test_branch_user_cannot_change_own_role_branch_or_status` | – |
| 5 | Cannot change own branch | same | same | – |
| 6 | Inactive account denied | `test_06_*` for branch and owner on every endpoint; missing profile → 403 | inactive sees 0 rows, cannot insert, loses owner powers | E2E: inactive/no-profile pages; deactivation on reload |
| 7 | Anonymous denied | `test_07_*` → 401 on all endpoints | anon has no table/function privileges (`TestInactiveAndAnon`, `TestStructure`) | – |
| 8 | Invalid JWT denied | `test_08_*` (garbage, forged key, wrong audience, expired) + Step 4 matrix (39 tests) | – | E2E: forged-key token → 401 |
| 9 | Owner-only API rejects Branch User | `test_09_*`: `/users`, `/users/{id}` → 403 `permission_denied` | owner-only tables empty for branch user | E2E |
| 10 | Direct URL access blocked | – | – | Vitest: branch user typing `/system-status` → Access denied, page content never rendered, no flicker; E2E in real Chrome incl. reload |
| 11 | Unauthorized requests return 403 | `test_11_*` (+ 401 for anonymous); denials audited | – | E2E |
| 12 | Direct record-ID cannot bypass branch rules | `test_12_*`: guarded handler → 404 (RLS-hidden); **handler without any check still returns nothing** (RLS); list scoped | `test_direct_record_id_of_other_branch_is_invisible` | – |
| 13 | Cannot edit submitted reports | no PUT/PATCH route exists (404/405) | UPDATE denied for Branch User **and Owner** (no grant) | – |
| 14 | Cannot delete submitted reports | no DELETE route (404/405) | DELETE denied for both | – |
| 15 | RLS blocks unauthorized queries | `test_15_*`: raw SQL in a branch user's API session sees 0 rows in 7 owner-only tables, 1 branch, no foreign reports | `TestBranchUserDenied`, `TestStructure` | – |
| 16 | Permissions correct after session refresh | `test_16_*`: new tokens keep permissions; role downgrade and deactivation take effect on the next request with the **same** token | – | Vitest: `TOKEN_REFRESHED` re-reads permissions (downgrade hides nav, deactivation → inactive page, no loading flash); expired session → login |

## Additional checks
- Hostile token metadata (`user_metadata.role = owner`, `app_metadata`), `X-Role`/`X-Branch-Id` headers, and `?role=owner` query parameters do not change the result (`test_04_05_token_metadata_and_headers_cannot_grant_owner`).
- Branch User grant set pinned exactly: dashboard R, branch R, daily reports R+C, nothing else, all OWN scope (`test_branch_user_allowed_set_is_exactly_this`); every owner-only module × every action is denied; unknown roles get nothing; nobody has APPROVE or report DELETE.
- Self-change guard: an owner cannot change their own role or status as an authenticated user; operator sessions can; user_id immutable; last-owner guard still works.
- Audit: denials recorded with actor, module, action and requested branch id; no tokens/passwords; allowed requests and anonymous denials not recorded; flood limit (30/min) works; oversized detail dropped; users cannot update/delete audit rows; role change, branch reassignment and deactivation are audited with the owner as actor and the reason.
- Structural: RLS on every table; no policy for `anon`/`public`; owner-only tables have only `is_owner()` policies; all SECURITY DEFINER helpers pin `search_path`; no `anon`/`public` execute on any function.

## Defect found by testing
The new trigger function was executable by `PUBLIC` (PostgreSQL default); the existing Step 2 test `test_no_public_execute_on_functions` caught it. Fixed in 0010 (`revoke all … from public, anon, authenticated`).

## What these results do not show
Real Supabase behaviour (still pending from Step 4); the pooler login as `app_api`; browsers other than headless Chrome; load/timing behaviour; business endpoints (none exist yet, so the guards are proven with the read-only branch/user endpoints and test-only probe routes). Security is **not** declared complete: every future module must apply and test these guards (rules in `BRANCH_ISOLATION.md`).
