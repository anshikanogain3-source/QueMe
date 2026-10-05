-- Private storage: buckets, object-path helpers, and storage policies.
-- Path conventions:
--   recordings: students/{student_id}/attempts/{attempt_id}/...
--   reports:    reports/{report_id}
-- No bucket is public. Signed URLs are minted by the trusted server only
-- after SQL authorization checks (see backend recordings endpoint).

insert into storage.buckets (id, name, public)
values ('recordings', 'recordings', false), ('reports', 'reports', false)
on conflict (id) do nothing;

create or replace function app.storage_student_id(obj_name text) returns uuid
language plpgsql immutable security definer set search_path = '' as $$
declare parts text[] := string_to_array(obj_name, '/');
begin
  if array_length(parts, 1) >= 4 and parts[1] = 'students' and parts[3] = 'attempts' then
    return parts[2]::uuid;
  end if;
  return null;
exception when others then
  return null;
end $$;

create or replace function app.storage_attempt_id(obj_name text) returns uuid
language plpgsql immutable security definer set search_path = '' as $$
declare parts text[] := string_to_array(obj_name, '/');
begin
  if array_length(parts, 1) >= 4 and parts[1] = 'students' and parts[3] = 'attempts' then
    return parts[4]::uuid;
  end if;
  return null;
end $$;

create or replace function app.storage_report_id(obj_name text) returns uuid
language plpgsql immutable security definer set search_path = '' as $$
declare parts text[] := string_to_array(obj_name, '/');
begin
  if array_length(parts, 1) >= 2 and parts[1] = 'reports' then
    return parts[2]::uuid;
  end if;
  return null;
exception when others then
  return null;
end $$;

create or replace function app.can_read_report_id(report_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.reports r where r.id = report_id and app.can_read_report(r)
  )
$$;

drop policy if exists recordings_read_own on storage.objects;
create policy recordings_read_own on storage.objects
  for select to authenticated
  using (bucket_id = 'recordings' and app.storage_student_id(name) = auth.uid());

drop policy if exists recordings_insert_own on storage.objects;
create policy recordings_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'recordings'
    and owner = auth.uid()
    and app.storage_student_id(name) = auth.uid()
    and app.storage_attempt_id(name) is not null
    and app.has_role('student')
  );

drop policy if exists recordings_delete_own on storage.objects;
create policy recordings_delete_own on storage.objects
  for delete to authenticated
  using (bucket_id = 'recordings' and owner = auth.uid());

drop policy if exists recordings_read_scope on storage.objects;
create policy recordings_read_scope on storage.objects
  for select to authenticated
  using (
    bucket_id = 'recordings'
    and app.storage_attempt_id(name) is not null
    and (
      app.is_admin()
      or app.can_read_student(app.attempt_student(app.storage_attempt_id(name)))
    )
  );

drop policy if exists reports_read_scope on storage.objects;
create policy reports_read_scope on storage.objects
  for select to authenticated
  using (
    bucket_id = 'reports'
    and app.storage_report_id(name) is not null
    and app.can_read_report_id(app.storage_report_id(name))
  );

drop policy if exists storage_service_all on storage.objects;
create policy storage_service_all on storage.objects
  for all to service_role using (true) with check (true);
