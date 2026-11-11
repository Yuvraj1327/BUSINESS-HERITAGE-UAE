-- 0013_employee_compliance.sql : Step 9 (Employees, Leave, Visas & Passports, Trade Licenses). Additive; no data changes.
--  * notes + archive (void-style, D4) columns on employees and trade_licenses
--  * employees.visa_cancelled_date (when the permanent cancellation took effect)
--  * license_renewals: immutable renewal history (D9 decided by the Step 9 brief: renewal history is preserved)
--  * unique licence number among non-archived licences
-- Leave history needs no table: the append-only audit_log already stores every employees UPDATE with old/new values and reason.

alter table public.employees
  add column notes              text,
  add column visa_cancelled_date date,
  add column archived_at        timestamptz,
  add column archived_by        uuid,
  add column archive_reason     text;
alter table public.employees
  add constraint employees_notes_len     check (notes is null or char_length(notes) <= 1000),
  add constraint employees_visa_cancel_chk check (visa_cancelled_date is null or visa_cancelled),
  add constraint employees_archive_chk   check ((archived_at is null) = (archive_reason is null));
create index employees_active_idx on public.employees (branch_id) where archived_at is null;

alter table public.trade_licenses
  add column notes          text,
  add column archived_at    timestamptz,
  add column archived_by    uuid,
  add column archive_reason text;
alter table public.trade_licenses
  add constraint trade_licenses_notes_len   check (notes is null or char_length(notes) <= 1000),
  add constraint trade_licenses_archive_chk check ((archived_at is null) = (archive_reason is null));
create unique index trade_licenses_no_uq on public.trade_licenses (lower(btrim(license_no))) where archived_at is null;

-- Renewal history: one immutable row per renewal. previous/new expiry are kept so nothing is ever overwritten.
create table public.license_renewals (
  id              uuid primary key default gen_random_uuid(),
  license_id      uuid not null references public.trade_licenses (id) on delete restrict,
  renewed_on      date not null default app.dubai_today(),
  previous_expiry date not null,
  new_expiry      date not null,
  renewal_fee     numeric(14,2) not null default 0,
  note            text,
  client_key      uuid,
  created_at      timestamptz not null default now(),
  created_by      uuid default auth.uid(),
  constraint lr_fee_nonneg   check (renewal_fee >= 0),
  constraint lr_forward_chk  check (new_expiry > previous_expiry),
  constraint lr_note_len     check (note is null or char_length(note) <= 500)
);
create index lr_license_idx on public.license_renewals (license_id, created_at desc);
create unique index lr_client_key_uq on public.license_renewals (client_key) where client_key is not null;

create or replace function app.license_renewal_guard() returns trigger
language plpgsql
as $$
begin
  if tg_op in ('UPDATE', 'DELETE') then
    raise exception 'renewal history is immutable' using errcode = 'check_violation';
  end if;
  if new.renewed_on > app.dubai_today() then
    raise exception 'renewal date % is in the future', new.renewed_on using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger lr_guard before insert or update or delete on public.license_renewals
  for each row execute function app.license_renewal_guard();
create trigger license_renewals_audit after insert on public.license_renewals
  for each row execute function app.audit_row_change();

revoke all on function app.license_renewal_guard() from public, anon, authenticated;
revoke all on public.license_renewals from public, anon, authenticated;
grant select, insert on public.license_renewals to authenticated;
alter table public.license_renewals enable row level security;
create policy license_renewals_select_owner on public.license_renewals for select to authenticated using ((select app.is_owner()));
create policy license_renewals_insert_owner on public.license_renewals for insert to authenticated with check ((select app.is_owner()));

comment on table public.license_renewals is 'Immutable trade-licence renewal history (Step 9; resolves D9 for licences).';
comment on column public.employees.visa_cancelled_date is 'Date the permanent visa cancellation took effect (leave limit date or manual date).';
