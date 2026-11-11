-- 0014_rentals_pdc.sql : Step 10 -- Rental Agreements and PDC cheque management.
-- Apply once, after 0013. Additive: new columns/indexes/triggers, one changed function (the cleared-cheque ledger row).
-- Cheque history is never deleted or overwritten: cleared/bounced cheques are immutable, bounced cheques are replaced
-- by a NEW linked cheque, and every change is in audit_log (triggers from 0006).

-- ---------------------------------------------------------------- rental agreements
alter table public.rental_agreements
  add column bank             text,
  add column cheque_count     smallint,
  add column first_cheque_date date,
  add column first_cheque_no  text,
  add column notes            text,
  add constraint ra_bank_chk         check (bank is null or bank in ('ENBD', 'ADCB')),
  add constraint ra_cheque_count_chk check (cheque_count is null or cheque_count between 1 and 12),
  add constraint ra_notes_len        check (notes is null or char_length(notes) <= 1000);
-- one renewal per agreement (the renewal chain is a line, never a tree)
create unique index ra_renewed_from_uq on public.rental_agreements (renewed_from_id) where renewed_from_id is not null;

-- ---------------------------------------------------------------- cheques
alter table public.pdc_cheques
  add column notes        text,
  add column cleared_on   date,
  add column bounced_on   date,
  add column bounced_at   timestamptz,
  add column cleared_by   uuid,
  add column bounced_by   uuid,
  add column replaces_id  uuid references public.pdc_cheques (id) on delete restrict,
  add column client_key   uuid;

update public.pdc_cheques set cleared_on = (cleared_at at time zone 'Asia/Dubai')::date where status = 'Cleared';

alter table public.pdc_cheques
  add constraint pdc_notes_len       check (notes is null or char_length(notes) <= 500),
  add constraint pdc_cleared_on_chk  check ((status = 'Cleared') = (cleared_on is not null)),
  add constraint pdc_bounced_chk     check ((status = 'Bounced') = (bounced_on is not null and bounced_at is not null)),
  add constraint pdc_replaces_self   check (replaces_id is null or replaces_id <> id);
-- a bounced cheque is replaced at most once; the replacement chain keeps the original bounced record
create unique index pdc_replaces_uq   on public.pdc_cheques (replaces_id) where replaces_id is not null;
create unique index pdc_client_key_uq on public.pdc_cheques (client_key) where client_key is not null;
-- a physical cheque (bank + number) exists once; bounced numbers are never reused
create unique index pdc_bank_no_uq    on public.pdc_cheques (bank, lower(btrim(cheque_no)));
create index pdc_date_idx             on public.pdc_cheques (cheque_date);

-- status bookkeeping: business dates default to Dubai today and may not be in the future
create or replace function app.pdc_before() returns trigger
language plpgsql
as $$
declare
  today date := app.dubai_today();
begin
  if new.status = 'Cleared' then
    new.cleared_at := coalesce(new.cleared_at, now());
    new.cleared_on := coalesce(new.cleared_on, today);
    new.cleared_by := coalesce(new.cleared_by, auth.uid());
    if new.cleared_on > today then
      raise exception 'the cleared date cannot be in the future (Dubai date)' using errcode = 'check_violation';
    end if;
  else
    new.cleared_at := null; new.cleared_on := null; new.cleared_by := null;
  end if;
  if new.status = 'Bounced' then
    new.bounced_at := coalesce(new.bounced_at, now());
    new.bounced_on := coalesce(new.bounced_on, today);
    new.bounced_by := coalesce(new.bounced_by, auth.uid());
    if new.bounced_on > today then
      raise exception 'the bounced date cannot be in the future (Dubai date)' using errcode = 'check_violation';
    end if;
  else
    new.bounced_at := null; new.bounced_on := null; new.bounced_by := null;
  end if;
  return new;
end $$;

-- history guard: cleared and bounced cheques are final; nothing is ever deleted
create or replace function app.pdc_guard() returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'cheque records are never deleted' using errcode = 'check_violation';
  end if;
  if old.status in ('Cleared', 'Bounced') and (
       new.status is distinct from old.status or new.cheque_no is distinct from old.cheque_no
       or new.bank is distinct from old.bank or new.cheque_date is distinct from old.cheque_date
       or new.amount is distinct from old.amount or new.agreement_id is distinct from old.agreement_id
       or new.replaces_id is distinct from old.replaces_id
       or new.cleared_on is distinct from old.cleared_on or new.bounced_on is distinct from old.bounced_on) then
    raise exception 'a % cheque cannot be changed; record a replacement cheque instead', lower(old.status)
      using errcode = 'check_violation';
  end if;
  if old.status = 'Pending' and new.status <> old.status and (
       new.cheque_no is distinct from old.cheque_no or new.bank is distinct from old.bank
       or new.cheque_date is distinct from old.cheque_date or new.amount is distinct from old.amount) then
    raise exception 'the cheque number, date, amount and bank cannot change while its status changes'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger pdc_guard before update on public.pdc_cheques
  for each row execute function app.pdc_guard();
create trigger pdc_no_delete before delete on public.pdc_cheques
  for each row execute function app.pdc_guard();

-- ---------------------------------------------------------------- ledger: cleared rental cheques
-- Same function and columns as 0012. Only the cheque row changed: it now carries the agreement's branch, the landlord in
-- the description, and the user/time of the CLEARING action. The cheque still counts on its cheque date, only while its
-- status is Cleared, and exactly once (one row per cheque, derived from the status, never copied).
create or replace function public.app_cash_bank_ledger(p_from date, p_to date)
returns table (
  txn_date date, txn_type text, source_table text, source_id uuid, branch_id uuid, branch_name text,
  account text, amount numeric, description text, created_by uuid, created_by_name text, created_at timestamptz)
language plpgsql stable set search_path = public, pg_temp
as $$
declare ob public.opening_balances%rowtype; start_d date;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  select * into ob from public.opening_balances where id = 1;
  if not found then
    raise exception 'opening balances are not set' using errcode = 'no_data_found';
  end if;
  start_d := ob.as_of_date + 1;
  return query
  with raw as (
    select r.report_date as d, 'Daily report cash'::text as t, 'daily_reports'::text as st, r.id as sid, r.branch_id as b,
           'Cash'::text as acc, r.cash_received as amt, 'Cash received'::text as descr, r.created_by as cb, r.created_at as ca
      from public.daily_reports r where r.voided_at is null and r.cash_received > 0
    union all
    select r.report_date, 'Shop expenses', 'daily_reports', r.id, r.branch_id, 'Cash', -r.shop_expenses,
           case when r.shop_savings > 0 then 'Shop expenses incl. savings of ' || r.shop_savings::text else 'Shop expenses' end,
           r.created_by, r.created_at
      from public.daily_reports r where r.voided_at is null and r.shop_expenses > 0
    union all
    select r.report_date, 'POS collection', 'daily_reports', r.id, r.branch_id, 'POS Pending', r.pos_amount,
           'POS card sales awaiting settlement', r.created_by, r.created_at
      from public.daily_reports r where r.voided_at is null and r.pos_amount > 0
    union all
    select r.report_date, 'Bank receipts', 'daily_reports', r.id, r.branch_id, ob.receipts_bank,
           r.bank_transfer + r.link_payment, 'Bank transfers and payment links', r.created_by, r.created_at
      from public.daily_reports r where r.voided_at is null and r.bank_transfer + r.link_payment > 0
    union all
    select h.expense_date, case when h.is_saving then 'Head office saving' else 'Head office expense' end,
           'head_office_expenses', h.id, h.branch_id,
           case h.paid_from when 'Cash received' then 'Cash' else h.paid_from end, -h.amount,
           coalesce(h.note, c.name), h.created_by, h.created_at
      from public.head_office_expenses h join public.expense_categories c on c.id = h.category_id
     where h.voided_at is null
    union all
    select e.entry_date, 'Supplier payment', 'supplier_entries', e.id, e.branch_id, e.paid_from, -e.amount,
           s.name || coalesce(' - ' || e.reference, ''), e.created_by, e.created_at
      from public.supplier_entries e join public.suppliers s on s.id = e.supplier_id
     where e.voided_at is null and e.kind = 'payment'
    union all
    select t.transfer_date, 'Transfer out', 'cash_transfers', t.id,
           case when t.from_account = 'Cash' then t.branch_id end, t.from_account, -t.amount,
           'To ' || t.to_account || coalesce(' - ' || t.reference, ''), t.created_by, t.created_at
      from public.cash_transfers t where t.voided_at is null
    union all
    select t.transfer_date, 'Transfer in', 'cash_transfers', t.id,
           case when t.to_account = 'Cash' then t.branch_id end, t.to_account, t.amount,
           'From ' || t.from_account || coalesce(' - ' || t.reference, ''), t.created_by, t.created_at
      from public.cash_transfers t where t.voided_at is null
    union all
    select p.settlement_date, 'POS settlement', 'pos_settlements', p.id, null::uuid, 'POS Pending', -p.amount,
           'Settled to ' || p.bank || coalesce(' - ' || p.reference, ''), p.created_by, p.created_at
      from public.pos_settlements p where p.voided_at is null
    union all
    select p.settlement_date, 'POS settlement', 'pos_settlements', p.id, null::uuid, p.bank, p.amount,
           'POS settlement received' || coalesce(' - ' || p.reference, ''), p.created_by, p.created_at
      from public.pos_settlements p where p.voided_at is null
    union all
    select k.cheque_date, 'Rental cheque cleared', 'pdc_cheques', k.id, ra.branch_id, k.bank, -k.amount,
           'Cheque ' || k.cheque_no || ' - ' || ra.landlord, coalesce(k.cleared_by, k.created_by), coalesce(k.cleared_at, k.created_at)
      from public.pdc_cheques k join public.rental_agreements ra on ra.id = k.agreement_id
     where k.status = 'Cleared'
  )
  select raw.d, raw.t, raw.st, raw.sid, raw.b, br.name, raw.acc, raw.amt, raw.descr, raw.cb, pr.full_name, raw.ca
    from raw
    left join public.branches br on br.id = raw.b
    left join public.profiles pr on pr.user_id = raw.cb
   where raw.d between greatest(p_from, start_d) and p_to
   order by raw.d, raw.ca, raw.t;
end $$;

revoke all on function app.pdc_guard() from public, anon, authenticated;
