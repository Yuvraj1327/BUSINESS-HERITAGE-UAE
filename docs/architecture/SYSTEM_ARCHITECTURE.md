# SYSTEM_ARCHITECTURE — ALSAFA Heritage Laundry ERP

## 1. Stack (as specified)

Frontend: React, TypeScript, Vite, Tailwind, shadcn/ui, React Router, TanStack Query, Axios, Recharts, React Hook Form, Zod, Lucide React.
Backend: Python, FastAPI, Pydantic, SQLAlchemy 2.0, Alembic, Pytest.
Data/Auth: Supabase PostgreSQL, Auth, Storage, RLS, JWT verification.
Deployment: Vercel (frontend), Render (backend), Supabase (DB/Auth), GitHub (source).
Permitted additions, with reason: TanStack Table (data grids); PyJWT (token verification); psycopg 3 driver; pydantic-settings (config); openpyxl (Excel export); WeasyPrint or ReportLab (PDF export); slowapi (rate limiting); Vitest + Testing Library and Playwright (tests); ruff/ESLint. No alternative frameworks.

## 2. Context and data flow

```
Browser (React SPA on Vercel)
  1. Sign in with Supabase Auth (anon key, auth only) → JWT
  2. All business calls → FastAPI (Render) with Authorization: Bearer JWT
FastAPI
  - verify JWT (signature, expiry, audience), load profile (role, branch, active)
  - authorize per route; apply business rules; write audit entries
  - SQLAlchemy → Supabase Postgres (pooler) as a restricted role, with the
    request's JWT claims set per transaction so RLS policies apply
Supabase: Postgres (RLS on every table) · Auth · Storage (private, if used)
```

Reasons: one place for business rules; RLS remains a real second barrier; service-role key never leaves backend secrets and is used only for admin tasks (user creation).

## 3. Key technology decisions

| Decision | Choice | Reason |
|---|---|---|
| Browser data access | FastAPI only (no direct table queries) | PDF assumed anon-key direct access; the FastAPI stack replaces it |
| RLS with API | Restricted DB role + per-request claims | Bypass roles would nullify RLS |
| Migrations | Alembic owns tables, RLS policies, functions | One migration tool |
| Calculations | Backend service layer with Decimal; SQL aggregates; parity tests against `app_balances()` [VERIFY] | One source of truth |
| Alerts/KPIs | Computed on read, via an alert registry | PDF stores none |
| Time zone | Asia/Dubai | PDF rule |
| SQLAlchemy mode | Synchronous | Simpler; load is 10 branches |
| Exports | Server-side generation (Excel/PDF), permission-checked | Prototype had none |
| Theme | Light (default), Dark, System; per user (D24 superseded) | Settings > Appearance |

## 4. Backend layout (recommended)

```
backend/app/
  main.py  core/(config, security, db, claims)  api/v1/<module>.py
  deps/(current_user, require_owner, require_branch_access)
  models/  schemas/  repositories/
  services/(reconciliation, balances, visa_rules, rental_schedule, alerts, exports, audit)
backend/alembic/   backend/tests/(unit, api, rls, calculations)
```

## 5. Frontend layout (recommended)

```
frontend/src/
  app/(router, providers, guards)  layouts/(Owner, Branch, Auth)
  components/ui (shadcn)  components/(kpi-card, data-table, filter-bar, charts, states)
  features/<module>/(api, hooks, schemas, pages, components)
  lib/(axios client, auth, formatters)  types/
```

## 6. Security and financial integrity

| Area | Strategy |
|---|---|
| JWT | Backend verifies signature, expiry, audience on every request; rejects anon |
| Authorization | Role and branch dependencies on every route; branch id taken from profile, never from client |
| RLS | Enabled on every table; owner full; branch limited per matrix; tests at DB level |
| Private employee data | Owner-only routes and policies; salary never in branch responses |
| Secrets | Env vars only; `.env.example`; service-role key backend only; not in frontend bundle or git |
| Audit | audit_log for financial edits, voids, status changes, user and balance changes |
| Integrity | Numeric(14,2); constraints in DB; atomic transactions (agreement+cheques, opening-balance save) |
| Duplicates | Unique (branch, date); idempotency keys on money-posting creates (proposed) |
| Corrections | Owner-only audited void/edit with reason (pending D4); no hard deletes |
| Submitted reports | Branch users cannot update or delete; confirmation returned once |
| Backup/recovery | Supabase daily backups (Pro); restore tested before go-live; migration rollback plan |
| Transport/hardening | HTTPS, CORS to SPA origin, rate limiting on auth, owner MFA |

### Risks found in current requirements

1. RLS bypass if API uses a privileged DB role.
2. Balance accuracy: no cash↔bank transfers, unclear POS-pending, unclear savings use (D19–D21).
3. Supplier "Mark paid → 0" erases history (D5).
4. No correction path; a wrong report is permanent unless D4 is approved.
5. Missing-report logic overcounts closed days (D13).
6. Hosting: Render free tier sleep; UAE latency; backups need Supabase Pro (D3).
7. Sample generator and "Clear sample data" would wipe real data if left in (D7).
8. Date handling: Dubai time vs UTC mistakes around midnight.
9. Rounding/month arithmetic in cheque schedules could produce off-by-one-day or off-by-fils errors.
10. Missing schema SQL and prototype means rules could diverge on rebuild.

## 7. Environments

Local (Supabase local or a test project), staging (separate Supabase project), production. Sample data only in non-production.

## 8. Optional module integration (Step 13, not approved)

Separate backend package/router and frontend feature folder; new tables only (customers, orders, order_payments, service_categories, order_status_history). Integration points: shared auth/roles (extra roles needed), shared layout and export engine, audit log. Financial link: daily_reports remains the source of truth for revenue; orders feed operational views; optional reconciliation report compares order collections to branch daily sales. Order expenses must map to the 7 core categories or be added through approved category changes. No change to core tables or formulas.
