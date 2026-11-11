# Deployment guide (Vercel + Render + Supabase)

**Nothing has been deployed.** This guide was written from the repository and tested only locally with a disposable
PostgreSQL and a simulated Auth server. Every step marked *manual* needs the Owner's own dashboards and credentials; none
are invented here.

## 1. Pieces
| Piece | Host | Notes |
|---|---|---|
| Frontend (`frontend/`) | Vercel | root `frontend`, build `npm run build`, output `dist`; `vercel.json` rewrites all paths to `index.html` |
| Backend (`backend/`) | Render web service | root `backend`, build `pip install -r requirements.lock`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Database + Auth | Supabase | Postgres with RLS, Supabase Auth (JWKS-signed tokens) |
| Source | GitHub | no `.env` files are committed (`.gitignore`) |

There is no Dockerfile, `render.yaml` or CI workflow in the repository; create them in the dashboards if wanted.

## 2. Environment variables
**Backend** (`backend/.env.example`)
| Name | Required in production | Meaning |
|---|---|---|
| `APP_ENV` | yes (`production`) | production mode enforces https, explicit CORS and a database |
| `CORS_ORIGINS` | yes | comma-separated https origins of the Vercel site (no `*`, no localhost) |
| `DATABASE_URL` | yes | Supabase connection string logging in as the restricted **`app_api`** role (never `postgres` / service role) |
| `SUPABASE_URL` | yes | `https://<ref>.supabase.co`; issuer and JWKS URL are derived from it |
| `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_JWKS_URL`, `SUPABASE_JWT_AUDIENCE` | optional | overrides |
| `LOG_LEVEL`, `LOG_JSON` | optional | logging |
| `JWKS_*`, `JWT_LEEWAY_SECONDS` | optional | JWKS cache tuning |

The Supabase **service-role key is not a backend setting** and must never be set on Render or Vercel. It is only used by
`backend/scripts/provision_account.py` from an operator's shell.

**Frontend** (`frontend/.env.example`, set in Vercel; all `VITE_*` values are public in the bundle)
`VITE_API_BASE_URL` (Render URL + `/api/v1`), `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (public anon key only).

## 3. Database migrations
The repository applies plain SQL files from `database/migrations/` **in filename order** (tests do the same). The Alembic
folder exists but contains no revisions, so do **not** run `alembic upgrade`; apply the files with `psql` or the Supabase
SQL editor on a fresh project: `0001` … `0016`. Details and one-line purposes: `docs/database/MIGRATION_GUIDE.md`.
Files `0001`–`0008` are not re-runnable; `0009` and `0016` are idempotent. Never run them against a database that already
holds data without a backup.

## 4. Order of work (manual)
1. Create the Supabase project; apply migrations 0001–0016.
2. `ALTER ROLE app_api LOGIN PASSWORD '…'` (out of band) and build `DATABASE_URL` from it.
3. Create the Owner in Supabase Auth and insert the `profiles` row (`docs/authentication/OWNER_ACCOUNT_SETUP.md`).
4. Create the Render service, set backend variables, deploy, then check `GET /api/v1/health` and `GET /api/v1/health/ready`
   (`ok` only when the database answers; 503 `database_unavailable` otherwise).
5. Create the Vercel project, set the three `VITE_*` variables, deploy, then add the Vercel origin to `CORS_ORIGINS` on Render.
6. In Supabase Auth settings: set the site URL and redirect URLs to the Vercel domain; enable the password-reset email
   template; decide on email confirmation (`docs/authentication/SUPABASE_SETUP.md`).
7. Enter the opening balances as the Owner. Smoke test: sign in, open Dashboard, Reports, Activity History.

## 5. Monitoring
No Sentry (or other monitoring) is wired in: it needs a DSN the project does not have. Use Render logs (JSON logging via
`LOG_JSON`), the health endpoints for uptime checks, and Supabase logs. Render's free tier sleeps when idle (decision D3);
the first request after idle is slow.

## 6. Backup and restore
- Supabase: enable the daily backups (paid plans) or take logical backups yourself:
  `pg_dump --format=custom --no-owner "$DIRECT_DB_URL" -f alsafa_$(date +%F).dump` (use the direct connection and a role
  that can read all schemas).
- Restore into an **empty** database only: `pg_restore --no-owner --clean --if-exists -d "$TARGET_URL" file.dump`. Restore
  to a scratch project first and run a smoke test before pointing production at it.
- `audit_log` is append-only and part of the dump; keep dumps in private storage (they contain salaries and bank data).
- This procedure was written, not executed, here: no production or Supabase database was available.

## 7. Manual dashboard configuration still required
Supabase project, `app_api` password, Owner account, Auth URLs and email templates; Render service + env vars + health
check path `/api/v1/health`; Vercel project + env vars; DNS / custom domains; CORS origin; backups; any monitoring.

## 8. Not done
No deployment, no production data change, no credentials created, no scheduler for alert generation (alerts are computed
when screens or `/alerts/refresh` are used; add a Render cron job calling the refresh if wanted).
