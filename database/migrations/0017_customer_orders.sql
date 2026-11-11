-- 0017_customer_orders.sql : Step 13 (Customer Order Management, pickup & delivery, order payments). Additive: new tables only,
-- no core table, formula or ledger function is changed.
--   * service_categories : configurable list (seeded with the nine approved categories)
--   * customers          : branch-scoped customer records (unique normalised mobile per branch)
--   * orders             : order header with schedule, amounts, status and payment status
--   * order_payments     : append-only payments (many per order); the ONLY writer of orders.amount_collected / payment_status
--   * order_status_history : written by a trigger on every status change (who / when / note)
-- Order revenue and order payments are NOT posted to daily_reports or to the cash & bank ledger (see docs/orders/).

create sequence public.order_no_seq as bigint start 1 minvalue 1;

-- ---------------------------------------------------------------- service categories
create table public.service_categories (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  sort_order integer not null default 0,
  is_active  boolean not null default true,
  created_at timestamptz not null default now(),
  constraint sc_name_not_blank check (btrim(name) <> '')
);
create unique index service_categories_name_uq on public.service_categories (lower(btrim(name)));
insert into public.service_categories (name, sort_order) values
  ('Wash & Fold', 1), ('Wash & Iron', 2), ('Ironing', 3), ('Dry Cleaning', 4), ('Shoes', 5),
  ('Curtains', 6), ('Carpets', 7), ('Bulky', 8), ('Other', 9)
on conflict do nothing;

-- ---------------------------------------------------------------- customers
create table public.customers (
  id         uuid primary key default gen_random_uuid(),
  branch_id  uuid not null references public.branches (id) on delete restrict,
  name       text not null,
  mobile     text not null,             -- normalised E.164, e.g. +971501234567
  whatsapp   text,
  address    text,
  area       text,
  notes      text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by uuid default auth.uid(),
  updated_by uuid,
  constraint cust_name_not_blank check (btrim(name) <> '' and char_length(name) <= 150),
  constraint cust_mobile_fmt check (mobile ~ '^\+[1-9][0-9]{7,14}$'),
  constraint cust_whatsapp_fmt check (whatsapp is null or whatsapp ~ '^\+[1-9][0-9]{7,14}$'),
  constraint cust_text_len check (coalesce(char_length(address), 0) <= 500 and coalesce(char_length(area), 0) <= 100
                                  and coalesce(char_length(notes), 0) <= 2000)
);
create unique index customers_branch_mobile_uq on public.customers (branch_id, mobile);
create index customers_name_idx on public.customers (branch_id, lower(name));

-- ---------------------------------------------------------------- orders
create table public.orders (
  id              uuid primary key default gen_random_uuid(),
  order_no        text not null default ('ORD-' || lpad(nextval('public.order_no_seq')::text, 6, '0')),
  customer_id     uuid not null references public.customers (id) on delete restrict,
  branch_id       uuid not null references public.branches (id) on delete restrict,
  order_date      date not null default app.dubai_today(),
  category_id     uuid not null references public.service_categories (id) on delete restrict,
  service_type    text not null,
  notes           text,
  pickup_at       timestamptz,
  pickup_address  text,
  delivery_at     timestamptz not null,
  delivery_address text,
  order_total     numeric(14,2) not null,
  discount        numeric(14,2) not null default 0,
  service_fee     numeric(14,2) not null default 0,
  final_payable   numeric(14,2) generated always as (order_total - discount + service_fee) stored,
  amount_collected numeric(14,2) not null default 0,
  payment_status  text not null default 'Unpaid',
  status          text not null default 'New',
  cancel_reason   text,
  cancelled_at    timestamptz,
  cancelled_by    uuid,
  delivered_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  created_by      uuid default auth.uid(),
  updated_by      uuid,
  constraint orders_no_uq unique (order_no),
  constraint orders_type_chk check (service_type in ('Standard', 'Express')),
  constraint orders_status_chk check (status in
    ('New', 'Scheduled', 'Picked Up', 'Processing', 'Ready', 'Out for Delivery', 'Delivered', 'Cancelled')),
  constraint orders_pay_chk check (payment_status in ('Unpaid', 'Partial', 'Paid', 'Refunded')),
  constraint orders_amounts_chk check (order_total >= 0 and discount >= 0 and service_fee >= 0 and amount_collected >= 0),
  constraint orders_final_pos check (order_total - discount + service_fee > 0),
  constraint orders_collected_le_final check (amount_collected <= order_total - discount + service_fee),
  constraint orders_schedule_chk check (pickup_at is null or delivery_at >= pickup_at),
  constraint orders_cancel_chk check ((status = 'Cancelled') = (cancel_reason is not null and cancelled_at is not null)),
  constraint orders_text_len check (coalesce(char_length(notes), 0) <= 2000 and coalesce(char_length(pickup_address), 0) <= 500
                                    and coalesce(char_length(delivery_address), 0) <= 500),
  client_key      uuid                        -- the browser's idempotency key: a repeated submit returns the same order
);
create index orders_branch_date_idx   on public.orders (branch_id, order_date desc);
create index orders_customer_idx      on public.orders (customer_id);
create index orders_status_idx        on public.orders (status);
create index orders_pickup_idx        on public.orders (pickup_at) where pickup_at is not null;
create index orders_delivery_idx      on public.orders (delivery_at);

-- ---------------------------------------------------------------- payments (append only)
create table public.order_payments (
  id           uuid primary key default gen_random_uuid(),
  order_id     uuid not null references public.orders (id) on delete restrict,
  branch_id    uuid not null references public.branches (id) on delete restrict,   -- copied from the order by a trigger
  payment_date date not null default app.dubai_today(),
  amount       numeric(14,2) not null,
  method       text not null,
  reference    text,
  note         text,
  client_key   uuid,                    -- the browser's idempotency key: a repeated submit cannot post twice
  created_at   timestamptz not null default now(),
  created_by   uuid default auth.uid(),
  constraint op_amount_pos check (amount > 0),
  constraint op_method_chk check (method in ('Cash', 'POS', 'Bank Transfer', 'Payment Link')),
  constraint op_text_len check (coalesce(char_length(reference), 0) <= 100 and coalesce(char_length(note), 0) <= 500)
);
create unique index orders_client_key_uq on public.orders (client_key) where client_key is not null;
create unique index op_client_key_uq on public.order_payments (client_key) where client_key is not null;
create index op_order_idx on public.order_payments (order_id);
create index op_date_idx  on public.order_payments (payment_date);

create table public.order_status_history (
  id          bigint generated always as identity primary key,
  order_id    uuid not null references public.orders (id) on delete restrict,
  branch_id   uuid not null,
  from_status text,
  to_status   text not null,
  changed_by  uuid,
  changed_at  timestamptz not null default now(),
  note        text
);
create index osh_order_idx on public.order_status_history (order_id, id);

-- ---------------------------------------------------------------- triggers
create or replace function app.customers_before() returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'UPDATE' then
    if new.branch_id is distinct from old.branch_id then
      raise exception 'a customer cannot move to another branch' using errcode = 'check_violation';
    end if;
    new.updated_by := auth.uid();
    new.updated_at := now();
  end if;
  return new;
end $$;
revoke all on function app.customers_before() from public, anon, authenticated;
create trigger customers_before before insert or update on public.customers
  for each row execute function app.customers_before();

create or replace function app.orders_before() returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
  cust_branch uuid;
  syncing boolean := coalesce(current_setting('app.order_pay_sync', true), '') = '1';
  cat_active boolean;
begin
  if tg_op = 'INSERT' then
    if new.status <> 'New' or new.amount_collected <> 0 or new.payment_status <> 'Unpaid' then
      raise exception 'a new order starts as New and Unpaid' using errcode = 'check_violation';
    end if;
    select c.branch_id into cust_branch from public.customers c where c.id = new.customer_id;
    if cust_branch is null or cust_branch <> new.branch_id then
      raise exception 'the customer does not belong to this branch' using errcode = 'check_violation';
    end if;
    select is_active into cat_active from public.service_categories where id = new.category_id;
    if not coalesce(cat_active, false) then
      raise exception 'the service category is not available' using errcode = 'check_violation';
    end if;
    if new.order_date > app.dubai_today() then
      raise exception 'the order date cannot be in the future' using errcode = 'check_violation';
    end if;
    return new;
  end if;

  -- UPDATE ---------------------------------------------------------------------------------------------
  if new.id <> old.id or new.order_no <> old.order_no or new.customer_id <> old.customer_id
     or new.branch_id <> old.branch_id or new.order_date <> old.order_date or new.created_by is distinct from old.created_by
     or new.created_at <> old.created_at then
    raise exception 'order number, customer, branch and order date cannot be changed' using errcode = 'check_violation';
  end if;
  if (new.amount_collected is distinct from old.amount_collected or new.payment_status is distinct from old.payment_status)
     and not syncing then
    raise exception 'payments are recorded through order payments only' using errcode = 'check_violation';
  end if;
  if old.status in ('Delivered', 'Cancelled')
     and (to_jsonb(new) - 'amount_collected' - 'payment_status' - 'updated_at' - 'updated_by')
         is distinct from (to_jsonb(old) - 'amount_collected' - 'payment_status' - 'updated_at' - 'updated_by') then
    raise exception 'a % order can no longer be changed', lower(old.status) using errcode = 'check_violation';
  end if;
  if new.status is distinct from old.status then
    if (old.status, new.status) not in (
         ('New', 'Scheduled'), ('Scheduled', 'Picked Up'), ('Picked Up', 'Processing'), ('Processing', 'Ready'),
         ('Ready', 'Out for Delivery'), ('Out for Delivery', 'Delivered'),
         ('New', 'Cancelled'), ('Scheduled', 'Cancelled'), ('Picked Up', 'Cancelled'),
         ('Processing', 'Cancelled'), ('Ready', 'Cancelled')) then
      raise exception 'an order cannot move from % to %', old.status, new.status using errcode = 'check_violation';
    end if;
    if new.status = 'Cancelled' then
      if new.cancel_reason is null or char_length(btrim(new.cancel_reason)) < 3 then
        raise exception 'a cancellation reason is required' using errcode = 'check_violation';
      end if;
      new.cancelled_at := now(); new.cancelled_by := auth.uid();
    end if;
    if new.status = 'Delivered' then new.delivered_at := now(); end if;
  elsif new.cancel_reason is distinct from old.cancel_reason or new.cancelled_at is distinct from old.cancelled_at then
    raise exception 'the cancellation can only be recorded when the order is cancelled' using errcode = 'check_violation';
  end if;
  if not syncing then
    new.updated_by := auth.uid();
    new.updated_at := now();
  end if;
  return new;
end $$;
revoke all on function app.orders_before() from public, anon, authenticated;
create trigger orders_before before insert or update on public.orders
  for each row execute function app.orders_before();

create or replace function app.orders_history() returns trigger
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if tg_op = 'INSERT' or new.status is distinct from old.status then
    insert into public.order_status_history (order_id, branch_id, from_status, to_status, changed_by, note)
    values (new.id, new.branch_id, case when tg_op = 'INSERT' then null else old.status end, new.status, auth.uid(),
            case when new.status = 'Cancelled' then new.cancel_reason
                 else nullif(current_setting('app.status_note', true), '') end);
  end if;
  return null;
end $$;
revoke all on function app.orders_history() from public, anon, authenticated;
create trigger orders_history after insert or update on public.orders
  for each row execute function app.orders_history();

create or replace function app.order_payments_before() returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare o public.orders%rowtype;
begin
  if tg_op <> 'INSERT' then
    raise exception 'order payments cannot be changed or deleted' using errcode = 'insufficient_privilege';
  end if;
  select * into o from public.orders where id = new.order_id for update;
  if not found then
    raise exception 'order not found' using errcode = 'check_violation';
  end if;
  if o.status = 'Cancelled' then
    raise exception 'a cancelled order cannot take payments' using errcode = 'check_violation';
  end if;
  if new.payment_date > app.dubai_today() then
    raise exception 'the payment date cannot be in the future' using errcode = 'check_violation';
  end if;
  if new.amount > o.final_payable - o.amount_collected then
    raise exception 'the payment is more than the outstanding balance' using errcode = 'check_violation';
  end if;
  new.branch_id := o.branch_id;
  return new;
end $$;
revoke all on function app.order_payments_before() from public, anon, authenticated;
create trigger order_payments_before before insert or update or delete on public.order_payments
  for each row execute function app.order_payments_before();

create or replace function app.order_payments_after() returns trigger
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  perform set_config('app.order_pay_sync', '1', true);
  update public.orders o
     set amount_collected = o.amount_collected + new.amount,
         payment_status = case when o.amount_collected + new.amount >= o.final_payable then 'Paid' else 'Partial' end
   where o.id = new.order_id;
  perform set_config('app.order_pay_sync', '0', true);
  return null;
end $$;
revoke all on function app.order_payments_after() from public, anon, authenticated;
create trigger order_payments_after after insert on public.order_payments
  for each row execute function app.order_payments_after();

create trigger customers_audit after insert or update or delete on public.customers
  for each row execute function app.audit_row_change();
create trigger orders_audit after insert or update or delete on public.orders
  for each row execute function app.audit_row_change();
create trigger order_payments_audit after insert or update or delete on public.order_payments
  for each row execute function app.audit_row_change();

-- ---------------------------------------------------------------- RLS and grants
alter table public.service_categories   enable row level security;
alter table public.customers            enable row level security;
alter table public.orders               enable row level security;
alter table public.order_payments       enable row level security;
alter table public.order_status_history enable row level security;

grant select on public.service_categories to authenticated;
grant insert, update on public.service_categories to authenticated;                 -- policies restrict writes to the owner
grant select, insert, update on public.customers to authenticated;                  -- no delete: customers keep their orders
grant select, insert, update on public.orders to authenticated;                     -- no delete: cancelled orders are kept
grant select, insert on public.order_payments to authenticated;                     -- no update / delete: payments are history
grant select on public.order_status_history to authenticated;                       -- written only by the trigger
grant usage on sequence public.order_no_seq to authenticated;

create policy sc_select on public.service_categories for select to authenticated using ((select app.user_role()) is not null);
create policy sc_write_owner on public.service_categories for insert to authenticated with check ((select app.is_owner()));
create policy sc_update_owner on public.service_categories for update to authenticated
  using ((select app.is_owner())) with check ((select app.is_owner()));

create policy cust_select on public.customers for select to authenticated using ((select app.can_access_branch(branch_id)));
create policy cust_insert on public.customers for insert to authenticated with check ((select app.can_access_branch(branch_id)));
create policy cust_update on public.customers for update to authenticated
  using ((select app.can_access_branch(branch_id))) with check ((select app.can_access_branch(branch_id)));

create policy ord_select on public.orders for select to authenticated using ((select app.can_access_branch(branch_id)));
create policy ord_insert on public.orders for insert to authenticated with check ((select app.can_access_branch(branch_id)));
create policy ord_update on public.orders for update to authenticated
  using ((select app.can_access_branch(branch_id))) with check ((select app.can_access_branch(branch_id)));

create policy op_select on public.order_payments for select to authenticated using ((select app.can_access_branch(branch_id)));
create policy op_insert on public.order_payments for insert to authenticated with check ((select app.can_access_branch(branch_id)));

create policy osh_select on public.order_status_history for select to authenticated
  using ((select app.can_access_branch(branch_id)));
