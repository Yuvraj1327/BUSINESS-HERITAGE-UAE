-- 0005_operations_tables.sql : employees, tasks, trade_licenses, rental_agreements, pdc_cheques.

create table public.employees (
  id               uuid primary key default gen_random_uuid(),
  full_name        text not null,
  branch_id        uuid not null references public.branches (id) on delete restrict,
  role_title       text,
  monthly_salary   numeric(14,2) not null default 0,
  visa_expiry      date,
  passport_expiry  date,
  status           text not null default 'Active',
  leave_start      date,
  visa_cancelled   boolean not null default false,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  created_by       uuid default auth.uid(),
  updated_by       uuid,
  constraint employees_name_not_blank check (btrim(full_name) <> ''),
  constraint employees_salary_nonneg  check (monthly_salary >= 0),
  constraint employees_status_chk     check (status in ('Active', 'Leave')),
  constraint employees_leave_chk      check ((status = 'Leave') = (leave_start is not null))
);
comment on table public.employees is 'Owner-only. Passport and Emirates ID numbers are intentionally NOT stored.';
create index employees_branch_idx   on public.employees (branch_id);
create index employees_status_idx   on public.employees (status);
create index employees_visa_idx     on public.employees (visa_expiry);
create index employees_passport_idx on public.employees (passport_expiry);

create or replace function app.employee_validate() returns trigger
language plpgsql
as $$
begin
  if new.status = 'Leave'
     and (tg_op = 'INSERT' or new.leave_start is distinct from old.leave_start)
     and new.leave_start > app.dubai_today() then
    raise exception 'leave_start % is in the future', new.leave_start using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger employee_validate before insert or update on public.employees
  for each row execute function app.employee_validate();

create table public.tasks (
  id                uuid primary key default gen_random_uuid(),
  title             text not null,
  branch_id         uuid references public.branches (id) on delete restrict,   -- null = All
  assignee_user_id  uuid references public.profiles (user_id) on delete restrict,  -- null = Unassigned
  due_date          date,
  status            text not null default 'To Do',
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  created_by        uuid default auth.uid(),
  updated_by        uuid,
  constraint tasks_title_not_blank check (btrim(title) <> ''),
  constraint tasks_status_chk check (status in ('To Do', 'In Progress', 'Done'))
);
create index tasks_status_due_idx on public.tasks (status, due_date);

create table public.trade_licenses (
  id           uuid primary key default gen_random_uuid(),
  branch_id    uuid not null references public.branches (id) on delete restrict,
  license_no   text not null,
  authority    text,
  expiry_date  date not null,
  renewal_fee  numeric(14,2) not null default 0,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  created_by   uuid default auth.uid(),
  updated_by   uuid,
  constraint trade_licenses_no_not_blank check (btrim(license_no) <> ''),
  constraint trade_licenses_fee_nonneg check (renewal_fee >= 0)
);
create index trade_licenses_expiry_idx on public.trade_licenses (expiry_date);
create index trade_licenses_branch_idx on public.trade_licenses (branch_id);

create table public.rental_agreements (
  id               uuid primary key default gen_random_uuid(),
  branch_id        uuid not null references public.branches (id) on delete restrict,
  landlord         text not null,
  unit             text,
  start_date       date not null,
  end_date         date not null,
  annual_rent      numeric(14,2) not null,
  status           text not null default 'Active',
  renewed_from_id  uuid references public.rental_agreements (id) on delete restrict,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  created_by       uuid default auth.uid(),
  updated_by       uuid,
  constraint ra_landlord_not_blank check (btrim(landlord) <> ''),
  constraint ra_dates_chk  check (end_date > start_date),
  constraint ra_rent_pos   check (annual_rent > 0),
  constraint ra_status_chk check (status in ('Active', 'Renewed', 'Terminated'))
);
create index ra_branch_idx on public.rental_agreements (branch_id);
create index ra_end_idx    on public.rental_agreements (end_date);

create table public.pdc_cheques (
  id            uuid primary key default gen_random_uuid(),
  agreement_id  uuid not null references public.rental_agreements (id) on delete restrict,
  cheque_no     text not null,
  bank          text not null,
  cheque_date   date not null,
  amount        numeric(14,2) not null,
  status        text not null default 'Pending',
  cleared_at    timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid default auth.uid(),
  updated_by    uuid,
  constraint pdc_no_not_blank check (btrim(cheque_no) <> ''),
  constraint pdc_bank_chk     check (bank in ('ENBD', 'ADCB')),
  constraint pdc_status_chk   check (status in ('Pending', 'Cleared', 'Bounced')),
  constraint pdc_amount_pos   check (amount > 0),
  constraint pdc_cleared_chk  check ((status = 'Cleared') = (cleared_at is not null)),
  constraint pdc_no_per_agreement_uq unique (agreement_id, cheque_no)
);
create index pdc_status_date_idx on public.pdc_cheques (status, cheque_date);
create index pdc_agreement_idx   on public.pdc_cheques (agreement_id);

create or replace function app.pdc_before() returns trigger
language plpgsql
as $$
begin
  if new.status = 'Cleared' then
    new.cleared_at := coalesce(new.cleared_at, now());
  else
    new.cleared_at := null;
  end if;
  return new;
end $$;
create trigger pdc_before before insert or update on public.pdc_cheques
  for each row execute function app.pdc_before();

create trigger employees_touch before update on public.employees for each row execute function app.touch_row();
create trigger tasks_touch before update on public.tasks for each row execute function app.touch_row();
create trigger trade_licenses_touch before update on public.trade_licenses for each row execute function app.touch_row();
create trigger ra_touch before update on public.rental_agreements for each row execute function app.touch_row();
create trigger pdc_touch before update on public.pdc_cheques for each row execute function app.touch_row();
