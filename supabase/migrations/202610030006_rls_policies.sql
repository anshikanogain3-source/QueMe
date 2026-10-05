-- Row Level Security policies. Deny-by-default: anonymous users get no policies
-- at all, so they cannot access interview data. Roles are read from
-- public.profiles (never client metadata) via security-definer helpers.

create or replace function app.attempt_student(target_attempt uuid) returns uuid
language sql stable security definer set search_path = '' as $$
  select a.student_id from public.interview_attempts a where a.id = target_attempt
$$;

create or replace function app.can_read_attempt(target_attempt uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.interview_attempts a
    where a.id = target_attempt and app.can_read_student(a.student_id)
  )
$$;

create or replace function app.can_read_answer(target_answer uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.answers a
    where a.id = target_answer and app.can_read_student(a.student_id)
  )
$$;

-- Who may read a profile row: self, admin, scope-covered students,
-- a student's own teachers, and feedback authors on the student's attempts.
create or replace function app.readable_profile(target_profile uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select case
    when target_profile is null then false
    when target_profile = auth.uid() then true
    when app.is_admin() then true
    when app.has_role('teacher') and app.teaches_student(target_profile) then true
    when app.has_role('coordinator') and app.coordinator_covers_student(target_profile) then true
    when exists (
      select 1 from public.enrollments e
      join public.teacher_assignments ta on ta.class_id = e.class_id
      where e.student_id = auth.uid() and ta.teacher_id = target_profile
    ) then true
    when exists (
      select 1 from public.teacher_feedback f
      join public.interview_attempts a on a.id = f.attempt_id
      where f.teacher_id = target_profile and a.student_id = auth.uid()
    ) then true
    else false
  end
$$;

create or replace function app.can_read_report(r public.reports) returns boolean
language sql stable security definer set search_path = '' as $$
  select case
    when app.is_admin() then true
    when r.attempt_id is not null and app.can_read_attempt(r.attempt_id) then true
    when r.attempt_id is null and r.student_id = auth.uid() then true
    when r.report_type = 'class' and r.class_id is not null and (
      app.teaches_class(r.class_id)
      or app.coordinator_covers_class(r.class_id)
    ) then true
    when r.report_type = 'course' and r.course_id is not null and (
      app.coordinator_covers_course(r.course_id)
    ) then true
    when r.report_type = 'department' and r.department_id is not null and (
      app.has_role('coordinator') and exists (
        select 1 from public.coordinator_assignments ca
        where ca.coordinator_id = auth.uid()
          and ca.scope_type = 'department' and ca.department_id = r.department_id
      )
    ) then true
    else false
  end
$$;

-- Feedback visibility: teachers always see their own rows; students see a
-- row only when it belongs to a readable attempt AND is student_visible.
-- Teacher-visible attempts include internal feedback for scope holders.
create or replace function app.can_read_feedback(f public.teacher_feedback) returns boolean
language sql stable security definer set search_path = '' as $$
  select case
    when f.teacher_id = auth.uid() then true
    when not app.can_read_attempt(f.attempt_id) then false
    when f.visibility = 'student_visible' then true
    when app.is_admin() then true
    when app.has_role('teacher') and app.teaches_student(app.attempt_student(f.attempt_id)) then true
    when app.has_role('coordinator') and app.coordinator_covers_student(app.attempt_student(f.attempt_id)) then true
    else false
  end
$$;

-- ---------------------------------------------------------------- profiles
drop policy if exists profiles_read_scope on public.profiles;
create policy profiles_read_scope on public.profiles
  for select to authenticated
  using (app.readable_profile(id));

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid());

-- ------------------------------------------------- academic structure reads
drop policy if exists departments_read on public.departments;
create policy departments_read on public.departments
  for select to authenticated using (true);

drop policy if exists courses_read on public.courses;
create policy courses_read on public.courses
  for select to authenticated using (true);

drop policy if exists semesters_read on public.semesters;
create policy semesters_read on public.semesters
  for select to authenticated using (true);

drop policy if exists batches_read on public.batches;
create policy batches_read on public.batches
  for select to authenticated using (true);

drop policy if exists classes_read_scope on public.classes;
create policy classes_read_scope on public.classes
  for select to authenticated
  using (
    app.is_admin()
    or exists (select 1 from public.enrollments e where e.class_id = id and e.student_id = auth.uid())
    or app.teaches_class(id)
    or app.coordinator_covers_class(id)
  );

drop policy if exists enrollments_read_scope on public.enrollments;
create policy enrollments_read_scope on public.enrollments
  for select to authenticated
  using (
    app.is_admin()
    or student_id = auth.uid()
    or app.teaches_student(student_id)
    or app.coordinator_covers_student(student_id)
  );

drop policy if exists teacher_assignments_read_scope on public.teacher_assignments;
create policy teacher_assignments_read_scope on public.teacher_assignments
  for select to authenticated
  using (
    app.is_admin()
    or teacher_id = auth.uid()
    or app.teaches_class(class_id)
    or exists (select 1 from public.enrollments e where e.class_id = class_id and e.student_id = auth.uid())
  );

drop policy if exists coordinator_assignments_read_scope on public.coordinator_assignments;
create policy coordinator_assignments_read_scope on public.coordinator_assignments
  for select to authenticated
  using (
    app.is_admin()
    or coordinator_id = auth.uid()
    or exists (
      select 1 from public.enrollments e
      where e.student_id = auth.uid() and app.coordinator_covers_class(e.class_id)
    )
  );

-- -------------------------------------------------------- interview access
drop policy if exists interview_assignments_read_scope on public.interview_assignments;
create policy interview_assignments_read_scope on public.interview_assignments
  for select to authenticated
  using (
    app.is_admin()
    or student_id = auth.uid()
    or app.teaches_student(student_id)
    or app.coordinator_covers_student(student_id)
  );

drop policy if exists interview_attempts_read_scope on public.interview_attempts;
create policy interview_attempts_read_scope on public.interview_attempts
  for select to authenticated
  using (app.can_read_attempt(id));

drop policy if exists interview_attempts_student_write on public.interview_attempts;
create policy interview_attempts_student_write on public.interview_attempts
  for insert to authenticated
  with check (student_id = auth.uid() and app.has_role('student'));

drop policy if exists interview_attempts_student_update on public.interview_attempts;
create policy interview_attempts_student_update on public.interview_attempts
  for update to authenticated
  using (student_id = auth.uid())
  with check (student_id = auth.uid());

-- question_rubrics: NO client policies at all (service_role only, bypasses RLS).

drop policy if exists generated_questions_read_scope on public.generated_questions;
create policy generated_questions_read_scope on public.generated_questions
  for select to authenticated
  using (
    app.is_admin()
    or (attempt_id is not null and app.can_read_attempt(attempt_id))
    or (attempt_id is null and (app.has_role('teacher') or app.has_role('coordinator')))
  );

drop policy if exists interview_turns_read_scope on public.interview_turns;
create policy interview_turns_read_scope on public.interview_turns
  for select to authenticated
  using (app.can_read_attempt(attempt_id));

drop policy if exists answers_read_scope on public.answers;
create policy answers_read_scope on public.answers
  for select to authenticated
  using (app.can_read_answer(id));

drop policy if exists answers_student_write on public.answers;
create policy answers_student_write on public.answers
  for insert to authenticated
  with check (student_id = auth.uid() and app.has_role('student'));

drop policy if exists answers_student_update on public.answers;
create policy answers_student_update on public.answers
  for update to authenticated
  using (student_id = auth.uid())
  with check (student_id = auth.uid());

drop policy if exists answers_teacher_insert on public.answers;
create policy answers_teacher_insert on public.answers
  for insert to authenticated
  with check (
    app.has_role('teacher')
    and app.teaches_student(student_id)
  );

drop policy if exists transcripts_read_scope on public.transcripts;
create policy transcripts_read_scope on public.transcripts
  for select to authenticated
  using (app.can_read_answer(answer_id));

drop policy if exists recording_assets_read_scope on public.recording_assets;
create policy recording_assets_read_scope on public.recording_assets
  for select to authenticated
  using (app.can_read_attempt(attempt_id));

drop policy if exists recording_assets_student_write on public.recording_assets;
create policy recording_assets_student_write on public.recording_assets
  for insert to authenticated
  with check (owner_id = auth.uid() and app.has_role('student'));

drop policy if exists recording_assets_student_manage on public.recording_assets;
create policy recording_assets_student_manage on public.recording_assets
  for update to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

drop policy if exists audio_segments_read_scope on public.audio_segments;
create policy audio_segments_read_scope on public.audio_segments
  for select to authenticated
  using (
    (answer_id is not null and app.can_read_answer(answer_id))
    or exists (
      select 1 from public.recording_assets r
      where r.id = recording_id and app.can_read_attempt(r.attempt_id)
    )
  );

drop policy if exists answer_evaluations_read_scope on public.answer_evaluations;
create policy answer_evaluations_read_scope on public.answer_evaluations
  for select to authenticated
  using (app.can_read_answer(answer_id));

drop policy if exists speech_metrics_read_scope on public.speech_metrics;
create policy speech_metrics_read_scope on public.speech_metrics
  for select to authenticated
  using (app.can_read_answer(answer_id));

-- Reminder: clients hold NO insert/update/delete grants on
-- answer_evaluations or speech_metrics, so no write policies exist.

drop policy if exists reports_read_scope on public.reports;
create policy reports_read_scope on public.reports
  for select to authenticated
  using (app.can_read_report(reports));

drop policy if exists teacher_feedback_read_scope on public.teacher_feedback;
create policy teacher_feedback_read_scope on public.teacher_feedback
  for select to authenticated
  using (app.can_read_feedback(teacher_feedback));

drop policy if exists teacher_feedback_teacher_write on public.teacher_feedback;
create policy teacher_feedback_teacher_write on public.teacher_feedback
  for insert to authenticated
  with check (teacher_id = auth.uid() and app.has_role('teacher'));

drop policy if exists teacher_feedback_teacher_update on public.teacher_feedback;
create policy teacher_feedback_teacher_update on public.teacher_feedback
  for update to authenticated
  using (teacher_id = auth.uid())
  with check (teacher_id = auth.uid());

drop policy if exists consent_records_read_scope on public.consent_records;
create policy consent_records_read_scope on public.consent_records
  for select to authenticated
  using (
    app.is_admin()
    or student_id = auth.uid()
    or app.teaches_student(student_id)
    or app.coordinator_covers_student(student_id)
  );

drop policy if exists consent_records_student_insert on public.consent_records;
create policy consent_records_student_insert on public.consent_records
  for insert to authenticated
  with check (student_id = auth.uid() and app.has_role('student'));

drop policy if exists audit_events_read_admin on public.audit_events;
create policy audit_events_read_admin on public.audit_events
  for select to authenticated
  using (app.is_admin());

drop policy if exists audit_events_insert_own on public.audit_events;
create policy audit_events_insert_own on public.audit_events
  for insert to authenticated
  with check (actor_id = auth.uid());


