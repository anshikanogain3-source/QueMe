-- Test users (fixed UUIDs so object paths are deterministic):
--   student1  11111111-1111-1111-1111-111111111111  MCA/III/A (class_a)
--   student2  22222222-2222-2222-2222-222222222222  MCA/III/A (class_a)
--   student3  33333333-3333-3333-3333-333333333333  BCA/I/B   (class_b)
--   teacher1  44444444-4444-4444-4444-444444444444  teaches class_a
--   teacher2  55555555-5555-5555-5555-555555555555  unassigned
--   coord1    66666666-6666-6666-6666-666666666666  MCA course scope
--   coord2    77777777-7777-7777-7777-777777777777  class_b scope
--   admin1    88888888-8888-8888-8888-888888888888  admin
--
-- A. identity hardening. B. student isolation. C. teacher scope.
-- D. coordinator scope. E. admin access. F. rubric secrecy.
-- G. storage paths. H. server-only writes.

select setseed(0.42);

create schema if not exists test;

-- ---------------------------------------------------------------- helpers
create or replace function test.set_test_role(
  p_role text, p_user_id uuid, p_claim_role text default 'authenticated'
) returns void
language plpgsql security invoker set search_path = '' as $$
begin
  execute format('set role %I', p_role);
  perform set_config('request.jwt.claim.sub', p_user_id::text, false);
  perform set_config('request.jwt.claim.role', p_claim_role, false);
  perform set_config('request.jwt.claims',
    jsonb_build_object('sub', p_user_id::text, 'role', p_claim_role)::text, false);
end $$;

create or replace function test.expect_denied(
  p_label text, p_sql text, p_expected text default '42501'
) returns void
language plpgsql security invoker set search_path = '' as $$
declare state_code text;
begin
  begin
    execute p_sql;
    raise exception 'expected denial (%) but statement succeeded', p_label;
  exception when others then
    get stacked diagnostics state_code = returned_sqlstate;
    if state_code not in ('42501','42502','42P01','P0001','P0002','23502','23503','23505','23514') then
      raise exception 'unexpected failure (%) sqlstate=%', p_label, state_code;
    end if;
    if p_expected = '42501' and state_code not in ('42501','42502','P0001') then
      raise exception 'expected permission denial for (%) got sqlstate=%', p_label, state_code;
    end if;
  end;
end $$;

create or replace function test.assert_count(
  p_label text, p_sql text, p_expected integer
) returns void
language plpgsql security invoker set search_path = '' as $$
declare actual integer;
begin
  execute format('select count(*) from (%s) t', p_sql) into actual;
  if actual is distinct from p_expected then
    raise exception 'count mismatch (%) expected=% actual=%', p_label, p_expected, actual;
  end if;
end $$;

-- Passes when the caller is denied outright (no grant, 42501) OR RLS hides
-- every row. Either way no data is exposed.
create or replace function test.assert_no_access(p_label text, p_sql text) returns void
language plpgsql security invoker set search_path = '' as $$
declare actual integer;
begin
  begin
    execute format('select count(*) from (%s) t', p_sql) into actual;
  exception when insufficient_privilege then
    return;
  end;
  if actual <> 0 then
    raise exception 'data exposed (%) rows=%', p_label, actual;
  end if;
end $$;

create or replace function test.assert_true(p_label text, p_condition boolean) returns void
language plpgsql security invoker set search_path = '' as $$
begin
  if p_condition is not true then
    raise exception 'assertion failed (%)', p_label;
  end if;
end $$;

-- Helpers are invoked by every test role, so grant execute broadly here;
-- the underlying tables stay protected by grants + RLS.
grant usage on schema test to anon, authenticated, service_role;
grant execute on all functions in schema app to anon, authenticated, service_role;
grant execute on function test.set_test_role(text, uuid, text) to anon, authenticated, service_role;
grant execute on function test.expect_denied(text, text, text) to anon, authenticated, service_role;
grant execute on function test.assert_count(text, text, integer) to anon, authenticated, service_role;
grant execute on function test.assert_true(text, boolean) to anon, authenticated, service_role;

-- Tests run as the migration owner, which bypasses RLS like service_role.
-- The suite impersonates attenuated roles through test helpers, so run as a
-- non-superuser who holds no implicit test bypass.
do $$ begin
  create role queme_test_runner nologin;
exception when duplicate_object then null; end $$;
grant authenticated to queme_test_runner;
grant anon to queme_test_runner;
grant service_role to queme_test_runner;
grant usage on schema public, app, storage, test to queme_test_runner;
grant usage on schema test to anon, authenticated, service_role;
grant execute on all functions in schema test to queme_test_runner;
grant select, insert, update, delete on all tables in schema public to queme_test_runner;
grant select, insert, update, delete on all tables in schema auth to queme_test_runner;
grant select, insert, update, delete on all tables in schema storage to queme_test_runner;
grant execute on all functions in schema app to queme_test_runner;
alter default privileges in schema public grant select, insert, update, delete on tables to queme_test_runner;
set role queme_test_runner;

-- ------------------------------------------------------------- seed data
-- service_role owns the seed: profile guard triggers reject privileged inserts.
set role service_role;
reset request.jwt.claim.sub;
reset request.jwt.claim.role;
reset request.jwt.claims;

insert into auth.users (id, email, raw_user_meta_data) values
  ('11111111-1111-1111-1111-111111111111', 'student1@example.com', '{"full_name":"Student One"}'),
  ('22222222-2222-2222-2222-222222222222', 'student2@example.com', '{"full_name":"Student Two"}'),
  ('33333333-3333-3333-3333-333333333333', 'student3@example.com', '{"full_name":"Student Three"}'),
  ('44444444-4444-4444-4444-444444444444', 'teacher1@example.com', '{"full_name":"Teacher One"}'),
  ('55555555-5555-5555-5555-555555555555', 'teacher2@example.com', '{"full_name":"Teacher Two"}'),
  ('66666666-6666-6666-6666-666666666666', 'coord1@example.com', '{"full_name":"Coordinator One"}'),
  ('77777777-7777-7777-7777-777777777777', 'coord2@example.com', '{"full_name":"Coordinator Two"}'),
  ('88888888-8888-8888-8888-888888888888', 'admin1@example.com', '{"full_name":"Admin One"}')
on conflict (id) do nothing;

-- Signup trigger provisions pending student profiles; activate with guard off.
select set_config('app.trusted_role_change', 'on', false);
insert into public.profiles (id, email, full_name, role, status) values
  ('11111111-1111-1111-1111-111111111111', 'student1@example.com', 'Student One', 'student', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'student2@example.com', 'Student Two', 'student', 'active'),
  ('33333333-3333-3333-3333-333333333333', 'student3@example.com', 'Student Three', 'student', 'active'),
  ('44444444-4444-4444-4444-444444444444', 'teacher1@example.com', 'Teacher One', 'teacher', 'active'),
  ('55555555-5555-5555-5555-555555555555', 'teacher2@example.com', 'Teacher Two', 'teacher', 'active'),
  ('66666666-6666-6666-6666-666666666666', 'coord1@example.com', 'Coordinator One', 'coordinator', 'active'),
  ('77777777-7777-7777-7777-777777777777', 'coord2@example.com', 'Coordinator Two', 'coordinator', 'active'),
  ('88888888-8888-8888-8888-888888888888', 'admin1@example.com', 'Admin One', 'admin', 'active')
on conflict (id) do update
  set email = excluded.email, full_name = excluded.full_name,
      role = excluded.role, status = excluded.status;
select set_config('app.trusted_role_change', 'off', false);

-- Academic fixtures: CS dept, MCA + BCA, class_a (MCA/III/A), class_b (BCA/I/B).
insert into public.departments (id, code, name) values
  ('d0000000-0000-0000-0000-000000000001', 'CS', 'Computer Science')
on conflict (id) do nothing;

insert into public.courses (id, department_id, code, name, program_level, duration_semesters) values
  ('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001', 'MCA', 'MCA', 'postgraduate', 6),
  ('c0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000001', 'BCA', 'BCA', 'undergraduate', 6)
on conflict (id) do nothing;

insert into public.semesters (id, course_id, number, label) values
  ('50000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 3, 'Semester III'),
  ('50000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002', 1, 'Semester I')
on conflict (id) do nothing;

insert into public.batches (id, course_id, start_year, label) values
  ('b0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', 2024, 'MCA 2024'),
  ('b0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002', 2025, 'BCA 2025')
on conflict (id) do nothing;

insert into public.classes (id, course_id, semester_id, batch_id, section, name) values
  ('a0000000-0000-0000-0000-000000000001', 'c0000000-0000-0000-0000-000000000001', '50000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 'A', 'MCA III-A'),
  ('a0000000-0000-0000-0000-000000000002', 'c0000000-0000-0000-0000-000000000002', '50000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000002', 'B', 'BCA I-B')
on conflict (id) do nothing;

insert into public.enrollments (student_id, class_id, roll_number, status) values
  ('11111111-1111-1111-1111-111111111111', 'a0000000-0000-0000-0000-000000000001', 'MCA-001', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'a0000000-0000-0000-0000-000000000001', 'MCA-002', 'active'),
  ('33333333-3333-3333-3333-333333333333', 'a0000000-0000-0000-0000-000000000002', 'BCA-001', 'active')
on conflict (class_id, student_id) do nothing;

insert into public.teacher_assignments (teacher_id, class_id) values
  ('44444444-4444-4444-4444-444444444444', 'a0000000-0000-0000-0000-000000000001')
on conflict (teacher_id, class_id) do nothing;

insert into public.coordinator_assignments (coordinator_id, scope_type, course_id) values
  ('66666666-6666-6666-6666-666666666666', 'course', 'c0000000-0000-0000-0000-000000000001')
on conflict do nothing;
insert into public.coordinator_assignments (coordinator_id, scope_type, class_id) values
  ('77777777-7777-7777-7777-777777777777', 'class', 'a0000000-0000-0000-0000-000000000002')
on conflict do nothing;

-- Interview fixtures for student1 (attempt) and student3 (attempt).
-- Inserted under each student's own JWT so the owner trigger holds legitimately.
select test.set_test_role('authenticated', '11111111-1111-1111-1111-111111111111');
do $$ begin
  if not exists (select 1 from public.interview_attempts where id = 'e0000000-0000-0000-0000-000000000001') then
    insert into public.interview_attempts (id, student_id, interview_type, target_role, status)
    values ('e0000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Technical', 'Data Scientist', 'completed');
  end if;
end $$;

select test.set_test_role('authenticated', '33333333-3333-3333-3333-333333333333');
do $$ begin
  if not exists (select 1 from public.interview_attempts where id = 'e0000000-0000-0000-0000-000000000002') then
    insert into public.interview_attempts (id, student_id, interview_type, target_role, status)
    values ('e0000000-0000-0000-0000-000000000002', '33333333-3333-3333-3333-333333333333', 'HR', 'Data Analyst', 'completed');
  end if;
end $$;
reset role;
set role service_role;

do $$ begin
  if not exists (select 1 from public.generated_questions where id = 'f0000000-0000-0000-0000-000000000001') then
    insert into public.generated_questions (id, attempt_id, topic, category, difficulty, prompt, question_text, source)
    values ('f0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 'SQL', 'Technical', 'Easy',
      'Ask an easy SQL join question.', 'What is the difference between INNER JOIN and LEFT JOIN?', 'bank');
  end if;
end $$;

insert into public.question_rubrics (question_id, expected_concepts, rubric, reference_answer)
values ('f0000000-0000-0000-0000-000000000001', array['join semantics','null handling'], '{"max":10}'::jsonb, 'Inner returns matches only.')
on conflict (question_id) do nothing;

do $$ begin
  if not exists (select 1 from public.interview_turns where id = 'd0000000-0000-0000-0000-000000000001') then
    insert into public.interview_turns (id, attempt_id, turn_index, question_id, question_text, asked_by, difficulty)
    values ('d0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 0,
      'f0000000-0000-0000-0000-000000000001', 'What is the difference between INNER JOIN and LEFT JOIN?', 'ai', 'Easy');
  end if;
end $$;

insert into public.answers (id, turn_id, attempt_id, student_id, answer_type, text_answer, status)
values ('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000001',
  'e0000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
  'text', 'Inner join returns matching rows; left join keeps left rows with nulls.', 'submitted')
on conflict (id) do nothing;

insert into public.transcripts (answer_id, engine, language, text_content, is_final)
values ('c0000000-0000-0000-0000-000000000001', 'manual', 'en', 'Inner join returns matching rows.', true)
on conflict do nothing;

insert into public.recording_assets (id, attempt_id, owner_id, bucket, object_path, status)
values ('b0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111', 'recordings',
  'students/11111111-1111-1111-1111-111111111111/attempts/e0000000-0000-0000-0000-000000000001/answer-0.webm', 'ready')
on conflict (id) do nothing;

insert into public.answer_evaluations (answer_id, attempt_id, source, evaluation_version, overall_score, feedback)
select 'c0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001',
  'deterministic', 'v1', 78, 'Correct join semantics; add an example.'
where not exists (
  select 1 from public.answer_evaluations
  where answer_id = 'c0000000-0000-0000-0000-000000000001'
    and source = 'deterministic' and evaluation_version = 'v1'
);

insert into public.reports (id, attempt_id, student_id, report_type, version, is_current, overall_score)
values ('a0000000-0000-0000-0000-000000000003', 'e0000000-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111', 'individual', 1, true, 78)
on conflict (id) do nothing;

insert into public.teacher_feedback (attempt_id, teacher_id, feedback_text, rating, visibility)
select 'e0000000-0000-0000-0000-000000000001', '44444444-4444-4444-4444-444444444444',
  'Good join semantics; slow down on trade-offs.', 4, 'student_visible'
where not exists (
  select 1 from public.teacher_feedback
  where attempt_id = 'e0000000-0000-0000-0000-000000000001'
    and teacher_id = '44444444-4444-4444-4444-444444444444'
);

-- Object fixtures for the storage-policy tests.
set role service_role;
insert into storage.objects (bucket_id, name, owner, metadata) values
  ('recordings', 'students/11111111-1111-1111-1111-111111111111/attempts/e0000000-0000-0000-0000-000000000001/answer-0.webm', '11111111-1111-1111-1111-111111111111', '{}'::jsonb),
  ('reports', 'reports/a0000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '{}'::jsonb)
on conflict (bucket_id, name) do update set owner = excluded.owner, metadata = excluded.metadata;

reset role;

-- A1. Anonymous users cannot access interview data.
select test.set_test_role('anon', '00000000-0000-0000-0000-000000000000', 'anon');
select test.assert_no_access('A1 attempts hidden from anon',
  $$select 1 from public.interview_attempts$$);
select test.assert_no_access('A1 answers hidden from anon',
  $$select 1 from public.answers$$);
select test.assert_no_access('A1 reports hidden from anon',
  $$select id, attempt_id, student_id, report_type, version, is_current,
       overall_score, sections, recommendations, generated_by, created_at
     from public.reports$$);
select test.assert_no_access('A1 profiles hidden from anon',
  $$select 1 from public.profiles$$);
select test.assert_no_access('A1 storage hidden from anon',
  $$select 1 from storage.objects$$);

-- A2. Signup metadata cannot grant roles: a fresh user is pending student.
-- (Signup itself is a platform call; service_role performs the shim insert,
-- the trigger still provisions the profile from user metadata.)
reset role;
set role service_role;
insert into auth.users (id, email, raw_user_meta_data)
values ('99999999-9999-9999-9999-999999999999', 'pending1@example.com',
  '{"full_name":"Pending One","role":"admin","user_role":"teacher"}')
on conflict (id) do nothing;
reset role;
select test.set_test_role('authenticated', '99999999-9999-9999-9999-999999999999');
select test.assert_true('A2 metadata admin ignored',
  (select role = 'student' and status = 'pending'
     from public.profiles where id = '99999999-9999-9999-9999-999999999999'));
select test.assert_count('A2 pending user sees no attempts',
  $$select 1 from public.interview_attempts$$, 0);

-- A3. Profile edits cannot escalate role or status.
select test.set_test_role('authenticated', '11111111-1111-1111-1111-111111111111');
select test.expect_denied('A3 student cannot self-promote to admin',
  $$update public.profiles set role = 'admin' where id = '11111111-1111-1111-1111-111111111111'$$);
select test.expect_denied('A3 student cannot change own status',
  $$update public.profiles set status = 'suspended' where id = '11111111-1111-1111-1111-111111111111'$$);

-- A4. Direct privileged profile insert is rejected without the workflow flag.
select test.expect_denied('A4 privileged insert blocked',
  $$insert into public.profiles (id, email, full_name, role, status)
    values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'evil@example.com', 'Evil', 'admin', 'active')$$);

-- A5. Non-admin RPC role change is rejected.
select test.set_test_role('authenticated', '22222222-2222-2222-2222-222222222222');
select test.expect_denied('A5 student RPC promotion rejected',
  $$select app.set_profile_role('22222222-2222-2222-2222-222222222222', 'admin')$$);

-- A6. Admin RPC role change succeeds and is audited.
select test.set_test_role('authenticated', '88888888-8888-8888-8888-888888888888');
select app.set_profile_role('55555555-5555-5555-5555-555555555555', 'teacher');
select test.assert_true('A6 promotion applied',
  (select role = 'teacher' from public.profiles where id = '55555555-5555-5555-5555-555555555555'));
select test.assert_true('A6 promotion audited',
  (select exists (select 1 from public.audit_events
     where action = 'profile.role_change'
       and entity_id = '55555555-5555-5555-5555-555555555555')));
select set_config('app.trusted_role_change', 'on', false);
reset role;
set role service_role;
update public.profiles set role = 'teacher', status = 'active'
  where id = '55555555-5555-5555-5555-555555555555';
select set_config('app.trusted_role_change', 'off', false);
reset role;

-- B. Cross-student isolation and client-side score protection.
select test.set_test_role('authenticated', '22222222-2222-2222-2222-222222222222');
select test.assert_count('B1 student cannot read another student attempt',
  $$select 1 from public.interview_attempts where id = 'e0000000-0000-0000-0000-000000000001'$$, 0);
select test.assert_count('B2 student cannot read another student answer',
  $$select 1 from public.answers where id = 'c0000000-0000-0000-0000-000000000001'$$, 0);
select test.expect_denied('B3 student cannot write AI score',
  $$insert into public.answer_evaluations (answer_id, attempt_id, source, evaluation_version, overall_score)
    values ('c0000000-0000-0000-0000-000000000001', 'e0000000-0000-0000-0000-000000000001', 'model', 'evil', 100)$$);
select test.expect_denied('B4 student cannot upload beneath another attempt',
  $$insert into storage.objects (bucket_id, name, owner, metadata) values
    ('recordings', 'students/22222222-2222-2222-2222-222222222222/attempts/e0000000-0000-0000-0000-000000000001/evil.webm',
     '22222222-2222-2222-2222-222222222222', '{}'::jsonb)$$);

-- C. A teacher without a class assignment cannot read that class's student.
select test.set_test_role('authenticated', '55555555-5555-5555-5555-555555555555');
select test.assert_count('C1 unassigned teacher cannot read class A attempt',
  $$select 1 from public.interview_attempts where id = 'e0000000-0000-0000-0000-000000000001'$$, 0);
