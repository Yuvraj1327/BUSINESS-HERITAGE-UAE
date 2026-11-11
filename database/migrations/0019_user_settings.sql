-- 0019_user_settings.sql : Settings section (my profile, preferences, profile photos). Additive only.
--   * profiles.phone, profiles.avatar_path: self-editable contact data. RLS on profiles stays owner-only for writes;
--     app.update_own_profile() lets a user change ONLY these three of THEIR OWN columns (full_name, phone, avatar_path).
--     Role, branch and active status can never be changed through it (and the 0010 guard trigger still applies).
--   * public.user_preferences: one row per user (theme, language, date format, timezone, notification choices).
--     Kept out of `profiles` on purpose so that changing the theme does not write to the audited profiles table.
--     RLS: a user reads and writes only their own row, and only while their profile is active.
--   * Storage bucket `avatars` (private, 2 MB, jpeg/png/webp). Object paths must be '<user id>/avatar-<uuid>.<ext>':
--     a user manages only objects in their own folder, an active owner may read all of them.

alter table public.profiles
  add column phone       text,
  add column avatar_path text;

alter table public.profiles
  add constraint profiles_phone_chk
    check (phone is null or phone ~ '^\+?[0-9 ()-]{7,20}$'),
  add constraint profiles_avatar_path_chk
    check (avatar_path is null
           or avatar_path ~ ('^' || user_id::text || '/avatar-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|png|webp)$'));

create or replace function app.update_own_profile(p_full_name text, p_phone text, p_avatar_path text) returns void
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if auth.uid() is null then
    raise exception 'not authenticated' using errcode = 'insufficient_privilege';
  end if;
  update public.profiles
     set full_name   = btrim(p_full_name),
         phone       = nullif(btrim(p_phone), ''),
         avatar_path = p_avatar_path,
         updated_at  = now(),
         updated_by  = auth.uid()
   where user_id = auth.uid() and is_active;
  if not found then
    raise exception 'no active profile' using errcode = 'insufficient_privilege';
  end if;
end $$;
revoke all on function app.update_own_profile(text, text, text) from public, anon, authenticated;
grant execute on function app.update_own_profile(text, text, text) to authenticated;

-- Preferences ---------------------------------------------------------------------------------------------------
create table public.user_preferences (
  user_id     uuid primary key references public.profiles (user_id) on delete cascade,
  preferences jsonb not null default '{}'::jsonb,
  updated_at  timestamptz not null default now(),
  constraint user_preferences_object_chk check (jsonb_typeof(preferences) = 'object'),
  constraint user_preferences_size_chk check (pg_column_size(preferences) <= 2048)
);
alter table public.user_preferences enable row level security;
revoke all on public.user_preferences from public, anon, authenticated;
grant select, insert, update on public.user_preferences to authenticated;   -- own row only, via RLS below

create policy user_preferences_select_own on public.user_preferences for select to authenticated
  using (user_id = (select auth.uid()) and (select app.user_role()) is not null);
create policy user_preferences_insert_own on public.user_preferences for insert to authenticated
  with check (user_id = (select auth.uid()) and (select app.user_role()) is not null);
create policy user_preferences_update_own on public.user_preferences for update to authenticated
  using (user_id = (select auth.uid()) and (select app.user_role()) is not null)
  with check (user_id = (select auth.uid()) and (select app.user_role()) is not null);

-- Profile photos (Supabase Storage). Skipped where Storage does not exist (the plain-Postgres test database).
do $storage$
begin
  if to_regclass('storage.buckets') is null or to_regclass('storage.objects') is null then
    return;
  end if;

  insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
  values ('avatars', 'avatars', false, 2097152, array['image/jpeg', 'image/png', 'image/webp'])
  on conflict (id) do update
    set public = false, file_size_limit = 2097152,
        allowed_mime_types = array['image/jpeg', 'image/png', 'image/webp'];

  execute $p$create policy avatars_select_own on storage.objects for select to authenticated
    using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
           and (select app.user_role()) is not null)$p$;
  execute $p$create policy avatars_select_owner on storage.objects for select to authenticated
    using (bucket_id = 'avatars' and (select app.is_owner()))$p$;
  execute $p$create policy avatars_insert_own on storage.objects for insert to authenticated
    with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
                and name ~ '^[0-9a-f-]{36}/avatar-[0-9a-f-]{36}\.(jpg|png|webp)$'
                and (select app.user_role()) is not null)$p$;
  execute $p$create policy avatars_update_own on storage.objects for update to authenticated
    using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
           and (select app.user_role()) is not null)
    with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text)$p$;
  execute $p$create policy avatars_delete_own on storage.objects for delete to authenticated
    using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
           and (select app.user_role()) is not null)$p$;
end
$storage$;
