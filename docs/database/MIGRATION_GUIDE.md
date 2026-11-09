# MIGRATION_GUIDE — Step 2

## Order (run strictly in sequence)
| File | Content |
|---|---|
| 0001_foundation.sql | `app` schema, Dubai-date helper, `app_api` role, touch trigger |
| 0002_core_tables.sql | branches, expense_categories, profiles, RLS helper functions, last-owner guard |
| 0003_finance_tables.sql | opening_balances, opening_branch_cash, suppliers, head_office_expenses |
| 0004_daily_reports.sql | daily_reports, active-unique index, future-date trigger |
| 0005_operations_tables.sql | employees, tasks, trade_licenses, rental_agreements, pdc_cheques |
| 0006_audit.sql | audit_log, audit triggers on 12 tables |
| 0007_functions_views.sql | reconciliation view, app_balances, missing reports, void and rental functions |
| 0008_rls_and_grants.sql | privilege reset, RLS enable, policies |
| 0009_seed_reference_data.sql | 10 branches, 7 categories (idempotent) |
| 0010_rbac_hardening.sql | Step 5: self-change guard on profiles, `ACCESS_DENIED` audit action + writer function, `app.can_access_branch()` (apply once, after 0009) |

## Ownership (single migration history)
- **Alembic (Step 4) owns every object in `public` and `app`.** Step 4 wraps each file above as one Alembic revision that executes the SQL; no Supabase-CLI migrations are used, so there is one history. Downgrades are not provided yet (add in Step 4 as needed).
- **Supabase owns** `auth`, `storage`, `extensions`, roles anon/authenticated/service_role. Migrations only reference `auth.users` and `auth.uid()`; they never create or alter them.
- SQLAlchemy models (Step 4+) mirror these tables; they must not auto-create tables (`create_all` is forbidden).

## Applying
- Fresh **development** Supabase project only. Do not run against production or any database containing data: 0001-0008 are not re-runnable (tables are created without IF NOT EXISTS; 0009 is idempotent).
- `app_api` login: an operator runs `ALTER ROLE app_api LOGIN PASSWORD '...'` out of band; never commit it.
- Create the first owner: insert the auth user via Supabase Auth, then insert a `profiles` row with role `owner` using the service role (profiles RLS requires an existing owner).
- Opening balances are NOT seeded; the owner enters them after D1 is decided.

## Local test run
1. A disposable PostgreSQL 14+ server (tested on 16.15). 2. `pip install -r database/tests/requirements-test.txt`. 3. `TEST_PG_ADMIN_DSN="host=... user=postgres dbname=postgres" pytest database/tests`. The suite creates and drops its own database and applies `tests/stub_supabase.sql` (test only, never for Supabase).

## Notes
`security_invoker` views need PostgreSQL 15+ (Supabase supports it). Extensions are not required (`gen_random_uuid()` is built in).
