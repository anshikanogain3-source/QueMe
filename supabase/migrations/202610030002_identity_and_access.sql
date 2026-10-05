-- QueMe identity, profiles, and role-elevation protection.
-- Role is authoritative in public.profiles and is NEVER read from client metadata.

create schema if not exists app;

create or replace function app.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

do $$ begin
  create type public.app_role as enum ('student','teacher','coordinator','admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.profile_status as enum ('pending','active','suspended','deactivated');
exception when duplicate_object then null; end $$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text not null default '',
  role public.app_role not null default 'student',
  status public.profile_status not null default 'pending',
  is_role_locked boolean not null default false,
  activated_at timestamptz,
  last_seen_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists profiles_email_lower_key on public.profiles (lower(email));
create index if not exists profiles_role_idx on public.profiles (role);
create index if not exists profiles_status_idx on public.profiles (status);

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at before update on public.profiles
  for each row execute function app.touch_updated_at();

-- True only when the session's database role is service_role (the trusted
-- backend). Reads the `role` setting rather than current_user, because
-- current_user is the function owner inside SECURITY DEFINER functions, and
-- rather than a JWT claim, so request payloads can never influence it.
create or replace function app.is_service_role() returns boolean
language sql stable set search_path = '' as $$
  select coalesce(current_setting('role', true), '') = 'service_role'
$$;

-- Role/status escalation guard. Only an authorized admin workflow may change them:
-- that workflow sets app.trusted_role_change = 'on' for the transaction.
create or replace function app.guard_profile_write() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if coalesce(current_setting('app.trusted_role_change', true), 'off') = 'on' then
    return new;
  end if;
  if tg_op = 'INSERT' then
    if new.role <> 'student' or new.status <> 'pending' or new.is_role_locked then
      raise exception 'privileged profiles must be created through the administrator workflow'
        using errcode = '42501';
    end if;
    return new;
  end if;
  if new.role is distinct from old.role
     or new.status is distinct from old.status
     or new.is_role_locked is distinct from old.is_role_locked then
    raise exception 'profile role/status changes require an authorized administrator workflow'
      using errcode = '42501';
  end if;
  return new;
end $$;

drop trigger if exists profiles_guard_write on public.profiles;
create trigger profiles_guard_write before insert or update on public.profiles
  for each row execute function app.guard_profile_write();

-- Delivery helpers used by every policy. security definer avoids policy recursion.
create or replace function app.current_profile_id() returns uuid
language sql stable security definer set search_path = '' as $$
  select p.id from public.profiles p where p.id = auth.uid() and p.status = 'active'
$$;

create or replace function app.current_role() returns public.app_role
language sql stable security definer set search_path = '' as $$
  select p.role from public.profiles p where p.id = auth.uid() and p.status = 'active'
$$;

create or replace function app.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin' and p.status = 'active')
$$;

create or replace function app.has_role(target public.app_role) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = target and p.status = 'active')
$$;

-- Auto-provision a pending student profile on signup. Client metadata is ignored for role.
create or replace function app.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email, full_name, role, status)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    'student',
    'pending'
  )
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function app.handle_new_user();

alter table public.profiles enable row level security;

grant usage on schema app to anon, authenticated, service_role;

-- Local test harmony only: Supabase platform owns auth.users in production.
-- The shim table used by supabase/tests needs explicit grants for RLS tests.
do $$ begin
  grant select, insert, update, delete on auth.users to authenticated, service_role;
exception when undefined_table then null; end $$;

revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (full_name) on public.profiles to authenticated;
grant select, insert, update, delete on public.profiles to service_role;
