-- 0001_foundation.sql
-- Owner: Alembic (wrapped in Step 4). Creates the private helper schema and the API database role.
-- Does NOT touch Supabase-managed schemas (auth, storage, extensions).

create schema if not exists app;
comment on schema app is 'Private helpers (RLS helper functions, trigger functions). Not exposed through the Supabase API.';

-- Business date helper: all "today" / "no future date" rules use the Dubai business timezone.
create or replace function app.dubai_today() returns date
language sql stable
as $$ select (now() at time zone 'Asia/Dubai')::date $$;

-- Role used by the FastAPI backend. NOLOGIN here on purpose: an operator sets LOGIN and a password
-- out of band (never in a migration). NOINHERIT + NOBYPASSRLS: it has no privileges of its own and
-- must `SET LOCAL ROLE authenticated` with the request's JWT claims so RLS applies to every query.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_api') then
    create role app_api nologin noinherit nobypassrls nosuperuser nocreatedb nocreaterole;
  end if;
end $$;
grant authenticated to app_api;

-- Generic trigger: maintain updated_at / updated_by.
create or replace function app.touch_row() returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  new.updated_by := auth.uid();
  return new;
end $$;
