-- Analysis jobs, versioned reports, teacher feedback, consent, and audit events.
-- Reuses the existing audio_analysis_jobs queue by widening its job types
-- instead of building a second queue.

do $$ begin
  create type public.report_type as enum ('individual','class','course','department');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.consent_type as enum ('recording','analysis','retention');
exception when duplicate_object then null; end $$;

-- Widen the existing queue: keep payload/status/lease semantics intact.
alter table public.audio_analysis_jobs drop constraint if exists audio_analysis_jobs_job_type_check;
alter table public.audio_analysis_jobs
  add constraint audio_analysis_jobs_job_type_check
  check (job_type in ('audio_analysis','asr','speech_eval','answer_eval','report_build'));
alter table public.audio_analysis_jobs
  add column if not exists attempt_id uuid references public.interview_attempts(id) on delete cascade;
alter table public.audio_analysis_jobs
  add column if not exists actor_id uuid references public.profiles(id) on delete set null;
create index if not exists audio_analysis_jobs_attempt_idx
  on public.audio_analysis_jobs (attempt_id);

-- Versioned reports. Individual reports anchor to an attempt; aggregates
-- anchor to class/course/department scope with nullable attempt.
create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid references public.interview_attempts(id) on delete cascade,
  student_id uuid references public.profiles(id) on delete set null,
  report_type public.report_type not null,
  class_id uuid references public.classes(id) on delete set null,
  course_id uuid references public.courses(id) on delete set null,
  department_id uuid references public.departments(id) on delete set null,
  version integer not null default 1 check (version >= 1),
  is_current boolean not null default true,
  overall_score integer check (overall_score is null or (overall_score >= 0 and overall_score <= 100)),
  sections jsonb not null default '{}'::jsonb,
  recommendations text[] not null default '{}',
  payload jsonb not null default '{}'::jsonb,
  generated_by text not null default 'system',
  created_at timestamptz not null default now()
);
create unique index if not exists reports_attempt_version_key
  on public.reports (attempt_id, version) where attempt_id is not null;
create unique index if not exists reports_current_individual_key
  on public.reports (attempt_id) where attempt_id is not null and is_current;
create unique index if not exists reports_current_aggregate_key
  on public.reports (report_type, class_id, course_id, department_id, version)
  where attempt_id is null;
create index if not exists reports_student_idx on public.reports (student_id);
create index if not exists reports_class_idx on public.reports (class_id);
create index if not exists reports_course_idx on public.reports (course_id);

-- Teacher feedback stays separate from AI evaluation. Teachers may only
-- comment on students they teach (trigger), and feedback is never an overwrite.
create table if not exists public.teacher_feedback (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  answer_id uuid references public.answers(id) on delete set null,
  teacher_id uuid not null references public.profiles(id) on delete cascade,
  feedback_text text not null check (char_length(feedback_text) between 1 and 5000),
  rating integer check (rating is null or (rating >= 1 and rating <= 5)),
  visibility text not null default 'student_visible',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists teacher_feedback_attempt_idx on public.teacher_feedback (attempt_id);
create index if not exists teacher_feedback_answer_idx on public.teacher_feedback (answer_id);
create index if not exists teacher_feedback_teacher_idx on public.teacher_feedback (teacher_id);
drop trigger if exists teacher_feedback_touch on public.teacher_feedback;
create trigger teacher_feedback_touch before update on public.teacher_feedback
  for each row execute function app.touch_updated_at();

create or replace function app.assert_feedback_scope() returns trigger
language plpgsql security definer set search_path = '' as $$
declare target_student uuid;
begin
  if coalesce(current_setting('app.trusted_role_change', true), 'off') = 'on'
     or app.is_service_role() then
    return new;
  end if;
  if new.teacher_id is distinct from auth.uid() then
    raise exception 'teacher feedback must be authored by the signed-in teacher'
      using errcode = '42501';
  end if;
  select a.student_id into target_student
    from public.interview_attempts a where a.id = new.attempt_id;
  if target_student is null
     or not (app.teaches_student(target_student) or app.is_admin()) then
    raise exception 'feedback is limited to students you are assigned to teach'
      using errcode = '42501';
  end if;
  return new;
end $$;
drop trigger if exists teacher_feedback_scope_check on public.teacher_feedback;
create trigger teacher_feedback_scope_check before insert or update on public.teacher_feedback
  for each row execute function app.assert_feedback_scope();

-- Consent + retention records. Revocation timestamps drive retention jobs.
create table if not exists public.consent_records (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.profiles(id) on delete cascade,
  consent_type public.consent_type not null,
  granted boolean not null,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  note text,
  created_at timestamptz not null default now()
);
create index if not exists consent_records_student_idx on public.consent_records (student_id);
create unique index if not exists consent_records_latest_key
  on public.consent_records (student_id, consent_type, granted_at);

-- Audit events. Append-mostly: no UPDATE/DELETE grants to clients.
create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references public.profiles(id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  request_id uuid,
  created_at timestamptz not null default now()
);
create index if not exists audit_events_actor_idx on public.audit_events (actor_id);
create index if not exists audit_events_entity_idx on public.audit_events (entity_type, entity_id);
create index if not exists audit_events_created_idx on public.audit_events (created_at);

create or replace function app.log_audit_event(
  p_action text,
  p_entity_type text,
  p_entity_id uuid,
  p_description text default null,
  p_metadata jsonb default '{}'::jsonb,
  p_request_id uuid default null
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare new_id uuid;
begin
  insert into public.audit_events (actor_id, action, entity_type, entity_id, description, metadata, request_id)
  values (auth.uid(), p_action, p_entity_type, p_entity_id, p_description, p_metadata, p_request_id)
  returning id into new_id;
  return new_id;
end $$;

alter table public.reports enable row level security;
alter table public.teacher_feedback enable row level security;
alter table public.consent_records enable row level security;
alter table public.audit_events enable row level security;

revoke all on public.reports, public.teacher_feedback, public.consent_records, public.audit_events
  from anon, authenticated;
-- audit_events SELECT is granted, but RLS (audit_events_read_admin) limits rows to admins.
grant select on public.teacher_feedback, public.consent_records, public.audit_events to authenticated;
grant insert, update on public.teacher_feedback to authenticated;
grant insert on public.consent_records, public.audit_events to authenticated;
grant select (id, attempt_id, student_id, report_type, version, is_current, overall_score,
  sections, recommendations, generated_by, created_at) on public.reports to authenticated;
grant select, insert, update, delete on public.reports, public.teacher_feedback,
  public.consent_records, public.audit_events to service_role;

