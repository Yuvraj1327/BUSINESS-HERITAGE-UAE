-- 0008_rls_and_grants.sql : privileges + Row Level Security. Default deny.
-- Model: Owner = all branches; Branch User = own profile, own branch, own-branch daily reports (read + insert only).
-- `anon` receives nothing. service_role (Supabase) bypasses RLS and is backend-only.

-- 1. Start from zero privileges (Supabase default privileges would otherwise grant ALL to anon/authenticated).
revoke all on all tables    in schema public from public, anon, authenticated;
revoke all on all sequences in schema public from public, anon, authenticated;
revoke all on all functions in schema public from public, anon, authenticated;
alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from public, anon, authenticated;

revoke all on schema app from public, anon;
grant usage on schema app to authenticated;
revoke all on all functions in schema app from public, anon, authenticated;
grant execute on function app.user_role(), app.branch_id(), app.is_owner(), app.dubai_today() to authenticated;

-- 2. Enable RLS on every application table.
alter table public.branches             enable row level security;
alter table public.expense_categories   enable row level security;
alter table public.profiles             enable row level security;
alter table public.opening_balances     enable row level security;
alter table public.opening_branch_cash  enable row level security;
alter table public.suppliers            enable row level security;
alter table public.head_office_expenses enable row level security;
alter table public.daily_reports        enable row level security;
alter table public.employees            enable row level security;
alter table public.tasks                enable row level security;
alter table public.trade_licenses       enable row level security;
alter table public.rental_agreements    enable row level security;
alter table public.pdc_cheques          enable row level security;
alter table public.audit_log            enable row level security;

-- 3. Table privileges for `authenticated` (RLS narrows these further).
grant select on public.branches, public.expense_categories, public.profiles, public.audit_log to authenticated;
grant update (name, sort_order, is_active) on public.branches to authenticated;   -- owner only via RLS
grant insert, update on public.profiles to authenticated;                         -- owner only via RLS
grant select, insert, update on public.opening_balances, public.opening_branch_cash, public.suppliers,
      public.employees, public.trade_licenses, public.rental_agreements, public.pdc_cheques to authenticated;
grant select, insert, delete on public.tasks to authenticated;
grant update on public.tasks to authenticated;
grant select, insert on public.head_office_expenses to authenticated;
grant update (is_saving) on public.head_office_expenses to authenticated;         -- saving toggle only; voids via function
grant select, insert on public.daily_reports to authenticated;                    -- no update/delete for anyone
grant select on public.v_daily_reports_reconciled to authenticated;

grant execute on function
  public.app_balances(date), public.missing_report_branches(date), public.missing_report_count(date, date),
  public.void_daily_report(uuid, text), public.void_head_office_expense(uuid, text),
  public.create_rental_agreement(uuid, text, text, date, date, numeric, jsonb, uuid),
  public.renew_rental_agreement(uuid, jsonb)
  to authenticated;

-- 4. Policies. (select app.fn()) lets Postgres evaluate the helper once per statement.
-- branches
create policy branches_select on public.branches for select to authenticated
  using ((select app.is_owner()) or id = (select app.branch_id()));
create policy branches_update_owner on public.branches for update to authenticated
  using ((select app.is_owner())) with check ((select app.is_owner()));

-- expense_categories (read-only for any active user; changes via migrations, decision D16)
create policy expense_categories_select on public.expense_categories for select to authenticated
  using ((select app.user_role()) is not null);

-- profiles: a user reads only their own row; only the owner creates/edits profiles (no self role/branch change)
create policy profiles_select on public.profiles for select to authenticated
  using (user_id = (select auth.uid()) or (select app.is_owner()));
create policy profiles_insert_owner on public.profiles for insert to authenticated
  with check ((select app.is_owner()));
create policy profiles_update_owner on public.profiles for update to authenticated
  using ((select app.is_owner())) with check ((select app.is_owner()));

-- daily_reports: owner all branches; branch user own branch; insert only; never update/delete
create policy dr_select on public.daily_reports for select to authenticated
  using ((select app.is_owner()) or branch_id = (select app.branch_id()));
create policy dr_insert_owner on public.daily_reports for insert to authenticated
  with check ((select app.is_owner()) and voided_at is null);
create policy dr_insert_branch on public.daily_reports for insert to authenticated
  with check ((select app.user_role()) = 'branch'
              and branch_id = (select app.branch_id())
              and created_by = (select auth.uid())
              and voided_at is null);

-- Owner-only tables: select / insert / update (no delete anywhere except tasks)
do $$
declare t text;
begin
  foreach t in array array['opening_balances','opening_branch_cash','suppliers','head_office_expenses',
                           'employees','trade_licenses','rental_agreements','pdc_cheques','tasks']
  loop
    execute format('create policy %I on public.%I for select to authenticated using ((select app.is_owner()))',
                   t || '_select_owner', t);
    execute format('create policy %I on public.%I for insert to authenticated with check ((select app.is_owner()))',
                   t || '_insert_owner', t);
    execute format('create policy %I on public.%I for update to authenticated
                    using ((select app.is_owner())) with check ((select app.is_owner()))',
                   t || '_update_owner', t);
  end loop;
end $$;
create policy tasks_delete_owner on public.tasks for delete to authenticated
  using ((select app.is_owner()));

-- audit_log: owner reads; nobody writes through the API (rows come from the SECURITY DEFINER trigger)
create policy audit_select_owner on public.audit_log for select to authenticated
  using ((select app.is_owner()));
