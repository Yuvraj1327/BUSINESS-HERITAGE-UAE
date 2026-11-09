# RBAC_ARCHITECTURE

Step 5: who may do what, enforced in three independent layers. Authentication (who you are) is Step 4 and is reused unchanged.

## Roles (exactly two)
| Role | Database value (`profiles.role`) | Python | Branch | Summary |
|---|---|---|---|---|
| OWNER | `owner` | `Role.OWNER` | none (`branch_id` is NULL, enforced by CHECK) | every branch, every approved module |
| BRANCH_USER | `branch` | `Role.BRANCH_USER` | exactly one (`branch_id` NOT NULL, CHECK) | own branch: dashboard (read), own branch record (read), daily reports (read, create) |

No other role names exist. Anonymous users have no role and no access. Inactive profiles (`is_active = false`) are treated as having no role.

## Trust model
Role, branch and active status come **only** from the `profiles` row of the user whose JWT signature was verified. Never trusted: a role/branch sent by the browser, request-body or query user ids, custom headers, `user_metadata` / `app_metadata` in the token. (Tested with hostile tokens and `X-Role` headers.)

## Three layers
```
Browser   route guards, hidden nav, <Can>          usability only (permissions come from the server)
FastAPI   verified JWT -> active profile -> Principal -> permission -> branch scope      real enforcement
Postgres  RLS as role `authenticated` with the caller's auth.uid(); constraints; triggers  last line of defence
```
Each layer is tested on its own: a handler that forgets its branch check still cannot leak another branch's row (RLS), and the database refuses writes the API never offers.

## Single source of truth: `backend/app/core/permissions.py`
`Role`, `Module` (15 modules + `audit_log`), `Action` (READ, CREATE, UPDATE, DELETE, APPROVE, EXPORT, MANAGE), `Scope` (`all_branches`, `own_branch`) and `PERMISSION_MATRIX`. Default deny: a module not listed for a role grants nothing; unknown role values grant nothing. The matrix is served to the UI as the caller's slice in `GET /api/v1/auth/profile` → `permissions`, so the frontend keeps no copy of the rules. Full table: `PERMISSION_MATRIX.md`.

## Backend authorization (`backend/app/api/authz.py`, `deps.py`)
| Dependency | Does |
|---|---|
| `get_token_claims` (Step 4) | verify JWT: signature, issuer, audience, expiry |
| `get_current_profile` (Step 4) | load the profile by token subject under RLS; 403 `profile_missing` / `account_inactive` |
| `get_principal` | build `Principal(user_id, role, branch_id, full_name)` from that row |
| `require_permission(module, action)` | 403 `permission_denied` unless the matrix grants it |
| `require_owner` | 403 unless role is owner (for owner-only operations not expressible as a module action) |
| `get_branch_scope(module, action)` | permission check + `BranchScope` (all branches vs own branch) |
| `require_branch_access(module, action, param)` | as above, and rejects a `{branch_id}` path/query value that is not the caller's branch before the handler runs |

Responses: 401 `not_authenticated` / `invalid_token` / `token_expired` (no or bad token), 403 `profile_missing`, `account_inactive`, `permission_denied`, `branch_access_denied`. Messages are generic.

Endpoints added in Step 5 (read-only; they exist to exercise the guards, not as business modules): `GET /api/v1/branches`, `GET /api/v1/branches/{id}`, `GET /api/v1/users`, `GET /api/v1/users/{id}` (owner only). `GET /api/v1/auth/profile` now also returns `permissions`.

## Frontend (`frontend/src/auth/`)
- `permissions.ts` – module/action names and `hasPermission` (default deny).
- `use-permissions.ts` – `usePermissions()` → `can(module, action)`, `scope`, `isOwner`, `branchId`.
- `permission-guards.tsx` – `<RequirePermission module action />` route guard (renders **Access denied** in place, URL unchanged) and `<Can>` (restricted buttons/links are not rendered).
- `config/navigation.ts` + `use-navigation.ts` – one list of nav entries; shown only if `available` (module exists) **and** permitted.
- `routes/index.tsx` – every protected branch of the route tree declares its module/action; new module pages must do the same.
- No flicker: `ProtectedRoute` (Step 4) holds a loading screen until the profile **and its permissions** have arrived; guards never render before that.
- Session refresh: each Supabase `TOKEN_REFRESHED` re-reads the profile in the background (no loading state), so a role/branch/active change made by the Owner shows up at the next refresh (about hourly) without signing out; a 403 from the API (`permission_denied`, `branch_access_denied`, …) shows a toast and triggers a throttled re-read. Expired sessions still end in the login page (Step 4).
- Inactive or missing profile → "Account inactive" / "Account not set up" page (Step 4).

## Database (migrations 0008 + 0010)
See `RLS_VERIFICATION.md`. Step 5 adds `0010_rbac_hardening.sql`: self-change guard on `profiles`, `app.can_access_branch()`, and the `ACCESS_DENIED` audit action with a locked-down writer function. Nothing from 0001–0009 was removed or weakened.

## User-management foundation (no UI, no write endpoints)
`backend/app/services/user_admin_policy.py` – pure authorization rules for the planned actions (create Branch User, assign branch, activate/deactivate, view, update profile, reset access): only an active Owner; nobody may change their own role/branch/status; Branch Users need exactly one branch; Owners have none; the last active Owner cannot be deactivated. Mirrors the database rules. The future service must call `authorize_user_change` before writing; account creation itself keeps using the operator tool (`backend/scripts/provision_account.py`, Step 4), which needs the service-role key and therefore stays out of the web API for now.

## Audit
Role changes, branch reassignment, activation/deactivation, and creation of profiles are recorded by the existing `profiles_audit` trigger (actor = `auth.uid()`, old and new values, optional reason). Failed privileged access by a signed-in user is recorded as `ACCESS_DENIED`. Details: `RLS_VERIFICATION.md` §Audit. Permission matrix changes are code changes (version control + review), not runtime edits, so there is no runtime "permission change" event.

## Not in scope (unchanged)
Dashboards, daily-report forms, finance, expenses, suppliers, employees, rentals, tasks, reports, customer orders, User Management UI.
