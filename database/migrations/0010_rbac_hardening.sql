-- 0010_rbac_hardening.sql : Step 5 corrective / additive migration. Nothing from 0001-0009 is dropped or weakened.
--   1. audit_log can also hold authorization failures (action 'ACCESS_DENIED'), written ONLY through a
--      SECURITY DEFINER function with a fixed shape (no direct INSERT grant for anyone).
--   2. profiles: nobody can change their OWN role / branch / active flag through the API (not even an owner),
--      and user_id is immutable. Operator sessions (auth.uid() is null: SQL editor, provisioning script) are unaffected.
--   3. app.can_access_branch(uuid): single SQL definition of "may this caller touch this branch".
-- RLS stays enabled everywhere; no policy is removed.

-- 1. Audit vocabulary ----------------------------------------------------------------------------------------
alter table public.audit_log drop constraint audit_action_chk;
alter table public.audit_log add constraint audit_action_chk
  check (action in ('INSERT', 'UPDATE', 'DELETE', 'ACCESS_DENIED'));

-- Records that a signed-in ERP user was refused something. Callable by `authenticated`, but:
--   * the actor is always auth.uid() (never a parameter), and only known profiles are recorded (no anon spam);
--   * module / action are truncated, detail is dropped if large; callers must never pass tokens or secrets;
--   * at most 30 events per actor per minute are stored (flood protection).
create or replace function app.log_access_denied(p_module text, p_action text, p_detail jsonb default null)
returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then return; end if;
  if not exists (select 1 from public.profiles p where p.user_id = v_uid) then return; end if;
  if (select count(*) from public.audit_log a
       where a.actor_user_id = v_uid and a.action = 'ACCESS_DENIED'
         and a.occurred_at > now() - interval '1 minute') >= 30 then
    return;
  end if;
  insert into public.audit_log (actor_user_id, action, table_name, record_id, new_values, reason)
  values (v_uid, 'ACCESS_DENIED', 'authorization', v_uid::text,
          jsonb_build_object(
            'module', left(coalesce(p_module, ''), 64),
            'action', left(coalesce(p_action, ''), 32),
            'detail', case when p_detail is null or pg_column_size(p_detail) > 1024 then '{}'::jsonb else p_detail end),
          'authorization failure');
end $$;
revoke all on function app.log_access_denied(text, text, jsonb) from public, anon, authenticated;
grant execute on function app.log_access_denied(text, text, jsonb) to authenticated;

-- 2. Self-change guard ---------------------------------------------------------------------------------------
create or replace function app.guard_profile_self_change() returns trigger
language plpgsql set search_path = public, pg_temp
as $$
begin
  if new.user_id <> old.user_id then
    raise exception 'profiles.user_id is immutable' using errcode = 'check_violation';
  end if;
  if auth.uid() is not null and auth.uid() = old.user_id
     and (new.role      is distinct from old.role
       or new.branch_id is distinct from old.branch_id
       or new.is_active is distinct from old.is_active) then
    raise exception 'you cannot change your own role, branch or active status'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end $$;
revoke all on function app.guard_profile_self_change() from public, anon, authenticated;  -- trigger function: no direct callers
create trigger profiles_guard_self_change before update on public.profiles
  for each row execute function app.guard_profile_self_change();

-- 3. Branch access helper -------------------------------------------------------------------------------------
-- True for an active owner (any branch) or an active branch user on THEIR branch. False for null, inactive, anon.
create or replace function app.can_access_branch(p_branch_id uuid) returns boolean
language sql stable security definer set search_path = public, pg_temp
as $$
  select p_branch_id is not null
     and exists (select 1 from public.profiles p
                  where p.user_id = auth.uid() and p.is_active
                    and (p.role = 'owner' or p.branch_id = p_branch_id))
$$;
revoke all on function app.can_access_branch(uuid) from public, anon, authenticated;
grant execute on function app.can_access_branch(uuid) to authenticated;
