-- 0011_reporting_start_date.sql (Step 7)
-- The reporting start date (opening "balances as at" date + 1 day) decides which days count as "missing report"
-- days. It lives in the owner-only opening_balances row, but Branch Users need it to see their own missing days.
-- This SECURITY DEFINER function exposes ONLY that single date (never any balance) to active signed-in users.
-- Returns NULL while the opening balances have not been configured (decision D1: the date is not seeded).

create or replace function public.reporting_start_date() returns date
language sql stable security definer set search_path = public, pg_temp
as $$
  select ob.as_of_date + 1
    from public.opening_balances ob
   where ob.id = 1
     and exists (select 1 from public.profiles p where p.user_id = auth.uid() and p.is_active)
$$;

revoke all on function public.reporting_start_date() from public, anon, authenticated;
grant execute on function public.reporting_start_date() to authenticated;

comment on function public.reporting_start_date() is
  'Tracking start date = opening_balances.as_of_date + 1; NULL until opening balances are saved. Date only, no balances.';
