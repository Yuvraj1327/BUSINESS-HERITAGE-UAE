# AUTH_TEST_RESULTS

Step 4 test evidence. **Read the first section before trusting anything below.**

## What was and was not tested
| Environment | Status |
|---|---|
| Local automated tests (unit, DB-backed, component) | **Executed** – results below |
| Local end-to-end run against a **simulated** Supabase Auth server (`e2e/fake_gotrue.py`) | **Executed** – results below |
| A **real Supabase project** (dashboard settings, real email delivery, real key rotation, pooler login as `app_api`, real GoTrue edge cases) | **NOT executed.** No Supabase project or credentials were available. Every "real Supabase" row below is *pending*. |

The simulation implements the GoTrue calls our code makes (password grant, refresh, PKCE exchange, recover/verify/redirect, update user, logout, admin user endpoints, JWKS with ES256). It proves our code follows that protocol and enforces our rules; it cannot prove that a given Supabase dashboard is configured the way `SUPABASE_SETUP.md` says. Nothing here used real credentials, real people's emails, or production data; all users are throw-away rows in a throw-away database.

## Commands executed and results (this build)
| Suite | Command | Result |
|---|---|---|
| Backend (unit + DB-backed) | `cd backend && python -m pytest` | **86 passed, 1 skipped** (skipped: legacy `TEST_DATABASE_URL` ping test). 39 JWT/JWKS tests, 17 DB-backed auth/RLS tests |
| Backend lint/format/types | `ruff check .`, `ruff format --check .`, `python -m mypy app` | clean (46 files formatted, 32 source files type-checked) |
| Database layer (Step 2, regression) | `cd database/tests && python -m pytest` | **111 passed** – migrations and RLS unchanged |
| Frontend (clean copy, `npm ci`) | `npm run typecheck`, `lint`, `format:check`, `test` | all clean; **40 tests passed** (2 files) |
| Frontend production build | `npm run build` with public env vars | built; see bundle scan below |
| End to end | `python e2e/run_e2e.py` | **21/21 scenarios passed** (simulated Auth; real FastAPI, real PostgreSQL + Step 2 migrations + RLS, connecting as `app_api`; real React app in headless Chrome via Playwright) |

DB-backed backend tests need a disposable PostgreSQL superuser (`TEST_PG_ADMIN_DSN`); without one they skip. They build a fresh database from the Step 2 migrations plus the Supabase stub, give `app_api` a temporary login and drop everything afterwards.
Mutation check performed: breaking `ProtectedRoute` made 10 frontend tests fail, then they passed again after restoring it.

## The 16 required test areas
"Local" = executed here. "Real" = needs a real Supabase project (pending).
| # | Area | Local evidence (executed) | Real Supabase |
|---|---|---|---|
| 1 | Valid login | Component test; E2E owner + branch login, profile via bearer token | pending |
| 2 | Invalid login | Component test (generic message, same for unknown email); E2E wrong password / unknown user | pending |
| 3 | Session persistence | E2E: reload ×3 + new tab stay signed in; "keep me signed in" off → sessionStorage only, absent in a new browser context; storage-adapter unit test | pending |
| 4 | Session restoration | Component test: loading state, login form never rendered while restoring; E2E DOM observer saw no login heading across reloads | pending |
| 5 | Logout | Component test (local sign-out, cache cleared, redirect); E2E: storage empty, reload and protected URL stay on login | pending |
| 6 | Forgot password | Component tests (validation, `redirectTo`, neutral message for unknown account, rate-limit message); E2E: ghost address gets same message | pending (real email delivery) |
| 7 | Password reset flow | Component tests (policy: length/letter/number/match, success → signed out → notice, server rejection); E2E full loop: email link → PKCE exchange → weak/mismatch rejected → new password → old password refused → new works → link cannot be reused; link opened in a different browser rejected | pending (real link format, expiry window) |
| 8 | Valid JWT | ES256 and RS256 tokens verified; `/auth/me` content checked (no raw token/secrets); E2E tokens from the simulated issuer | pending |
| 9 | Invalid JWT | malformed, oversize, tampered payload, foreign key with same `kid`, `alg:none`, HS256 confusion, missing `kid`, `anon`/`service_role`/anonymous tokens, non-UUID `sub`, each required claim removed | n/a (pure crypto/logic) |
| 10 | Expired JWT | `token_expired` code + `WWW-Authenticate`; 10 s leeway boundary; UI: 401 → signed out with "session has ended" notice | pending (real expiry/refresh timing) |
| 11 | Wrong issuer | wrong `iss` and wrong `aud` rejected; E2E token signed by an unrelated key rejected | pending (confirm real issuer string matches `<SUPABASE_URL>/auth/v1`) |
| 12 | Missing token | none / `Basic` / `Token` / empty bearer → 401 `not_authenticated` | n/a |
| 13 | Missing profile | 403 `profile_missing` (DB-backed + E2E); `/auth/me` still 200; UI "Account not set up" | n/a |
| 14 | Inactive account | 403 `account_inactive`; inactive user sees no data under RLS; E2E deactivation of a signed-in user takes effect on reload; script deactivate bans Auth sign-in (simulated) | pending (real ban behaviour) |
| 15 | Role-modification prevention | Under `app_api`/`authenticated`: UPDATE of own role affects 0 rows, INSERT of an owner profile rejected, DB unchanged; hostile `user_metadata`/`app_metadata` ignored; PUT/PATCH/POST/DELETE on profile and `/register`, `/signup`, `/logout` → 404/405 | n/a |
| 16 | Protected frontend route access | Component + E2E: unauthenticated → `/login` (with return path), signed-in on `/login` → app, recovery session kept out of app, blocked profile never reaches pages, `/register` is a 404 | pending (with real session) |

## Other verifications
**JWKS handling (local):** cached between requests (1 fetch/5 requests); rotation refresh on unknown `kid`; refresh rate limit (10 forged `kid`s → 1 fetch); JWKS down at start → 503 fail closed; stale keys used briefly then fail closed. E2E: after the simulated issuer rotated its key, the old session was rejected (401 → signed out with notice) and a new sign-in worked after the JWKS refresh.

**RLS user-context sessions (DB-backed):** connection role is `app_api` (not superuser, no BYPASSRLS); session runs as `authenticated` with the caller's `auth.uid()`; the context survives `commit()` and `rollback()`; nothing leaks to the next pooled checkout; a branch user sees only their own profile, the Owner sees all; backend without `DATABASE_URL` → 503 `database_not_configured`.

**Provisioning script (against the simulated Auth + real Postgres):** create branch user (profile + email in outbox + no secrets printed); invalid branch rolls the Auth user back (no orphan); owner-with-branch and branch-without-branch refused; deactivate/activate flips `is_active` and the Auth ban; refuses to run without `SUPABASE_SERVICE_ROLE_KEY`.

**Security checklist**
| Check | Result |
|---|---|
| Service-role key in frontend source or bundle | none. Scan of the production bundle: no `SERVICE_ROLE`, `postgres://`, `DATABASE_URL`, `app_api`, no JWT-shaped strings. The strings `service_role`/`sb_secret` appear only in our refusal check, UI text and supabase-js's own browser guard |
| Env guard | refuses `VITE_*service_role*` names, a `service_role` JWT or `sb_secret_…` as the anon key; requires Supabase vars (https) in production builds (unit-tested) |
| Service-role key in backend settings | not a setting (existing test still passes) |
| Hard-coded credentials / real emails in repo | none; only `*.example` placeholders and test-only throw-away values. Throw-away addresses use the reserved `.test` TLD |
| Step 2 migrations/RLS | untouched; 111 DB tests pass |
| Public registration | no page, route or endpoint; component test + E2E; also disable sign-ups in the dashboard (setup step 4) |
| Identity source | token only; query/header/body values and token metadata ignored (tests) |
| Error disclosure | uniform `invalid_token`; no claim names or stack traces in responses (test) |
| Logout claim | no `/auth/logout` endpoint; docs state tokens live until `exp` and access is governed by the profile |
| CORS | explicit origins, no credentials; unchanged from Step 3 |

**Bundle size note:** the main chunk is ~543 kB (≈158 kB gzipped) after adding supabase-js (separate chunk configured); code-splitting of route pages can come with the real pages.

## Defects found and fixed while testing
1. The "Your session has ended" banner never appeared in the dev server: React StrictMode's double effect run cleared it as the login page mounted. Found by the E2E key-rotation scenario; fixed by clearing the notice on the next sign-in instead.
2. My first key-rotation scenario assumed the backend would reject the old key immediately. The backend (correctly) keeps a cached key until its TTL; documented in `JWT_SECURITY.md` and the E2E runs the backend with a 2 s TTL.
3. Test-helper bug (default `sub` filled in when `sub=None` was meant to remove it) caught by the required-claims test.

## Known limitations
- Real-Supabase behaviour is unverified (table above). Run the checklist in `SUPABASE_SETUP.md` §10 first and record results here.
- Headless Chrome only; no Safari/Firefox/mobile-device runs. Login and forgot-password pages were reviewed in screenshots at 375 px and 1280 px wide; the other auth pages were not screenshot-reviewed.
- No automated check that the real Supabase `redirectTo` allow-list or email template is configured correctly (dashboard-side).
- Access tokens already issued cannot be recalled before expiry (inherent to JWTs); mitigated by the per-request profile check.

## Real Supabase checks (to fill in)
| Date | Project | Checklist item | Result | By |
|---|---|---|---|---|
| | | | | |
