-- 0007_functions_views.sql
-- Only what the approved architecture needs: reconciliation view, balances (app_balances),
-- missing-report detection, owner void functions, atomic rental create/renew.
-- All are SECURITY INVOKER (RLS applies) unless stated; void functions are SECURITY DEFINER with a fixed
-- search_path and an explicit owner check.
-- Alert calculations (visa/passport/licence/cheque-due) are computed by backend services in later steps.

-- Reconciliation: total received, difference (= "not yet received"), check label.
create or replace view public.v_daily_reports_reconciled with (security_invoker = true) as
select r.*,
       (r.cash_received + r.pos_amount + r.bank_transfer + r.link_payment)                  as total_received,
       r.total_sales - (r.cash_received + r.pos_amount + r.bank_transfer + r.link_payment)  as difference,
       case when r.total_sales - (r.cash_received + r.pos_amount + r.bank_transfer + r.link_payment) = 0
            then 'Matches' else 'Diff' end                                                  as check_label
from public.daily_reports r
where r.voided_at is null;

-- Balance engine. PDF formulas (Technical Summary section 4). VERIFY against alsafa_supabase_schema.sql app_balances().
-- Flows count when dated on/after the tracking start (opening date + 1) and on/before p_as_of.
-- Voided rows are excluded. Owner only.
create or replace function public.app_balances(p_as_of date default null)
returns table (
  tracking_start  date,
  balance_date    date,
  cash_now        numeric,
  enbd_now        numeric,
  adcb_now        numeric,
  total_cash_bank numeric,
  savings_total   numeric,
  pos_pending     numeric
)
language plpgsql stable set search_path = public, pg_temp
as $$
declare
  ob       public.opening_balances%rowtype;
  asof     date;
  start_d  date;
  v_cash   numeric;
  v_enbd   numeric;
  v_adcb   numeric;
  v_sav    numeric;
  v_dr_cash numeric; v_dr_exp numeric; v_dr_bank numeric; v_dr_sav numeric;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  select * into ob from public.opening_balances where id = 1;
  if not found then
    raise exception 'opening balances are not set' using errcode = 'no_data_found';
  end if;
  asof    := coalesce(p_as_of, app.dubai_today());
  start_d := ob.as_of_date + 1;

  select coalesce(sum(cash_received), 0), coalesce(sum(shop_expenses), 0),
         coalesce(sum(pos_amount + bank_transfer + link_payment), 0), coalesce(sum(shop_savings), 0)
    into v_dr_cash, v_dr_exp, v_dr_bank, v_dr_sav
    from public.daily_reports
   where voided_at is null and report_date between start_d and asof;

  v_cash := (select coalesce(sum(amount), 0) from public.opening_branch_cash)
            + v_dr_cash - v_dr_exp
            - (select coalesce(sum(amount), 0) from public.head_office_expenses
                where voided_at is null and paid_from = 'Cash received'
                  and expense_date between start_d and asof);

  v_enbd := ob.enbd_balance
            + case when ob.receipts_bank = 'ENBD' then v_dr_bank else 0 end
            - (select coalesce(sum(amount), 0) from public.head_office_expenses
                where voided_at is null and paid_from = 'ENBD' and expense_date between start_d and asof)
            - (select coalesce(sum(amount), 0) from public.pdc_cheques
                where status = 'Cleared' and bank = 'ENBD' and cheque_date between start_d and asof);

  v_adcb := ob.adcb_balance
            + case when ob.receipts_bank = 'ADCB' then v_dr_bank else 0 end
            - (select coalesce(sum(amount), 0) from public.head_office_expenses
                where voided_at is null and paid_from = 'ADCB' and expense_date between start_d and asof)
            - (select coalesce(sum(amount), 0) from public.pdc_cheques
                where status = 'Cleared' and bank = 'ADCB' and cheque_date between start_d and asof);

  v_sav := ob.savings_brought_forward + v_dr_sav
           + (select coalesce(sum(amount), 0) from public.head_office_expenses
               where voided_at is null and is_saving and expense_date between start_d and asof);

  return query select start_d, asof, v_cash, v_enbd, v_adcb, v_cash + v_enbd + v_adcb, v_sav, ob.pos_pending;
end $$;

-- Missing-report detection (RLS applies: a branch user only ever sees their own branch).
create or replace function public.missing_report_branches(p_date date)
returns table (branch_id uuid, branch_name text)
language sql stable set search_path = public, pg_temp
as $$
  select b.id, b.name
    from public.branches b
   where b.is_active
     and not exists (select 1 from public.daily_reports r
                      where r.branch_id = b.id and r.report_date = p_date and r.voided_at is null)
   order by b.sort_order
$$;

-- Month mode: (days in range x active branches) - reports received. Owner only.
create or replace function public.missing_report_count(p_from date, p_to date)
returns integer
language plpgsql stable set search_path = public, pg_temp
as $$
declare n_branches integer; n_reports integer; n_days integer;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if p_to < p_from then return 0; end if;
  n_days := (p_to - p_from) + 1;
  select count(*) into n_branches from public.branches where is_active;
  select count(*) into n_reports from public.daily_reports
   where voided_at is null and report_date between p_from and p_to;
  return n_days * n_branches - n_reports;
end $$;

-- Owner corrections: void instead of delete (decision D4 pending; unused until approved).
create or replace function public.void_daily_report(p_id uuid, p_reason text)
returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if p_reason is null or btrim(p_reason) = '' then
    raise exception 'a void reason is required' using errcode = 'check_violation';
  end if;
  perform set_config('app.audit_reason', p_reason, true);
  update public.daily_reports
     set voided_at = now(), voided_by = auth.uid(), void_reason = p_reason
   where id = p_id and voided_at is null;
  if not found then
    raise exception 'daily report % not found or already voided', p_id using errcode = 'no_data_found';
  end if;
end $$;

create or replace function public.void_head_office_expense(p_id uuid, p_reason text)
returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if p_reason is null or btrim(p_reason) = '' then
    raise exception 'a void reason is required' using errcode = 'check_violation';
  end if;
  perform set_config('app.audit_reason', p_reason, true);
  update public.head_office_expenses
     set voided_at = now(), voided_by = auth.uid(), void_reason = p_reason
   where id = p_id and voided_at is null;
  if not found then
    raise exception 'expense % not found or already voided', p_id using errcode = 'no_data_found';
  end if;
end $$;

-- Atomic agreement + cheque creation. p_cheques: [{"cheque_no","bank","cheque_date","amount"}, ...]
-- The backend computes the split (Step 10); the database verifies count (1-12) and that the total equals annual rent.
create or replace function public.create_rental_agreement(
  p_branch_id uuid, p_landlord text, p_unit text, p_start_date date, p_end_date date,
  p_annual_rent numeric, p_cheques jsonb, p_renewed_from_id uuid default null)
returns uuid
language plpgsql set search_path = public, pg_temp
as $$
declare
  v_id uuid; v_n integer; v_sum numeric;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if p_cheques is null or jsonb_typeof(p_cheques) <> 'array' then
    raise exception 'p_cheques must be a JSON array' using errcode = 'invalid_parameter_value';
  end if;
  v_n := jsonb_array_length(p_cheques);
  if v_n < 1 or v_n > 12 then
    raise exception 'number of cheques must be between 1 and 12 (got %)', v_n using errcode = 'check_violation';
  end if;
  select coalesce(sum((c ->> 'amount')::numeric), 0) into v_sum from jsonb_array_elements(p_cheques) c;
  if v_sum <> p_annual_rent then
    raise exception 'cheque total % does not equal annual rent %', v_sum, p_annual_rent
      using errcode = 'check_violation';
  end if;

  insert into public.rental_agreements (branch_id, landlord, unit, start_date, end_date, annual_rent, renewed_from_id)
  values (p_branch_id, p_landlord, p_unit, p_start_date, p_end_date, p_annual_rent, p_renewed_from_id)
  returning id into v_id;

  insert into public.pdc_cheques (agreement_id, cheque_no, bank, cheque_date, amount, status)
  select v_id, c ->> 'cheque_no', c ->> 'bank', (c ->> 'cheque_date')::date, (c ->> 'amount')::numeric, 'Pending'
    from jsonb_array_elements(p_cheques) c;
  return v_id;
end $$;

-- Atomic renewal: PDF rules -- new start = old end + 1 day, new end = old end + 1 year, same rent and cheque count,
-- all new cheques Pending. History preserved: the old agreement and its cheques are kept (status becomes 'Renewed').
create or replace function public.renew_rental_agreement(p_agreement_id uuid, p_cheques jsonb)
returns uuid
language plpgsql set search_path = public, pg_temp
as $$
declare
  old_ra public.rental_agreements%rowtype; v_old_n integer; v_new_id uuid;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  select * into old_ra from public.rental_agreements where id = p_agreement_id for update;
  if not found then
    raise exception 'agreement % not found', p_agreement_id using errcode = 'no_data_found';
  end if;
  if old_ra.status <> 'Active' then
    raise exception 'only an Active agreement can be renewed (status is %)', old_ra.status
      using errcode = 'check_violation';
  end if;
  select count(*) into v_old_n from public.pdc_cheques where agreement_id = p_agreement_id;
  if p_cheques is null or jsonb_typeof(p_cheques) <> 'array' or jsonb_array_length(p_cheques) <> v_old_n then
    raise exception 'renewal must have the same number of cheques as the original (%)', v_old_n
      using errcode = 'check_violation';
  end if;
  v_new_id := public.create_rental_agreement(
      old_ra.branch_id, old_ra.landlord, old_ra.unit,
      old_ra.end_date + 1, (old_ra.end_date + interval '1 year')::date,
      old_ra.annual_rent, p_cheques, old_ra.id);
  update public.rental_agreements set status = 'Renewed' where id = old_ra.id;
  return v_new_id;
end $$;
