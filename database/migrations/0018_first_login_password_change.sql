-- 0018_first_login_password_change.sql : mandatory "change password on first login" for Owner-provisioned accounts.
-- Additive only. Stores a boolean flag, never a password or hash (those live only in Supabase Auth).
--   * profiles.must_change_password: set true when the Owner creates a Branch User with an initial password.
--   * app.complete_password_change(): lets the signed-in user clear ONLY their OWN flag (true -> false). It is called by
--     the API after Supabase Auth has accepted the new password. RLS stays owner-only for profile writes.
-- Existing profiles default to false, so current users are unaffected.

alter table public.profiles
  add column must_change_password boolean not null default false;

create or replace function app.complete_password_change() returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = 'insufficient_privilege';
  end if;
  update public.profiles set must_change_password = false
   where user_id = auth.uid() and must_change_password;
end $$;
revoke all on function app.complete_password_change() from public, anon, authenticated;
grant execute on function app.complete_password_change() to authenticated;
