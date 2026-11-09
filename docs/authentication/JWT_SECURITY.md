# JWT_SECURITY

How the FastAPI backend verifies Supabase access tokens (`backend/app/core/security.py`).

## Prerequisite: asymmetric signing keys
The backend verifies tokens with the project's **public JWKS** (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`). That requires the Supabase project to sign with an asymmetric key (ES256, or RS256). Projects that still use the legacy shared HS256 secret expose no useful JWKS and would force the backend to hold a signing secret; **do not do that** – migrate the project to JWT Signing Keys (see `SUPABASE_SETUP.md`). Until then every token is rejected (`auth_keys_unavailable` / `invalid_token`).

## Checks on every token
| Check | Rule |
|---|---|
| Algorithm | allow-list `ES256`, `RS256` only. `none` and `HS*` are rejected **before** any key lookup (blocks algorithm-confusion attacks) |
| Key | header must carry a `kid`; the key is looked up in the JWKS by `kid`; unknown `kid` → invalid |
| Signature | verified with that key |
| Issuer | `iss` == `SUPABASE_JWT_ISSUER` (default `<SUPABASE_URL>/auth/v1`) |
| Audience | `aud` == `authenticated` |
| Expiry | `exp` required; 10 s leeway for clock skew |
| Required claims | `exp`, `iss`, `aud`, `sub` |
| Subject | `sub` must be a UUID (it becomes `auth.uid()`) |
| Token class | `role` must be `authenticated`; `anon` / `service_role` API-key JWTs and anonymous sign-ins are rejected |
| Size | tokens over 8 KB are rejected without parsing |

Errors are intentionally uniform (`invalid_token`) except expiry (`token_expired`), which the UI uses to say "session ended". Details are never returned to the client or logged with token contents.

## JWKS cache and key rotation
- Keys are cached in memory per process for **600 s** (`JWKS_CACHE_TTL_SECONDS`).
- An unknown `kid` (typical during rotation) triggers one refresh, **at most once per 60 s** (`JWKS_REFRESH_COOLDOWN_SECONDS`), so forged tokens with random `kid`s cannot make the backend hammer the auth server.
- If a refresh fails, the last good keys are still used for up to **3600 s** past their TTL (`JWKS_MAX_STALE_SECONDS`); after that verification **fails closed** with `503 auth_keys_unavailable`. It never "fails open".
- The JWKS fetch uses HTTPS (required in production), a 5 s timeout and no redirects. Only keys with an allowed algorithm are accepted. The cache is thread-safe.
- Consequence to know: after you **revoke** a signing key in Supabase, the old key can still be used for up to `JWKS_CACHE_TTL_SECONDS` (10 min by default) on instances that cached it. Lower the TTL if you need faster revocation.

## What a token is trusted for
Only `sub` (user id), `email`, `session_id`, `exp`, `iat`, `aal` are read, and only after verification. **`user_metadata` and `app_metadata` are never used for authorization.** Role, branch and active flag come from the `profiles` table, read under RLS.

## Limits of JWTs (be honest about them)
- A JWT cannot be recalled before `exp`. Signing out in the browser does not invalidate a copy of the token someone already holds. Access tokens live ≤ 1 hour (Supabase default; keep it short in the dashboard).
- Therefore **access is controlled by the profile**, checked on each request: deactivating an account blocks it immediately even while its token is still valid (tested end to end).
- Refresh-token revocation (which `provision_account.py deactivate` does by banning the Auth user) stops new tokens from being issued.

## Secrets and exposure
- The API needs **no secret** to verify tokens (public keys).
- `SUPABASE_SERVICE_ROLE_KEY` is not a setting of the API (`test_service_role_key_is_not_a_setting`). Only the operator script reads it, from the shell environment.
- The frontend env check refuses any `VITE_*` name containing "service role" and any anon key that is a `service_role` JWT or an `sb_secret_…` key. The production bundle was scanned: no service-role key, DB URL or database role names (`AUTH_TEST_RESULTS.md`).
- Tokens are sent in the `Authorization` header only; CORS `allow_credentials` is off; no cookies.

## Test coverage (all local, locally generated keys)
valid ES256 and RS256 · missing / wrong-scheme / malformed / oversize token · expired, within leeway · wrong issuer · wrong audience · each required claim missing · non-UUID subject · `anon`, `service_role`, missing role, anonymous sign-in · same `kid` with different key · tampered payload · `alg: none` · HS256 confusion · missing `kid` · cache hit · rotation refresh · refresh rate-limit · JWKS down at start (503) · stale keys then fail-closed · identity not taken from query/header · no leakage in error text.
