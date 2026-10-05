-- Interview core: assignments, attempts, turns, generated questions (no rubrics),
-- answers, versioned transcripts, recording metadata, per-answer audio
-- segments, answer evaluations, and speech metrics.
-- Grading keys (expected concepts, rubrics, reference answers) live ONLY in
-- question_rubrics, which is never student-readable.

do $$ begin
  create type public.attempt_status as enum ('created','in_progress','processing','completed','abandoned');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.turn_asked_by as enum ('ai','teacher','human_interviewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.question_source as enum ('bank','model','teacher','human_intervention');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.answer_status as enum ('draft','submitted','timed_out','skipped');
exception when duplicate_object then null; end $$;

create table if not exists public.interview_assignments (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.profiles(id) on delete cascade,
  class_id uuid not null references public.classes(id) on delete cascade,
  created_by uuid references public.profiles(id) on delete set null,
  interview_type text not null,
  target_role text not null,
  experience_level text not null default 'beginner',
  difficulty text not null default 'adaptive',
  question_target_count integer not null default 5 check (question_target_count between 1 and 30),
  due_at timestamptz,
  status text not null default 'assigned',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists interview_assignments_student_idx on public.interview_assignments (student_id);
create index if not exists interview_assignments_class_idx on public.interview_assignments (class_id);
drop trigger if exists interview_assignments_touch on public.interview_assignments;
create trigger interview_assignments_touch before update on public.interview_assignments
  for each row execute function app.touch_updated_at();

create table if not exists public.interview_attempts (
  id uuid primary key default gen_random_uuid(),
  assignment_id uuid references public.interview_assignments(id) on delete set null,
  student_id uuid not null references public.profiles(id) on delete cascade,
  interview_type text not null,
  target_role text not null,
  experience_level text not null default 'beginner',
  mode text not null default 'ai',
  status public.attempt_status not null default 'created',
  current_difficulty text,
  config jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists interview_attempts_student_idx on public.interview_attempts (student_id);
create index if not exists interview_attempts_assignment_idx on public.interview_attempts (assignment_id);
create index if not exists interview_attempts_status_idx on public.interview_attempts (status);
drop trigger if exists interview_attempts_touch on public.interview_attempts;
create trigger interview_attempts_touch before update on public.interview_attempts
  for each row execute function app.touch_updated_at();

-- Attempts may only be created for the signed-in student; ownership is immutable.
create or replace function app.assert_attempt_owner() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' and new.student_id is distinct from auth.uid()
     and coalesce(current_setting('app.trusted_role_change', true), 'off') <> 'on' then
    raise exception 'interview attempts must be created for the signed-in student'
      using errcode = '42501';
  end if;
  if tg_op = 'UPDATE' and (new.student_id is distinct from old.student_id
     or (new.student_id is distinct from auth.uid()
         and coalesce(current_setting('app.trusted_role_change', true), 'off') <> 'on')) then
    raise exception 'interview attempt ownership is immutable'
      using errcode = '42501';
  end if;
  return new;
end $$;
drop trigger if exists interview_attempts_owner_check on public.interview_attempts;
create trigger interview_attempts_owner_check before insert or update on public.interview_attempts
  for each row execute function app.assert_attempt_owner();

-- Generated questions: prompt/question text is safe to expose; NEVER rubrics.
create table if not exists public.generated_questions (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid references public.interview_attempts(id) on delete set null,
  topic text not null,
  category text not null,
  difficulty text not null,
  prompt text not null,
  question_text text not null,
  source public.question_source not null default 'bank',
  model_name text,
  model_version text,
  prompt_version text,
  structured_output jsonb,
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now()
);
create index if not exists generated_questions_attempt_idx on public.generated_questions (attempt_id);
create index if not exists generated_questions_source_idx on public.generated_questions (source);

-- Private grading keys. No SELECT for anon/authenticated users.
create table if not exists public.question_rubrics (
  question_id uuid primary key references public.generated_questions(id) on delete cascade,
  expected_concepts text[] not null default '{}',
  rubric jsonb,
  reference_answer text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
drop trigger if exists question_rubrics_touch on public.question_rubrics;
create trigger question_rubrics_touch before update on public.question_rubrics
  for each row execute function app.touch_updated_at();

create table if not exists public.interview_turns (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  turn_index integer not null check (turn_index >= 0),
  question_id uuid references public.generated_questions(id) on delete set null,
  question_text text not null,
  asked_by public.turn_asked_by not null default 'ai',
  difficulty text,
  question_source public.question_source,
  presented_at timestamptz,
  answered_at timestamptz,
  created_at timestamptz not null default now()
);
create unique index if not exists interview_turns_attempt_index_key
  on public.interview_turns (attempt_id, turn_index);
create index if not exists interview_turns_attempt_idx on public.interview_turns (attempt_id);
create index if not exists interview_turns_question_idx on public.interview_turns (question_id);

create table if not exists public.answers (
  id uuid primary key default gen_random_uuid(),
  turn_id uuid not null references public.interview_turns(id) on delete cascade,
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  student_id uuid not null references public.profiles(id) on delete cascade,
  answer_type text not null default 'text',
  text_answer text,
  status public.answer_status not null default 'draft',
  duration_seconds integer check (duration_seconds is null or duration_seconds >= 0),
  submitted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists answers_turn_key on public.answers (turn_id);
create index if not exists answers_attempt_idx on public.answers (attempt_id);
create index if not exists answers_student_idx on public.answers (student_id);
drop trigger if exists answers_touch on public.answers;
create trigger answers_touch before update on public.answers
  for each row execute function app.touch_updated_at();

-- Versioned transcripts. Version 1 starts at 1 per answer via the trigger.
create table if not exists public.transcripts (
  id uuid primary key default gen_random_uuid(),
  answer_id uuid not null references public.answers(id) on delete cascade,
  version integer not null default 1 check (version >= 1),
  engine text not null default 'manual',
  language text not null default 'en',
  text_content text not null default '',
  is_final boolean not null default false,
  confidence numeric(4,3) check (confidence is null or (confidence >= 0 and confidence <= 1)),
  created_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now()
);
create unique index if not exists transcripts_answer_version_key on public.transcripts (answer_id, version);
create index if not exists transcripts_answer_idx on public.transcripts (answer_id);

create or replace function app.assign_transcript_version() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  select coalesce(max(version), 0) + 1 into new.version
    from public.transcripts where answer_id = new.answer_id;
  return new;
end $$;
drop trigger if exists transcripts_version_check on public.transcripts;
create trigger transcripts_version_check before insert on public.transcripts
  for each row execute function app.assign_transcript_version();

-- Recording metadata + per-answer audio segments (private storage only).
do $$ begin
  create type public.recording_status as enum ('uploading','ready','failed','deleted');
exception when duplicate_object then null; end $$;

create table if not exists public.recording_assets (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  bucket text not null default 'recordings',
  object_path text not null,
  content_type text,
  byte_size bigint check (byte_size is null or byte_size >= 0),
  duration_seconds numeric(8,2) check (duration_seconds is null or duration_seconds >= 0),
  status public.recording_status not null default 'uploading',
  retention_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists recording_assets_bucket_path_key
  on public.recording_assets (bucket, object_path);
create index if not exists recording_assets_attempt_idx on public.recording_assets (attempt_id);
create index if not exists recording_assets_owner_idx on public.recording_assets (owner_id);
drop trigger if exists recording_assets_touch on public.recording_assets;
create trigger recording_assets_touch before update on public.recording_assets
  for each row execute function app.touch_updated_at();

create table if not exists public.audio_segments (
  id uuid primary key default gen_random_uuid(),
  recording_id uuid not null references public.recording_assets(id) on delete cascade,
  answer_id uuid references public.answers(id) on delete set null,
  starts_at_ms integer not null check (starts_at_ms >= 0),
  ends_at_ms integer not null check (ends_at_ms > starts_at_ms),
  created_at timestamptz not null default now()
);
create index if not exists audio_segments_recording_idx on public.audio_segments (recording_id);
create index if not exists audio_segments_answer_idx on public.audio_segments (answer_id);

-- Answer evaluations + speech metrics. Written by the trusted server only.
do $$ begin
  create type public.evaluation_source as enum ('deterministic','model','teacher_assisted');
exception when duplicate_object then null; end $$;

create table if not exists public.answer_evaluations (
  id uuid primary key default gen_random_uuid(),
  answer_id uuid not null references public.answers(id) on delete cascade,
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  source public.evaluation_source not null default 'deterministic',
  evaluation_version text not null default 'v1',
  overall_score integer check (overall_score is null or (overall_score >= 0 and overall_score <= 100)),
  concept_score integer check (concept_score is null or (concept_score >= 0 and concept_score <= 100)),
  relevance_score integer check (relevance_score is null or (relevance_score >= 0 and relevance_score <= 100)),
  completeness_score integer check (completeness_score is null or (completeness_score >= 0 and completeness_score <= 100)),
  technical_score integer check (technical_score is null or (technical_score >= 0 and technical_score <= 100)),
  feedback text,
  raw_output jsonb,
  created_at timestamptz not null default now()
);
create index if not exists answer_evaluations_answer_idx on public.answer_evaluations (answer_id);
create index if not exists answer_evaluations_attempt_idx on public.answer_evaluations (attempt_id);
create unique index if not exists answer_evaluations_answer_version_key
  on public.answer_evaluations (answer_id, source, evaluation_version);

create table if not exists public.speech_metrics (
  id uuid primary key default gen_random_uuid(),
  answer_id uuid not null references public.answers(id) on delete cascade,
  attempt_id uuid not null references public.interview_attempts(id) on delete cascade,
  model_name text,
  model_version text,
  speech_rate_wpm numeric(6,2),
  pause_count integer,
  long_pause_count integer,
  hesitation_count integer,
  filler_word_count integer,
  repetition_count integer,
  pronunciation_score integer check (pronunciation_score is null or (pronunciation_score >= 0 and pronunciation_score <= 100)),
  noise_level_db numeric(6,2),
  clarity_score integer check (clarity_score is null or (clarity_score >= 0 and clarity_score <= 100)),
  metrics jsonb,
  created_at timestamptz not null default now()
);
create index if not exists speech_metrics_answer_idx on public.speech_metrics (answer_id);
create index if not exists speech_metrics_attempt_idx on public.speech_metrics (attempt_id);

-- Students may never write evaluation or speech-metric rows. These tables are
-- written by the trusted server only (service_role or a trusted workflow).
create or replace function app.deny_client_eval_write() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if app.is_service_role()
     or coalesce(current_setting('app.trusted_role_change', true), 'off') = 'on' then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;
  raise exception 'evaluations and metrics are written by the trusted server only'
    using errcode = '42501';
end $$;
drop trigger if exists answer_evaluations_client_guard on public.answer_evaluations;
create trigger answer_evaluations_client_guard before insert or update or delete on public.answer_evaluations
  for each row execute function app.deny_client_eval_write();
drop trigger if exists speech_metrics_client_guard on public.speech_metrics;
create trigger speech_metrics_client_guard before insert or update or delete on public.speech_metrics
  for each row execute function app.deny_client_eval_write();

alter table public.interview_assignments enable row level security;
alter table public.interview_attempts enable row level security;
alter table public.generated_questions enable row level security;
alter table public.question_rubrics enable row level security;
alter table public.interview_turns enable row level security;
alter table public.answers enable row level security;
alter table public.transcripts enable row level security;
alter table public.recording_assets enable row level security;
alter table public.audio_segments enable row level security;
alter table public.answer_evaluations enable row level security;
alter table public.speech_metrics enable row level security;

revoke all on public.interview_assignments, public.interview_attempts, public.generated_questions,
  public.interview_turns, public.answers, public.transcripts, public.recording_assets,
  public.audio_segments, public.answer_evaluations, public.speech_metrics from anon, authenticated;
grant select on public.interview_assignments, public.interview_attempts, public.generated_questions,
  public.answers, public.recording_assets, public.audio_segments to authenticated;
grant select on public.answer_evaluations to authenticated;
grant select (id, answer_id, attempt_id, model_name, model_version, speech_rate_wpm,
  pause_count, long_pause_count, hesitation_count, filler_word_count, repetition_count,
  pronunciation_score, noise_level_db, clarity_score, created_at) on public.speech_metrics to authenticated;
grant insert, update, delete on public.interview_attempts, public.answers, public.recording_assets to authenticated;
revoke all on public.question_rubrics from anon, authenticated;
revoke all on public.interview_turns, public.transcripts from anon, authenticated;
grant select, insert, update, delete on public.interview_assignments, public.interview_attempts,
  public.generated_questions, public.question_rubrics, public.interview_turns, public.answers,
  public.transcripts, public.recording_assets, public.audio_segments,
  public.answer_evaluations, public.speech_metrics to service_role;



