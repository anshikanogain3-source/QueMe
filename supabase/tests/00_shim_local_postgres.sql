-- Local-Postgres test shim for the QueMe Supabase migrations.
-- NOT deployed to Supabase. Provides the auth/storage surface that the
-- real Supabase platform supplies (roles, auth.users, auth.uid(), storage).
-- Loaded by supabase/tests/run_rls_tests.sh before the versioned migrations.

-- Roles mirrored from Supabase. service_role bypasses RLS like production.
do $$ begin
  create role anon nologin;
exception when duplicate_object then null; end $$;
do $$ begin
  create role authenticated nologin;
exception when duplicate_object then null; end $$;
do $$ begin
  create role service_role nologin bypassrls;
exception when duplicate_object then null; end $$;
alter role service_role with bypassrls;

create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

create or replace function auth.role() returns text
language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), current_setting('role', true))
$$;

create or replace function auth.jwt() returns jsonb
language plpgsql stable as $$
declare claims text := current_setting('request.jwt.claims', true);
begin
  return case when claims is null or claims = '' then '{}'::jsonb else claims::jsonb end;
end $$;

grant execute on function auth.uid() to anon, authenticated, service_role;
grant execute on function auth.role() to anon, authenticated, service_role;
grant execute on function auth.jwt() to anon, authenticated, service_role;

-- Minimal storage surface mirroring Supabase (buckets/objects + helpers).
create schema if not exists storage;
grant usage on schema storage to anon, authenticated, service_role;

create table if not exists storage.buckets (
  id text primary key,
  name text not null,
  public boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text not null references storage.buckets(id) on delete cascade,
  name text not null,
  owner uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_accessed_at timestamptz not null default now(),
  metadata jsonb
);
create unique index if not exists storage_objects_bucket_name_key
  on storage.objects (bucket_id, name);

create or replace function storage.foldername(name text) returns text[]
language sql immutable as $$
  select string_to_array(name, '/')
$$;

create or replace function storage.filename(name text) returns text
language sql immutable as $$
  select (string_to_array(name, '/'))[array_length(string_to_array(name, '/'), 1)]
$$;

create or replace function storage.extension(name text) returns text
language sql immutable as $$
  select split_part(storage.filename(name), '.', 2)
$$;

alter table storage.objects enable row level security;
revoke all on storage.buckets, storage.objects from anon, authenticated;
grant select on storage.buckets to anon, authenticated;
grant all on storage.buckets, storage.objects to service_role;
