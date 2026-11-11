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
| 0011_reporting_start_date.sql | Step 7: `public.reporting_start_date()` (SECURITY DEFINER, active users) so Branch Users can learn the reporting start date without reading owner-only balances (apply once, after 0010) |
| 0012_finance_ledgers.sql | Step 8: supplier entries, POS settlements, cash transfers, expense idempotency/correction link, `app_cash_bank_ledger()` (single source of truth for balances), replaced `app_balances`/`app_branch_cash`, `v_supplier_outstanding`, void functions (apply once, after 0011; additive). See `docs/finance/STEP8_FINANCE.md` |
| 0013_employee_compliance.sql | Step 9: employee notes/visa-cancelled date/archive columns, licence notes/archive and unique number, immutable `license_renewals` history (apply once, after 0012; additive). See `docs/hr/STEP9_EMPLOYEES_COMPLIANCE.md` |
| 0014_rentals_pdc.sql | Step 10: rental agreement bank/cheque count/first cheque/notes, PDC cleared/bounced dates and users, replacement link, unique cheque number per bank, final (immutable, undeletable) cleared/bounced cheques via `app.pdc_guard`, and `app_cash_bank_ledger` replaced so the cleared-cheque row carries branch and description (apply once, after 0013; additive). See `docs/rentals/STEP10_RENTALS_PDC.md` |
| 0015_tasks_alerts.sql | Step 11: task description / notes / completion date and user (Done if and only if completed), assignee must be an active user (`app.tasks_before`), and the new Owner-only `alerts` table (unique open key, read / acknowledged / resolved state, no delete). Apply once, after 0014; additive. See `docs/tasks/STEP11_TASKS_ALERTS.md` |
| 0016_report_indexes.sql | Step 12: partial and date indexes for report range scans (`pdc_cheques` cleared/bounced dates, `tasks.completed_at`, `audit_log(table_name, occurred_at)`, `license_renewals.renewed_on`, `rental_agreements.start_date`). `create index if not exists`, no data or rule change (apply once, after 0015; safe to re-run). See `docs/reports/STEP12_REPORTS_ANALYTICS.md` |
| 0017_customer_orders.sql | Step 13: `service_categories`, `customers`, `orders`, `order_payments`, `order_status_history`, order-number sequence, workflow/payment triggers, audit triggers, RLS and grants. Adds tables only; no existing table or rule changes (apply once, after 0016). See `docs/orders/STEP13_CUSTOMER_ORDERS.md` |
| 0018_first_login_password_change.sql | Adds `profiles.must_change_password boolean not null default false` and `app.complete_password_change()` (SECURITY DEFINER, clears only the caller's own flag). Additive; existing users unaffected. Apply once, after 0017, **before** deploying the API that reads the column. |

## Ownership (single migration history)
- **Alembic (Step 4) owns every object in `public` and `app`.** The plan was for Step 4 to wrap each file above as one Alembic revision; **in the repository today `backend/alembic/versions/` is empty, so the SQL files are applied directly, in filename order (see `docs/deployment/DEPLOYMENT_GUIDE.md`)**; no Supabase-CLI migrations are used, so there is one history. Downgrades are not provided yet (add in Step 4 as needed).
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
