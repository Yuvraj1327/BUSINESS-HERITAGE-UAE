-- 0012_finance_ledgers.sql : Step 8 (finance management). Additive except `create or replace` of app_balances().
-- Adds what the approved model lacked and the Step 8 brief requires (see docs/finance/STEP8_FINANCE.md):
--   * supplier_entries   : supplier dues + payments ledger (decision D5: no overwriting of amount_owed)
--   * pos_settlements    : POS pending -> bank settlements (decision D19)
--   * cash_transfers     : traceable cash/bank movements (decision D20, pending owner confirmation)
--   * suppliers.notes, head_office_expenses.client_key / corrects_id
--   * app_cash_bank_ledger(), app_branch_cash(), v_supplier_outstanding, void functions
--   * app_balances() now derives every account from the ledger so balances, history and dashboard can never disagree.
-- Nothing is seeded and no existing row is modified.

alter table public.suppliers add column if not exists notes text;
create unique index if not exists suppliers_name_uq on public.suppliers (lower(btrim(name)));

alter table public.head_office_expenses add column if not exists client_key uuid;
alter table public.head_office_expenses add column if not exists corrects_id uuid references public.head_office_expenses (id);
create unique index if not exists hoe_client_key_uq on public.head_office_expenses (client_key) where client_key is not null;

-- ------------------------------------------------------------------------------------------------ tables
create table public.supplier_entries (
  id            uuid primary key default gen_random_uuid(),
  supplier_id   uuid not null references public.suppliers (id) on delete restrict,
  entry_date    date not null,
  kind          text not null,
  amount        numeric(14,2) not null,
  paid_from     text,
  branch_id     uuid references public.branches (id) on delete restrict,  -- optional: which branch's cash paid
  reference     text,
  note          text,
  client_key    uuid,
  voided_at     timestamptz,
  voided_by     uuid,
  void_reason   text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid default auth.uid(),
  updated_by    uuid,
  constraint se_kind_chk check (kind in ('due', 'payment')),
  constraint se_amount_pos check (amount > 0),
  constraint se_paid_from_chk check (
    (kind = 'payment' and paid_from in ('Cash', 'ENBD', 'ADCB')) or (kind = 'due' and paid_from is null)),
  constraint se_branch_cash_only check (branch_id is null or paid_from = 'Cash'),
  constraint se_void_pair_chk check ((voided_at is null) = (void_reason is null))
);
create index se_supplier_idx on public.supplier_entries (supplier_id, entry_date);
create index se_date_idx on public.supplier_entries (entry_date);
create unique index se_client_key_uq on public.supplier_entries (client_key) where client_key is not null;

create table public.pos_settlements (
  id             uuid primary key default gen_random_uuid(),
  settlement_date date not null,
  bank           text not null,
  amount         numeric(14,2) not null,
  reference      text,
  note           text,
  client_key     uuid,
  voided_at      timestamptz,
  voided_by      uuid,
  void_reason    text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  created_by     uuid default auth.uid(),
  updated_by     uuid,
  constraint ps_bank_chk check (bank in ('ENBD', 'ADCB')),
  constraint ps_amount_pos check (amount > 0),
  constraint ps_void_pair_chk check ((voided_at is null) = (void_reason is null))
);
create index ps_date_idx on public.pos_settlements (settlement_date);
create unique index ps_client_key_uq on public.pos_settlements (client_key) where client_key is not null;

create table public.cash_transfers (
  id             uuid primary key default gen_random_uuid(),
  transfer_date  date not null,
  from_account   text not null,
  to_account     text not null,
  branch_id      uuid references public.branches (id) on delete restrict,  -- the branch whose cash is involved
  amount         numeric(14,2) not null,
  reference      text,
  note           text,
  client_key     uuid,
  voided_at      timestamptz,
  voided_by      uuid,
  void_reason    text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  created_by     uuid default auth.uid(),
  updated_by     uuid,
  constraint ct_accounts_chk check (from_account in ('Cash', 'ENBD', 'ADCB') and to_account in ('Cash', 'ENBD', 'ADCB')),
  constraint ct_distinct_chk check (from_account <> to_account),
  constraint ct_amount_pos check (amount > 0),
  constraint ct_branch_chk check ((branch_id is not null) = (from_account = 'Cash' or to_account = 'Cash')),
  constraint ct_void_pair_chk check ((voided_at is null) = (void_reason is null))
);
create index ct_date_idx on public.cash_transfers (transfer_date);
create unique index ct_client_key_uq on public.cash_transfers (client_key) where client_key is not null;

-- Dates: Dubai business rules enforced in the database, not only the API.
create or replace function app.finance_entry_validate() returns trigger
language plpgsql set search_path = public, pg_temp
as $$
declare d date; ob_date date;
begin
  -- to_jsonb(new) keeps this one function valid for three tables with different date columns
  d := (to_jsonb(new) ->> case tg_table_name when 'supplier_entries' then 'entry_date'
                                             when 'pos_settlements' then 'settlement_date'
                                             else 'transfer_date' end)::date;
  if d > app.dubai_today() then
    raise exception 'date % is in the future (Asia/Dubai today is %)', d, app.dubai_today()
      using errcode = 'check_violation';
  end if;
  select as_of_date into ob_date from public.opening_balances where id = 1;
  if ob_date is null then
    raise exception 'opening balances are not set' using errcode = 'no_data_found';
  end if;
  if d <= ob_date then
    raise exception 'date % is on or before the opening balance date %; tracking starts the day after', d, ob_date
      using errcode = 'check_violation';
  end if;
  return new;
end $$;

create trigger se_validate before insert on public.supplier_entries for each row execute function app.finance_entry_validate();
create trigger ps_validate before insert on public.pos_settlements for each row execute function app.finance_entry_validate();
create trigger ct_validate before insert on public.cash_transfers for each row execute function app.finance_entry_validate();
create trigger se_touch before update on public.supplier_entries for each row execute function app.touch_row();
create trigger ps_touch before update on public.pos_settlements for each row execute function app.touch_row();
create trigger ct_touch before update on public.cash_transfers for each row execute function app.touch_row();

-- Immutable amounts: rows can only be voided (through the functions below), never edited.
create or replace function app.finance_row_immutable() returns trigger
language plpgsql
as $$
begin
  if to_jsonb(new) - 'voided_at' - 'voided_by' - 'void_reason' - 'updated_at' - 'updated_by'
     is distinct from to_jsonb(old) - 'voided_at' - 'voided_by' - 'void_reason' - 'updated_at' - 'updated_by' then
    raise exception 'ledger rows cannot be edited; void and re-enter' using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger se_immutable before update on public.supplier_entries for each row execute function app.finance_row_immutable();
create trigger ps_immutable before update on public.pos_settlements for each row execute function app.finance_row_immutable();
create trigger ct_immutable before update on public.cash_transfers for each row execute function app.finance_row_immutable();

create trigger supplier_entries_audit after insert or update or delete on public.supplier_entries
  for each row execute function app.audit_row_change();
create trigger pos_settlements_audit after insert or update or delete on public.pos_settlements
  for each row execute function app.audit_row_change();
create trigger cash_transfers_audit after insert or update or delete on public.cash_transfers
  for each row execute function app.audit_row_change();

-- ------------------------------------------------------------------------------------------------ ledger
-- One row per money movement per account, signed (+ in, - out), dated on/after the tracking start.
-- Daily-report cash/expenses/collections are DERIVED here (never copied), so nothing is counted twice.
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
    select k.cheque_date, 'Rental cheque cleared', 'pdc_cheques', k.id, null::uuid, k.bank, -k.amount,
           'Cheque ' || k.cheque_no, null::uuid, k.created_at
      from public.pdc_cheques k where k.status = 'Cleared'
  )
  select raw.d, raw.t, raw.st, raw.sid, raw.b, br.name, raw.acc, raw.amt, raw.descr, raw.cb, pr.full_name, raw.ca
    from raw
    left join public.branches br on br.id = raw.b
    left join public.profiles pr on pr.user_id = raw.cb
   where raw.d between greatest(p_from, start_d) and p_to
   order by raw.d, raw.ca, raw.t;
end $$;

-- Balance engine v2 (same signature and columns as Step 2): every account = opening + signed ledger movements.
-- Change vs Step 2: POS is no longer credited to the bank on the day of sale; it sits in POS Pending until a
-- settlement is recorded (decision D19, Step 8 brief). Cash+bank total therefore excludes unsettled POS.
create or replace function public.app_balances(p_as_of date default null)
returns table (
  tracking_start date, balance_date date, cash_now numeric, enbd_now numeric, adcb_now numeric,
  total_cash_bank numeric, savings_total numeric, pos_pending numeric)
language plpgsql stable set search_path = public, pg_temp
as $$
declare
  ob public.opening_balances%rowtype; asof date; start_d date;
  v_cash numeric; v_enbd numeric; v_adcb numeric; v_pos numeric; v_sav numeric;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  select * into ob from public.opening_balances where id = 1;
  if not found then
    raise exception 'opening balances are not set' using errcode = 'no_data_found';
  end if;
  asof := coalesce(p_as_of, app.dubai_today());
  start_d := ob.as_of_date + 1;

  select (select coalesce(sum(amount), 0) from public.opening_branch_cash) + coalesce(sum(l.amount) filter (where l.account = 'Cash'), 0),
         ob.enbd_balance + coalesce(sum(l.amount) filter (where l.account = 'ENBD'), 0),
         ob.adcb_balance + coalesce(sum(l.amount) filter (where l.account = 'ADCB'), 0),
         ob.pos_pending + coalesce(sum(l.amount) filter (where l.account = 'POS Pending'), 0)
    into v_cash, v_enbd, v_adcb, v_pos
    from public.app_cash_bank_ledger(start_d, asof) l;

  v_sav := ob.savings_brought_forward
           + (select coalesce(sum(shop_savings), 0) from public.daily_reports
               where voided_at is null and report_date between start_d and asof)
           + (select coalesce(sum(amount), 0) from public.head_office_expenses
               where voided_at is null and is_saving and expense_date between start_d and asof);

  return query select start_d, asof, v_cash, v_enbd, v_adcb, v_cash + v_enbd + v_adcb, v_sav, v_pos;
end $$;

-- Branch cash: opening + ledger movements per branch; the NULL-branch row holds head-office / unattributed cash
-- movements (decision D18). Rows sum to Cash Now.
create or replace function public.app_branch_cash(p_as_of date default null)
returns table (branch_id uuid, branch_name text, sort_order integer, opening numeric, incoming numeric, outgoing numeric, closing numeric)
language plpgsql stable set search_path = public, pg_temp
as $$
declare ob public.opening_balances%rowtype; asof date; start_d date;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  select * into ob from public.opening_balances where id = 1;
  if not found then
    raise exception 'opening balances are not set' using errcode = 'no_data_found';
  end if;
  asof := coalesce(p_as_of, app.dubai_today());
  start_d := ob.as_of_date + 1;
  return query
  with l as (
    select x.branch_id as bid, sum(x.amount) filter (where x.amount > 0) as inc, -sum(x.amount) filter (where x.amount < 0) as outg
      from public.app_cash_bank_ledger(start_d, asof) x where x.account = 'Cash' group by x.branch_id),
  rows as (
    select b.id as bid, b.name as bname, b.sort_order as so, coalesce(oc.amount, 0) as op
      from public.branches b left join public.opening_branch_cash oc on oc.branch_id = b.id
    union all
    select null::uuid, 'Head office / all branches', 1000, 0::numeric)
  select rows.bid, rows.bname, rows.so, rows.op, coalesce(l.inc, 0), coalesce(l.outg, 0),
         rows.op + coalesce(l.inc, 0) - coalesce(l.outg, 0)
    from rows left join l on l.bid is not distinct from rows.bid
   order by rows.so, rows.bname;
end $$;

-- Supplier outstanding = opening (suppliers.amount_owed) + dues - payments. Voided entries ignored.
create or replace view public.v_supplier_outstanding with (security_invoker = true) as
select s.id as supplier_id,
       s.amount_owed as opening_outstanding,
       coalesce(sum(e.amount) filter (where e.kind = 'due'), 0)     as new_dues,
       coalesce(sum(e.amount) filter (where e.kind = 'payment'), 0) as payments,
       s.amount_owed
         + coalesce(sum(e.amount) filter (where e.kind = 'due'), 0)
         - coalesce(sum(e.amount) filter (where e.kind = 'payment'), 0) as outstanding
  from public.suppliers s
  left join public.supplier_entries e on e.supplier_id = s.id and e.voided_at is null
 group by s.id, s.amount_owed;

-- ------------------------------------------------------------------------------------------------ void functions
create or replace function app.void_ledger_row(p_table text, p_id uuid, p_reason text)
returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
declare n integer;
begin
  if not app.is_owner() then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if p_reason is null or btrim(p_reason) = '' then
    raise exception 'a void reason is required' using errcode = 'check_violation';
  end if;
  if p_table not in ('supplier_entries', 'pos_settlements', 'cash_transfers') then
    raise exception 'unknown ledger table' using errcode = 'invalid_parameter_value';
  end if;
  perform set_config('app.audit_reason', p_reason, true);
  execute format('update public.%I set voided_at = now(), voided_by = auth.uid(), void_reason = $1
                   where id = $2 and voided_at is null', p_table) using p_reason, p_id;
  get diagnostics n = row_count;  -- EXECUTE does not set FOUND
  if n = 0 then
    raise exception 'row % not found or already voided', p_id using errcode = 'no_data_found';
  end if;
end $$;

create or replace function public.void_supplier_entry(p_id uuid, p_reason text) returns void
language sql security definer set search_path = public, pg_temp
as $$ select app.void_ledger_row('supplier_entries', p_id, p_reason) $$;
create or replace function public.void_pos_settlement(p_id uuid, p_reason text) returns void
language sql security definer set search_path = public, pg_temp
as $$ select app.void_ledger_row('pos_settlements', p_id, p_reason) $$;
create or replace function public.void_cash_transfer(p_id uuid, p_reason text) returns void
language sql security definer set search_path = public, pg_temp
as $$ select app.void_ledger_row('cash_transfers', p_id, p_reason) $$;

-- ------------------------------------------------------------------------------------------------ privileges + RLS
revoke all on function app.void_ledger_row(text, uuid, text), app.finance_entry_validate(), app.finance_row_immutable()
  from public, anon, authenticated;
revoke all on function public.app_cash_bank_ledger(date, date), public.app_branch_cash(date),
  public.void_supplier_entry(uuid, text), public.void_pos_settlement(uuid, text), public.void_cash_transfer(uuid, text)
  from public, anon, authenticated;
grant execute on function public.app_cash_bank_ledger(date, date), public.app_branch_cash(date),
  public.void_supplier_entry(uuid, text), public.void_pos_settlement(uuid, text), public.void_cash_transfer(uuid, text)
  to authenticated;
-- app.void_ledger_row is called from SECURITY DEFINER wrappers owned by the migration role; authenticated needs usage only.
revoke all on public.supplier_entries, public.pos_settlements, public.cash_transfers, public.v_supplier_outstanding
  from public, anon, authenticated;
grant select, insert on public.supplier_entries, public.pos_settlements, public.cash_transfers to authenticated;
grant select on public.v_supplier_outstanding to authenticated;
-- head office expenses: owner correction links (corrects_id) are written on insert only
alter table public.supplier_entries enable row level security;
alter table public.pos_settlements  enable row level security;
alter table public.cash_transfers   enable row level security;
do $$
declare t text;
begin
  foreach t in array array['supplier_entries', 'pos_settlements', 'cash_transfers'] loop
    execute format('create policy %I on public.%I for select to authenticated using ((select app.is_owner()))', t || '_select_owner', t);
    execute format('create policy %I on public.%I for insert to authenticated with check ((select app.is_owner()) and voided_at is null)', t || '_insert_owner', t);
    -- voids run inside the SECURITY DEFINER function; this policy lets that update through for the owner only
    execute format('create policy %I on public.%I for update to authenticated using ((select app.is_owner())) with check ((select app.is_owner()))', t || '_update_owner', t);
  end loop;
end $$;
-- No UPDATE privilege is granted to authenticated on the ledgers (the definer functions perform the void).

comment on table public.supplier_entries is 'Supplier dues and payments ledger. Outstanding = suppliers.amount_owed (opening) + dues - payments (v_supplier_outstanding).';
comment on table public.pos_settlements  is 'Settlement of POS pending funds into a bank (decision D19).';
comment on table public.cash_transfers   is 'Cash/bank movements; each row yields a debit and a credit ledger line (decision D20 pending confirmation).';
