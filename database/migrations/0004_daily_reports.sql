-- 0004_daily_reports.sql

create table public.daily_reports (
  id             uuid primary key default gen_random_uuid(),
  report_date    date not null,
  branch_id      uuid not null references public.branches (id) on delete restrict,
  total_sales    numeric(14,2) not null,
  order_count    integer not null default 0,
  cash_received  numeric(14,2) not null default 0,
  pos_amount     numeric(14,2) not null default 0,
  bank_transfer  numeric(14,2) not null default 0,
  link_payment   numeric(14,2) not null default 0,
  shop_expenses  numeric(14,2) not null default 0,
  shop_savings   numeric(14,2) not null default 0,
  voided_at      timestamptz,
  voided_by      uuid,
  void_reason    text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  created_by     uuid default auth.uid() references auth.users (id) on delete restrict,
  updated_by     uuid,
  constraint dr_sales_positive   check (total_sales > 0),
  constraint dr_orders_nonneg    check (order_count >= 0),
  constraint dr_amounts_nonneg   check (cash_received >= 0 and pos_amount >= 0 and bank_transfer >= 0
                                        and link_payment >= 0 and shop_expenses >= 0 and shop_savings >= 0),
  constraint dr_savings_le_exp   check (shop_savings <= shop_expenses),
  constraint dr_void_pair_chk    check ((voided_at is null) = (void_reason is null))
);

-- One ACTIVE report per branch per day. A voided report (owner correction, decision D4) frees the slot
-- so the branch can resubmit. Concurrent duplicate submissions are rejected by this unique index.
create unique index dr_branch_date_active_uq on public.daily_reports (branch_id, report_date)
  where voided_at is null;
create index dr_branch_date_idx on public.daily_reports (branch_id, report_date desc);
create index dr_date_idx        on public.daily_reports (report_date);

-- Future-date rule uses the Dubai business date (not immutable, so a trigger rather than a CHECK).
create or replace function app.dr_validate() returns trigger
language plpgsql
as $$
begin
  if new.report_date > app.dubai_today() then
    raise exception 'report_date % is in the future (Asia/Dubai today is %)', new.report_date, app.dubai_today()
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

create trigger dr_validate before insert or update of report_date on public.daily_reports
  for each row execute function app.dr_validate();
create trigger dr_touch before update on public.daily_reports
  for each row execute function app.touch_row();
