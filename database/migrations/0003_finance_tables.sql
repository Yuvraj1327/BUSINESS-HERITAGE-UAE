-- 0003_finance_tables.sql : opening balances, suppliers, head office expenses.
-- No stored "current balance" fields: balances are derived (see 0007 app_balances()).

create table public.opening_balances (
  id                      smallint primary key default 1,
  as_of_date              date not null,
  receipts_bank           text not null,
  enbd_balance            numeric(14,2) not null default 0,
  adcb_balance            numeric(14,2) not null default 0,
  pos_pending             numeric(14,2) not null default 0,
  savings_brought_forward numeric(14,2) not null default 0,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  updated_by              uuid,
  constraint opening_balances_single_row check (id = 1),
  constraint opening_balances_bank_chk check (receipts_bank in ('ENBD', 'ADCB')),
  constraint opening_balances_nonneg check (
    enbd_balance >= 0 and adcb_balance >= 0 and pos_pending >= 0 and savings_brought_forward >= 0)
);
comment on table public.opening_balances is 'Single settings row. Tracking start date = as_of_date + 1 day. Not seeded (opening date is decision D1).';

create table public.opening_branch_cash (
  branch_id   uuid primary key references public.branches (id) on delete restrict,
  amount      numeric(14,2) not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  updated_by  uuid,
  constraint opening_branch_cash_nonneg check (amount >= 0)
);

create table public.suppliers (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  category      text,
  payment_terms text,
  amount_owed   numeric(14,2) not null default 0,
  is_active     boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid default auth.uid(),
  updated_by    uuid,
  constraint suppliers_name_not_blank check (btrim(name) <> ''),
  constraint suppliers_owed_nonneg check (amount_owed >= 0)
);
create index suppliers_active_idx on public.suppliers (is_active);

create table public.head_office_expenses (
  id            uuid primary key default gen_random_uuid(),
  expense_date  date not null,
  branch_id     uuid references public.branches (id) on delete restrict,   -- null = All branches
  category_id   uuid not null references public.expense_categories (id) on delete restrict,
  amount        numeric(14,2) not null,
  paid_from     text not null,
  note          text,
  is_saving     boolean not null default false,
  voided_at     timestamptz,
  voided_by     uuid,
  void_reason   text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid default auth.uid() references auth.users (id) on delete restrict,
  updated_by    uuid,
  constraint hoe_amount_nonneg check (amount >= 0),
  constraint hoe_paid_from_chk check (paid_from in ('Cash received', 'ENBD', 'ADCB')),
  constraint hoe_void_pair_chk check ((voided_at is null) = (void_reason is null))
);
create index hoe_date_idx          on public.head_office_expenses (expense_date);
create index hoe_paid_from_idx     on public.head_office_expenses (paid_from, expense_date);
create index hoe_branch_idx        on public.head_office_expenses (branch_id);

create trigger opening_balances_touch before update on public.opening_balances for each row execute function app.touch_row();
create trigger opening_branch_cash_touch before update on public.opening_branch_cash for each row execute function app.touch_row();
create trigger suppliers_touch before update on public.suppliers for each row execute function app.touch_row();
create trigger hoe_touch before update on public.head_office_expenses for each row execute function app.touch_row();
