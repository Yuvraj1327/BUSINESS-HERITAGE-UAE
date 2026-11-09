# ENVIRONMENT_SETUP

Real values live only in git-ignored files: `frontend/.env.local` and `backend/.env`. Committed `*.example` files hold placeholders. Nothing in this repository contains a real credential.

## Frontend (`frontend/.env.local`) — public values only
Everything prefixed `VITE_` is compiled into the browser bundle and visible to every visitor.

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | production: yes; dev default `http://localhost:8000/api/v1` | FastAPI base URL including `/api/v1` |
| `VITE_SUPABASE_URL` | production: yes (https) | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | production: yes | Supabase anon / publishable key (public by design) |

Validation (`src/config/env.ts`, Zod) runs at startup and fails fast with a readable message. It also **refuses to start** if any `VITE_*` variable name contains "service role", or if the anon key is actually a JWT with `role: service_role` (verified manually in Step 3).

## Backend (`backend/.env`) — private
| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | no (default `development`) | `development`, `test` or `production` |
| `LOG_LEVEL`, `LOG_JSON` | no | JSON logs by default in production |
| `CORS_ORIGINS` | no (default `http://localhost:5173`) | Comma-separated explicit `http(s)://` origins; production forbids localhost |
| `DATABASE_URL` | production: yes | Postgres URL; `postgres://` / `postgresql://` are normalised to the psycopg 3 driver. Blank = not configured |
| `SUPABASE_URL` | production: yes | Project URL |
| `SUPABASE_JWT_ISSUER` | derived | Defaults to `<SUPABASE_URL>/auth/v1` |
| `SUPABASE_JWT_JWKS_URL` | derived | Defaults to `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_AUDIENCE` | no (`authenticated`) | Required `aud` claim |
| `JWKS_CACHE_TTL_SECONDS` / `JWKS_REFRESH_COOLDOWN_SECONDS` / `JWKS_MAX_STALE_SECONDS` | no (600 / 60 / 3600) | Signing-key cache, unknown-`kid` refresh rate limit, and how long cached keys may be used if the key endpoint is unreachable |
| `JWT_LEEWAY_SECONDS` | no (10) | Clock-skew allowance for `exp` |

Production additionally requires `SUPABASE_URL` and the JWKS URL to use `https`. Authentication details: `docs/authentication/`.

Settings are validated at startup (`app/core/config.py`): in `production` a missing `DATABASE_URL`/`SUPABASE_URL` or a localhost CORS origin aborts startup. `DATABASE_URL` is stored as a secret (never printed in repr/logs).

## Development vs production
- Development/test: API docs at `/docs`, readable logs, database optional.
- Production: docs disabled, JSON logs, database and Supabase settings required, explicit CORS origins.

## Security notes
- **Service-role key:** not a setting of the API (a test enforces this) and never a `VITE_*` variable. Only the operator tool `backend/scripts/provision_account.py` reads `SUPABASE_SERVICE_ROLE_KEY`, from the operator's shell environment.
- **Database access:** the API connects as the restricted `app_api` role and, per transaction, switches to `authenticated` with the verified user's claims so RLS applies (`docs/authentication/AUTHENTICATION_FLOW.md`). Never use the `postgres` or `service_role` credentials for ordinary requests.
- **Pooler:** the engine disables psycopg server-side prepared statements (`prepare_threshold=None`) for Supabase's transaction pooler.
- Rotate any key that was ever pasted into chat, an issue or a commit.
- Supabase auth tokens are sent as `Authorization: Bearer` headers (no cookies), so CORS `allow_credentials` is off.
