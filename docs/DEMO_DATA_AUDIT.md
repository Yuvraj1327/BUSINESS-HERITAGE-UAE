# Demo / mock data audit

Scope: `backend/app`, `backend/scripts`, `database/migrations`, `frontend/src` (non-test), `e2e/`.

## Result: no dummy business data was found in application code

| Area | Finding | Action |
| --- | --- | --- |
| Backend (`backend/app`, `backend/scripts`) | No random generators, faker, sample payloads, fallback values or hardcoded KPIs. Every dashboard/report figure is a SQL aggregate over the database (via `dashboard_service`, `analytics_service`, repositories). | none needed |
| Migrations `0001`-`0017` | Only reference data is inserted (`0009`, `0017`): the 10 branches, 7 expense categories, 9 service categories. No transactions, customers, employees, suppliers, balances or salaries. | kept (required master data) |
| Frontend pages/hooks | No mock API layer, no `initialData`, no hardcoded figures. `placeholderData: keepPreviousData` only keeps the previous *real* response visible while a filter change loads. | none needed |
| Frontend cards | `StatCard` shows a skeleton while loading, `—` when no value exists, and the server's `0.00` / `0` when the database is empty. Errors render `ErrorState` with Retry, never a number. "Cash + Bank Balance" shows `—` + "Not configured" until Opening Balances are saved (a real unknown, not a zero). | none needed |
| `frontend/src/pages/DesignSystemPage.tsx` | Contains `SAMPLE_ROWS` for component demos. Only routed when `env.isDev`, is not in the sidebar, and is excluded from production builds. Labelled "not business data". | left; remove the file and its route if you want it gone entirely |
| Test fixtures (`frontend/src/test`, `backend/tests`, `database/tests`, `e2e/`) | Contain invented values ("Test Branch One", etc.). They run only under test runners against throw-away databases / stubbed HTTP and are never bundled or seeded into Supabase. | left |

This audit changed no application behaviour. It added one regression test
(`reports.test.tsx` -> "empty database: every KPI is zero ...") proving the Owner Dashboard shows only zeros and
empty states for an all-zero API response.

## Modules confirmed to read from the database through FastAPI
Dashboard (Owner and Branch), Daily Reports, Branch & Date View, Cash & Banks, Opening Balances, Expenses & Savings,
Suppliers, Employees, Visas & Passports, Trade Licences, Rental Agreements, PDC Cheques, Tasks, Notifications,
Orders, Customers, Pickup & Delivery, Order Reports, Reports & Analytics, Activity History, User Management, Branches.
Each is a React Query call to `/api/v1/...` (see `frontend/src/services/*.service.ts`).

## Existing demo records in your database: manual cleanup plan
Nothing here was run, and no data was touched. The repo cannot tell which rows in *your* Supabase project are
test entries, so check first (read-only; run in the SQL editor as `postgres`):

```sql
-- 1. Everything business-related that exists, by table (review each non-zero count).
select 'daily_reports' t, count(*) from public.daily_reports union all
select 'customers', count(*) from public.customers union all
select 'orders', count(*) from public.orders union all
select 'suppliers', count(*) from public.suppliers union all
select 'employees', count(*) from public.employees union all
select 'rental_agreements', count(*) from public.rental_agreements union all
select 'pdc_cheques', count(*) from public.pdc_cheques union all
select 'tasks', count(*) from public.tasks union all
select 'expenses', count(*) from public.expenses;

-- 2. Accounts: which are real people?
select p.user_id, p.full_name, p.role, b.name branch, p.is_active, u.email
from public.profiles p join auth.users u on u.id = p.user_id left join public.branches b on b.id = p.branch_id
order by p.created_at;
```
Plan, only if you find test rows:
1. Take a backup (Supabase dashboard -> Database -> Backups, or `pg_dump`) before anything else.
2. Financial and compliance records are intentionally never hard-deleted by the app (audited voids instead), and
   foreign keys are `ON DELETE RESTRICT`. Prefer **voiding through the app** (Owner) for reports, expenses, payments.
3. If a hard purge of test data is truly required, do it in a **non-production copy first**, in dependency order
   (children before parents: payments/cheques/entries -> orders/agreements/reports -> customers/suppliers/employees),
   inside a transaction you inspect before `commit`. Never delete `profiles`, `branches`, `expense_categories`,
   `service_categories` or `audit_log`.
4. Deactivate (do not delete) test user accounts: `python scripts/provision_account.py deactivate --email ...`.
5. If Opening Balances were entered with test numbers, re-save them (Owner, Opening Balances) rather than editing rows.
