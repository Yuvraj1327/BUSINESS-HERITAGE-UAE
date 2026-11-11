# ALSAFA Heritage Laundry — Management System

Web-based ERP for ALSAFA Heritage Laundry: one Owner dashboard over 10 branches, plus branch-level daily reporting, cash and bank management, expenses and savings, suppliers, employees and compliance, trade licences, rental agreements with post-dated cheques, tasks, and reports. Currency AED; banks ENBD and ADCB.

**Status:** Steps 1-12 complete in code (architecture, database, foundation, authentication, RBAC, layout, dashboard & daily reports, finance, employees & compliance, rentals & PDC, tasks & alerts, reports/analytics/exports/activity history). Not deployed. Start with `docs/HANDOVER.md`. Planning documents: `docs/architecture/`; database: `docs/database/`, `database/`; deployment: `docs/deployment/`.

## Stack
Frontend: React 19, TypeScript (strict), Vite, Tailwind CSS 4, shadcn/ui conventions (Radix), React Router, TanStack Query, Axios, React Hook Form, Zod, Recharts, Lucide, Sonner.
Backend: Python, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic, Pytest, Uvicorn. Database/Auth: Supabase (PostgreSQL, Auth, Storage, RLS). Deploy targets: Vercel (frontend), Render (backend), Supabase.

## Requirements
- Node.js >= 20.19 (tested 22) and npm
- Python >= 3.12 (tested 3.13)
- Optional: a disposable PostgreSQL 14+ server to run the database tests

## Install
```bash
# Frontend
cd frontend && npm install && cp .env.example .env.local

# Backend (macOS/Linux)
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && cp .env.example .env
# Windows: .venv\Scripts\activate   |   copy .env.example .env
```
Use `pip install -r requirements.lock` for the exact versions the project was verified with.

## Run
```bash
# Terminal 1 - API on http://localhost:8008  (docs: /docs, health: /api/v1/health)
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload

# Terminal 2 - web app on http://localhost:5173
cd frontend && npm run dev
```
Without Supabase settings the API still starts (`/api/v1/health/ready` reports `not_configured`) and the web app shows a "sign-in is not configured" page. To sign in you need a Supabase project and an Owner account: `docs/authentication/SUPABASE_SETUP.md` and `OWNER_ACCOUNT_SETUP.md`.

## Checks and tests
```bash
# Frontend (from frontend/)
npm run typecheck     # tsc -b
npm run lint          # eslint
npm run build         # typecheck + production build
npm run format:check  # prettier
npm test              # vitest (mocked Supabase client)

# Backend (from backend/, venv active)
python -m pytest                       # unit tests; DB-backed auth tests auto-skip without a PostgreSQL (TEST_PG_ADMIN_DSN)
python -m mypy app                     # types
ruff check . && ruff format --check .  # lint + format
ruff format .                          # apply formatting

# End-to-end auth run (real app + DB, SIMULATED Supabase Auth; see docs/authentication/AUTH_TEST_RESULTS.md)
pip install -r e2e/requirements.txt && python e2e/run_e2e.py

# Database layer (needs a disposable PostgreSQL; see docs/database/MIGRATION_GUIDE.md)
cd database/tests && pip install -r requirements-test.txt
TEST_PG_ADMIN_DSN="host=localhost user=postgres dbname=postgres" python -m pytest
```

## Layout
```
frontend/   React app (src/: components, layouts, pages, routes, hooks, services, lib, schemas, config ...)
backend/    FastAPI app (app/: api, core, database, models, schemas, repositories, services, middleware ...), alembic/, tests/
database/   SQL migrations 0001-0019 and database tests
e2e/        local end-to-end harness: simulated Supabase Auth server + Playwright (Step 4)
docs/       architecture/ (Step 1), database/ (Step 2), authentication/ (Step 4), security/ (Step 5), ui/ (Step 6), settings/ (Settings section), PROJECT_SETUP.md, ENVIRONMENT_SETUP.md
```
More detail: `docs/PROJECT_SETUP.md`. Environment variables and security rules: `docs/ENVIRONMENT_SETUP.md`.

## Security basics
`.env` files are git-ignored; only `*.example` placeholders are committed. The Supabase service-role key and database password must never appear in frontend variables or source control.
