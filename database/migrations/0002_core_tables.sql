-- 0002_core_tables.sql : branches, expense_categories, profiles + RLS helper functions.

create table public.branches (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  sort_order  integer not null,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  updated_by  uuid,
  constraint branches_name_key unique (name),
  constraint branches_name_not_blank check (btrim(name) <> '')
);
create index branches_sort_order_idx on public.branches (sort_order);

create table public.expense_categories (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  constraint expense_categories_name_key unique (name),
  constraint expense_categories_name_not_blank check (btrim(name) <> '')
);

create table public.profiles (
  user_id     uuid primary key references auth.users (id) on delete restrict,
  full_name   text not null,
  role        text not null,
  branch_id   uuid references public.branches (id) on delete restrict,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  created_by  uuid,
  updated_by  uuid,
  constraint profiles_role_chk check (role in ('owner', 'branch')),
  constraint profiles_role_branch_chk check (
    (role = 'owner'  and branch_id is null) or
    (role = 'branch' and branch_id is not null)
  ),
  constraint profiles_name_not_blank check (btrim(full_name) <> '')
);
create index profiles_branch_idx on public.profiles (branch_id);

-- RLS helper functions. SECURITY DEFINER so they read profiles without triggering profiles' own RLS
-- (avoids recursion). Fixed search_path. Execution restricted in 0008. They trust only auth.uid()
-- and the stored profile -- never client-supplied role or branch values.
create or replace function app.user_role() returns text
language sql stable security definer set search_path = public, pg_temp
as $$ select p.role from public.profiles p where p.user_id = auth.uid() and p.is_active $$;

create or replace function app.branch_id() returns uuid
language sql stable security definer set search_path = public, pg_temp
as $$ select p.branch_id from public.profiles p where p.user_id = auth.uid() and p.is_active $$;

create or replace function app.is_owner() returns boolean
language sql stable security definer set search_path = public, pg_temp
as $$ select coalesce((select p.role = 'owner' from public.profiles p
                        where p.user_id = auth.uid() and p.is_active), false) $$;

-- Lock-out protection: the last active owner can never be demoted, deactivated or deleted.
create or replace function app.guard_last_owner() returns trigger
language plpgsql set search_path = public, pg_temp
as $$
begin
  if old.role = 'owner' and old.is_active
     and (tg_op = 'DELETE' or new.role <> 'owner' or not new.is_active) then
    if not exists (select 1 from public.profiles p
                    where p.role = 'owner' and p.is_active and p.user_id <> old.user_id) then
      raise exception 'cannot remove, demote or deactivate the last active owner'
        using errcode = 'check_violation';
    end if;
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end $$;

create trigger profiles_guard_last_owner before update or delete on public.profiles
  for each row execute function app.guard_last_owner();

create trigger branches_touch before update on public.branches
  for each row execute function app.touch_row();
create trigger profiles_touch before update on public.profiles
  for each row execute function app.touch_row();
