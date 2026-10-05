-- A student may upload only beneath an attempt they own. Checking the path
-- owner alone is insufficient: otherwise a user could place an object under
-- another student's attempt UUID and make the object look associated with it.
create or replace function app.can_upload_recording_path(object_name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select app.storage_student_id(object_name) = auth.uid()
     and exists (
       select 1 from public.interview_attempts a
       where a.id = app.storage_attempt_id(object_name) and a.student_id = auth.uid()
     )
$$;

drop policy if exists recordings_insert_own on storage.objects;
create policy recordings_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'recordings'
    and owner = auth.uid()
    and app.has_role('student')
    and app.can_upload_recording_path(name)
  );
