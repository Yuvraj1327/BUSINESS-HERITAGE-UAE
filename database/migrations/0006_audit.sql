-- 0006_audit.sql : append-only audit log written only by a SECURITY DEFINER trigger.

create table public.audit_log (
  id             bigint generated always as identity primary key,
  occurred_at    timestamptz not null default now(),
  actor_user_id  uuid,
  action         text not null,
  table_name     text not null,
  record_id      text,
  old_values     jsonb,
  new_values     jsonb,
  reason         text,
  constraint audit_action_chk check (action in ('INSERT', 'UPDATE', 'DELETE'))
);
create index audit_table_record_idx on public.audit_log (table_name, record_id);
create index audit_occurred_idx     on public.audit_log (occurred_at desc);
create index audit_actor_idx        on public.audit_log (actor_user_id);

-- Optional reason: set per transaction with set_config('app.audit_reason', '...', true).
create or replace function app.audit_row_change() returns trigger
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  j_new jsonb := case when tg_op = 'DELETE' then null else to_jsonb(new) end;
  j_old jsonb := case when tg_op = 'INSERT' then null else to_jsonb(old) end;
  j_ref jsonb := coalesce(j_new, j_old);
begin
  insert into public.audit_log (actor_user_id, action, table_name, record_id, old_values, new_values, reason)
  values (auth.uid(), tg_op, tg_table_name,
          coalesce(j_ref ->> 'id', j_ref ->> 'user_id', j_ref ->> 'branch_id'),
          j_old, j_new, nullif(current_setting('app.audit_reason', true), ''));
  return null;
end $$;

-- Tamper protection: nobody (including superusers using normal SQL) may update, delete or truncate.
create or replace function app.audit_immutable() returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_log is append-only' using errcode = 'insufficient_privilege';
end $$;
create trigger audit_no_update_delete before update or delete on public.audit_log
  for each row execute function app.audit_immutable();
create trigger audit_no_truncate before truncate on public.audit_log
  for each statement execute function app.audit_immutable();

do $$
declare t text;
begin
  foreach t in array array[
    'branches','profiles','opening_balances','opening_branch_cash','daily_reports',
    'head_office_expenses','suppliers','employees','tasks','trade_licenses',
    'rental_agreements','pdc_cheques']
  loop
    execute format(
      'create trigger %I after insert or update or delete on public.%I
         for each row execute function app.audit_row_change()', t || '_audit', t);
  end loop;
end $$;
