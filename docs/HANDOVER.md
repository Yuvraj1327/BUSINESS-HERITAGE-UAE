# ALSAFA Heritage Laundry ERP — Project handover (after Step 13)

## 1. Completed modules
| Step | Module | Main doc |
|---|---|---|
| 1–2 | Planning documents; PostgreSQL schema, RLS, functions, seed | `docs/architecture/`, `docs/database/` |
| 3–5 | Project foundation; Supabase authentication; RBAC and branch isolation | `docs/authentication/`, `docs/security/` |
| 6 | Layout and design system | `docs/ui/` |
| 7 | Owner dashboard, daily branch reports, missing reports | `docs/reporting/STEP7_REPORTING.md` |
| 8 | Opening balances, cash & banks, expenses & savings, suppliers | `docs/finance/STEP8_FINANCE.md` |
| 9 | Employees, visas/passports, trade licences | `docs/hr/STEP9_EMPLOYEES_COMPLIANCE.md` |
| 10 | Rental agreements and PDC cheques | `docs/rentals/STEP10_RENTALS_PDC.md` |
| 11 | Tasks and centralized alerts | `docs/tasks/STEP11_TASKS_ALERTS.md` |
| 12 | Reports & Analytics, CSV/Excel exports, Activity History, final integration | `docs/reports/STEP12_REPORTS_ANALYTICS.md` |
| 13 | Customer orders, pickup & delivery operations, order payments, order reports | `docs/orders/STEP13_CUSTOMER_ORDERS.md` |

Still placeholders (unchanged by approved scope): **User Management** (`/users`) and **Settings → General** (`/settings`);
they show "This module is not built yet". Customer order management is built (Step 13) on assumptions O1–O14 that need client confirmation, notably Branch User access, no refund workflow, and no posting of order payments to Cash & Banks.

## 2. Stack
React 19 + TypeScript + Vite + Tailwind 4 + shadcn/Radix, React Router, TanStack Query, Axios, Zod, Recharts · FastAPI +
Pydantic v2 + SQLAlchemy 2 (raw SQL) + openpyxl · PostgreSQL 16 / Supabase (RLS, JWKS-verified JWT; API runs as the
restricted `app_api` role) · Vercel / Render / Supabase / GitHub as targets.

## 3. Run locally
See `README.md` (install and run), `docs/ENVIRONMENT_SETUP.md` and `docs/authentication/SUPABASE_SETUP.md` (a Supabase
project and an Owner account are needed to sign in).
```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev            # http://localhost:5173
```

## 4. Environment and migrations
Variable reference: `docs/deployment/DEPLOYMENT_GUIDE.md` §2 and the three `.env.example` files. Migrations are plain SQL,
`database/migrations/0001`–`0016`, applied in order (the Alembic folder has no revisions; do not run `alembic upgrade`).
Order and purpose: `docs/database/MIGRATION_GUIDE.md`.

## 5. Test commands and results (executed 2026-11-10)
| Command | Result |
|---|---|
| `cd backend && pytest -q` (PostgreSQL test server needed, otherwise ~270 tests skip silently — check the passed count) | 560 passed, 1 skipped |
| `ruff check . && ruff format --check . && mypy app` | clean |
| `cd database/tests && TEST_PG_ADMIN_DSN=… pytest -q` | 162 passed |
| `cd frontend && npx tsc -b && npx eslint src && npx vitest run && npm run build` | clean; 285 tests passed |
| `python e2e/run_e2e.py` (≈5 min; `E2E_ONLY=13` runs only the Step 13 scenarios) | 122/122 passed, simulated Auth |

## 6. Deployment
`docs/deployment/DEPLOYMENT_GUIDE.md`. **Nothing is deployed.** Manual dashboard work remaining: Supabase project + migrations
+ `app_api` password + Owner account + Auth URLs/email templates; Render service and variables; Vercel project and variables;
CORS origin; domains; backups; optional monitoring (no Sentry DSN exists, so none is wired).

## 7. Known issues and open decisions
- Real Supabase Auth has never been exercised; E2E uses a simulated GoTrue (`e2e/fake_gotrue.py`).
- No scheduler for alerts (computed on demand); export downloads are logged, not stored in `audit_log` (X1).
- Alembic is configured but empty; migrations are applied as SQL files.
- Production-size performance is untested; the main frontend bundle is ~686 kB (Reports/Activity are lazy-loaded).
- Business decisions awaiting the Owner are numbered in `docs/architecture/OPEN_DECISIONS.md` (D…, R1–R11, T1–T10, X1–X7).
- Optional customer order management: not started.
