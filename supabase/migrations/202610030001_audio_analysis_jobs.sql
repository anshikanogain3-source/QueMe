create table if not exists public.audio_analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  job_type text not null check (job_type = 'audio_analysis'),
  idempotency_key text not null unique check (char_length(idempotency_key) between 8 and 128),
  payload jsonb not null check (jsonb_typeof(payload) = 'object'),
  request_id uuid not null,
  status text not null default 'queued' check (status in ('queued', 'processing', 'retrying', 'succeeded', 'failed')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 4 check (max_attempts between 1 and 10),
  available_at timestamptz not null default now(),
  locked_by uuid,
  lease_expires_at timestamptz,
  last_error text,
  result jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  check ((status = 'processing') = (locked_by is not null and lease_expires_at is not null))
);

create index if not exists audio_analysis_jobs_claim_idx
  on public.audio_analysis_jobs (available_at, created_at)
  where status in ('queued', 'retrying');

create index if not exists audio_analysis_jobs_expired_lease_idx
  on public.audio_analysis_jobs (lease_expires_at)
  where status = 'processing';

alter table public.audio_analysis_jobs enable row level security;
revoke all on public.audio_analysis_jobs from public, anon, authenticated;
grant select, insert, update on public.audio_analysis_jobs to service_role;
