-- 0015_tasks_alerts.sql : Step 11 (Task Management, centralized Alerts / Notifications). Additive.
--  * tasks: description, notes, completion stamps (maintained by a trigger), assignee must be an active user
--  * alerts: ONE table of alert occurrences (open / acknowledged / resolved). Conditions are always recomputed from the real
--    records; this table only stores the occurrence, its first/last seen time and the read / acknowledged / resolved state.
--    Existing audit triggers are NOT attached to it (syncing would flood audit_log); who read / acknowledged and when
--    is stored on the row itself, and rows are never deleted (history).

alter table public.tasks
  add column description  text,
  add column notes        text,
  add column completed_at timestamptz,
  add column completed_by uuid;
alter table public.tasks
  add constraint tasks_description_len check (description is null or char_length(description) <= 2000),
  add constraint tasks_notes_len       check (notes is null or char_length(notes) <= 2000);
-- existing Done rows: best available completion time is their last update
update public.tasks set completed_at = updated_at where status = 'Done' and completed_at is null;
alter table public.tasks add constraint tasks_completed_chk check ((status = 'Done') = (completed_at is not null));

create index tasks_branch_idx   on public.tasks (branch_id);
create index tasks_assignee_idx on public.tasks (assignee_user_id);

create or replace function app.tasks_before() returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'INSERT' then
    if new.status = 'Done' then
      new.completed_at := coalesce(new.completed_at, now());
      new.completed_by := coalesce(new.completed_by, auth.uid());
    else
      new.completed_at := null; new.completed_by := null;
    end if;
  else
    if new.status = 'Done' and old.status <> 'Done' then
      new.completed_at := now(); new.completed_by := auth.uid();
    elsif new.status = 'Done' then
      new.completed_at := old.completed_at; new.completed_by := old.completed_by;  -- completion is never rewritten
    else
      new.completed_at := null; new.completed_by := null;                          -- re-opened
    end if;
  end if;
  if new.assignee_user_id is not null
     and not exists (select 1 from public.profiles p where p.user_id = new.assignee_user_id and p.is_active) then
    raise exception 'tasks can only be assigned to an active user' using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger tasks_before before insert or update on public.tasks
  for each row execute function app.tasks_before();
revoke all on function app.tasks_before() from public, anon, authenticated;

-- ---------------------------------------------------------------- alerts
create table public.alerts (
  id              uuid primary key default gen_random_uuid(),
  alert_key       text not null,                      -- kind:record-id -> one open row per record and condition
  kind            text not null,
  module          text not null,
  severity        text not null,
  title           text not null,
  detail          text not null default '',
  record_id       text,
  branch_id       uuid,
  branch_name     text,
  due_date        date,
  href            text not null,
  first_seen_at   timestamptz not null default now(),
  last_seen_at    timestamptz not null default now(),
  resolved_at     timestamptz,                         -- the condition no longer exists
  read_at         timestamptz,
  read_by         uuid,
  acknowledged_at timestamptz,
  acknowledged_by uuid,
  constraint alerts_severity_chk check (severity in ('critical', 'warning', 'info')),
  constraint alerts_key_not_blank check (btrim(alert_key) <> ''),
  constraint alerts_ack_implies_read check (acknowledged_at is null or read_at is not null)
);
create unique index alerts_open_uq on public.alerts (alert_key) where resolved_at is null;
create index alerts_active_idx  on public.alerts (severity, due_date) where resolved_at is null and acknowledged_at is null;
create index alerts_history_idx on public.alerts (first_seen_at desc);
create index alerts_kind_idx    on public.alerts (kind);

alter table public.alerts enable row level security;
grant select, insert, update on public.alerts to authenticated;   -- no delete: alert history is kept
create policy alerts_select_owner on public.alerts for select to authenticated using ((select app.is_owner()));
create policy alerts_insert_owner on public.alerts for insert to authenticated with check ((select app.is_owner()));
create policy alerts_update_owner on public.alerts for update to authenticated
  using ((select app.is_owner())) with check ((select app.is_owner()));
