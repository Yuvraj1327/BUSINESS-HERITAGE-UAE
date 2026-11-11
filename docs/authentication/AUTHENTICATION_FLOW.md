# AUTHENTICATION_FLOW

How sign-in works end to end in the ALSAFA ERP (Step 4). Authorization (what each role may do) is Step 5: see `docs/security/RBAC_ARCHITECTURE.md`.

## Principles
- **Supabase Auth proves who you are; the ERP profile decides if you may use the system.** A valid Supabase account without an active `profiles` row gets nothing.
- Identity comes only from the **verified access token**. Never from a request body, query string, other header, or `user_metadata`.
- The browser holds only the public URL + anon key. The service-role key exists nowhere in the app.
- **No public registration.** Accounts are created by an operator (`OWNER_ACCOUNT_SETUP.md`).
- Row Level Security (Step 2) stays on and is enforced for every API query.

## Components
| Piece | Where | Job |
|---|---|---|
| Supabase client | `frontend/src/lib/supabase.ts` | PKCE flow, persisted session, auto token refresh |
| Session storage | `frontend/src/lib/auth-storage.ts` | localStorage ("keep me signed in") or sessionStorage |
| `AuthProvider` | `frontend/src/auth/AuthProvider.tsx` | restores session, listens to auth events, loads profile, feeds token to API client |
| Guards | `frontend/src/auth/guards.tsx` | `ProtectedRoute`, `GuestRoute` |
| Pages | `frontend/src/pages/auth/` | Login, Forgot password, Reset password, Access denied |
| Token verifier | `backend/app/core/security.py` | JWKS fetch/cache, signature + claim checks |
| Dependencies | `backend/app/api/deps.py` | bearer extraction, claims, user-context DB session, active profile |
| Endpoints | `backend/app/api/v1/auth.py` | `GET /api/v1/auth/me`, `GET /api/v1/auth/profile` |
| Provisioning | `backend/scripts/provision_account.py` | operator tool for accounts |

## Sign-in
1. User submits email + password (validated client-side: email format, password present).
2. `supabase.auth.signInWithPassword` → Supabase returns access token (JWT, ~1 h) + refresh token.
3. supabase-js stores the session (localStorage if "Keep me signed in" is ticked, otherwise sessionStorage) and emits `SIGNED_IN`.
4. `AuthProvider` sees the session and calls `GET /api/v1/auth/profile` with `Authorization: Bearer <access token>`.
5. Backend verifies the JWT (see `JWT_SECURITY.md`), opens a DB session as `authenticated` with the user's claims, reads the user's `profiles` row (RLS lets a user read only their own).
6. `200` → the app renders. `403 profile_missing` / `403 account_inactive` → "Access denied" page with a sign-out button. Other failure → "Could not load your account" + retry.

Wrong email and wrong password produce the same message ("Incorrect email or password.").

## Session restoration (no login flicker)
On page load `AuthProvider` is in status `loading` until supabase-js has read the stored session (`INITIAL_SESSION`). Guards render a loading indicator in that state, so a signed-in user never sees the login form flash, and a signed-out user is redirected exactly once. Verified in the E2E run by watching the DOM for the login heading across three reloads.

## Token refresh and expiry
- supabase-js refreshes the access token automatically before it expires; `TOKEN_REFRESHED` updates the session without reloading the profile.
- The API client asks `getSession()` for the token on every request, so it always sends a fresh one.
- If the refresh token is invalid, Supabase emits `SIGNED_OUT` → the app returns to login and shows "Your session has ended." (also shown if the API answers `401`, which triggers a local sign-out).

## Logout
`signOut({ scope: 'local' })` ends the session **on this device**, clears persisted storage and the TanStack Query cache, then guards redirect to `/login`. Other devices stay signed in (use `scope: 'global'` later if the owner wants "sign out everywhere").
**There is no `/auth/logout` API endpoint on purpose.** An already-issued access token remains valid until its `exp` (≤ 1 hour); a server endpoint could not truthfully revoke it. What does take effect immediately is **deactivating the profile**: the API checks the profile on every `/auth/profile` call and (from Step 5) on every protected call.

## Password reset
1. `/forgot-password`: user enters email → `resetPasswordForEmail(email, { redirectTo: <origin>/reset-password })`. The page **always** shows "If an account exists…" (except for network or rate-limit errors), so it cannot be used to discover accounts.
2. User opens the emailed link **in the same browser** (PKCE: the one-time code is exchanged using a verifier saved in that browser).
3. supabase-js exchanges the code, emits `PASSWORD_RECOVERY`; the status becomes `recovery`. Guards keep a recovery session out of the app and send it to `/reset-password`.
4. User chooses a new password (≥ 10 characters, a letter and a number, confirmation must match) → `updateUser({ password })` → the session is ended → login page says "Your password has been updated."
5. A link that is invalid, expired, reused, or opened in another browser shows "Reset link not valid" with a link to request a new one.

Set the same minimum length (10) in the Supabase dashboard (`SUPABASE_SETUP.md`) so the server enforces what the form promises.

## First login with an Owner-issued password
The Owner creates a Branch User with an initial password (`POST /users`, Supabase Admin API, no invitation email) and the
profile gets `must_change_password = true`.
1. The user signs in with email + initial password (normal `signInWithPassword`; public signup stays off).
2. `GET /auth/profile` returns `must_change_password: true`; `ProtectedRoute` renders only the *Change your password* page.
3. Server-side enforcement: every business route goes through `get_current_profile`, which answers `403 password_change_required`
   while the flag is set. Only `/auth/me`, `/auth/profile` and `/auth/change-password` are exempt, so skipping the page in the browser gains nothing.
4. The page re-checks the current password, requires a different, strong new password + matching confirmation, then calls
   `POST /auth/change-password`. The API updates the password through the Supabase Admin API and clears the flag with
   `app.complete_password_change()` (SECURITY DEFINER; touches only the caller's own row). The app opens.
Limits: the server cannot compare the new password with the initial one (it never stores it); the page does that. Nobody can clear the flag by writing to `profiles` (RLS: owner-only writes).

## Routes
| Path | Access | Notes |
|---|---|---|
| `/login`, `/forgot-password` | guests only | signed-in users are sent to `/` (or the page they originally wanted) |
| `/reset-password` | recovery session | unauthenticated → "link not valid" |
| `/` and everything in the app shell | signed in + active profile | placeholder home page; no Owner/Branch routing yet (Step 5/6) |
| anything else | – | 404 page. There is no `/register`. |

## Backend request path
```
Authorization: Bearer <jwt>
  → get_token_claims   verify signature/iss/aud/exp/sub (no DB)
  → get_db_session     SET LOCAL ROLE authenticated + request.jwt.claims (per transaction)
  → get_current_profile  profiles row by token subject → 403 if missing/inactive
```
`GET /auth/me` stops after step 1 (token-only, no DB). `GET /auth/profile` runs all three and also returns the caller's `permissions`. Protected endpoints add `require_permission` / `BranchScope` on top (Step 5).

### Database access
The API logs in as **`app_api`** (NOLOGIN until an operator sets a password; NOINHERIT; NOBYPASSRLS; member of `authenticated`). Each transaction starts with `SET LOCAL ROLE authenticated` and `set_config('request.jwt.claims', …, true)`, so `auth.uid()` and every policy behave exactly as they would for a Supabase client. A SQLAlchemy `after_begin` hook re-applies this at the start of every transaction (so it survives `commit()`); `SET LOCAL` is transaction-scoped so nothing leaks to the next pooled use (tested). The privileged `postgres`/`service_role` credentials are never used by request handling.

## Error responses
| HTTP | `error.code` | When |
|---|---|---|
| 401 | `not_authenticated` | no/odd `Authorization` header |
| 401 | `invalid_token` | bad signature, issuer, audience, structure, algorithm, unknown key, non-user token |
| 401 | `token_expired` | `exp` passed (beyond 10 s leeway) |
| 403 | `profile_missing` | valid token, no profile row |
| 403 | `account_inactive` | profile `is_active = false` |
| 503 | `auth_keys_unavailable` | signing keys cannot be fetched and no usable cached copy |
| 503 | `database_not_configured` | `DATABASE_URL` missing |

401 responses carry `WWW-Authenticate: Bearer`. Messages never reveal which check failed.

## What users cannot do
- Change their own role, branch or active flag: there is no endpoint that does it, and RLS allows `profiles` writes to the Owner only (tested: an attempted self-escalation updates 0 rows / is rejected).
- Gain a role from token content: `user_metadata`/`app_metadata` are ignored (tested with a hostile token).
- Register: no page, no route, no endpoint.
