-- First-admin bootstrap + administrator-only user management.
-- Because auth.users is platform-managed, creation uses the backend Admin
-- API; what the database enforces:
--   1. bootstrap_first_admin() creates the ONLY admin when none exists,
--      and only with the server-held bootstrap secret (never a client token).
--   2. set_profile_role() is the only way to grant/revoke trusted roles;
--      it rejects callers without the admin role and records an audit event.
--   3. Client role edits remain blocked by the guard in migration 02.

-- Bootstrap secret is server-held: set QUEME_BOOTSTRAP_SECRET in backend/.env
-- and pass it to this function from the backend endpoint. There is no way to
-- learn it from auth.users, profiles, or any client-visible table.
create or replace function app.bootstrap_first_admin(
  p_user_id uuid,
  p_email text,
  p_full_name text,
  p_secret text
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare expected text := coalesce(current_setting('app.bootstrap_secret', true), '');
begin
  if expected = '' or expected is distinct from p_secret then
    raise exception 'bootstrap is not authorized' using errcode = '42501';
  end if;
  if exists (select 1 from public.profiles p where p.role = 'admin') then
    raise exception 'an administrator already exists' using errcode = '23505';
  end if;
  perform set_config('app.trusted_role_change', 'on', true);
  insert into public.profiles (id, email, full_name, role, status, is_role_locked, activated_at)
  values (p_user_id, p_email, coalesce(p_full_name, ''), 'admin', 'active', true, now())
  on conflict (id) do update
    set role = 'admin', status = 'active', is_role_locked = true, activated_at = now(),
        email = excluded.email, full_name = excluded.full_name;
  insert into public.audit_events (actor_id, action, entity_type, entity_id, description)
  values (p_user_id, 'admin.bootstrap', 'profile', p_user_id, 'First administrator provisioned.');
  return p_user_id;
end $$;
revoke all on function app.bootstrap_first_admin(uuid, text, text, text) from public, anon, authenticated;
grant execute on function app.bootstrap_first_admin(uuid, text, text, text) to service_role;

-- Administrator-only role assignment. Teachers/admins are created as pending
-- students via signup, then promoted here after verification.
create or replace function app.set_profile_role(
  p_target uuid,
  p_role public.app_role,
  p_request_id uuid default null
) returns void
language plpgsql security definer set search_path = '' as $$
declare old_role public.app_role;
begin
  if not app.is_admin() and not app.is_service_role() then
    raise exception 'role changes require an administrator' using errcode = '42501';
  end if;
  select role into old_role from public.profiles where id = p_target;
  if not found then
    raise exception 'profile not found' using errcode = 'P0002';
  end if;
  perform set_config('app.trusted_role_change', 'on', true);
  update public.profiles
  set role = p_role, status = 'active', activated_at = coalesce(activated_at, now())
  where id = p_target;
  insert into public.audit_events (actor_id, action, entity_type, entity_id, description, metadata, request_id)
  values (
    auth.uid(), 'profile.role_change', 'profile', p_target,
    'Role changed by administrator.',
    jsonb_build_object('from', old_role, 'to', p_role),
    p_request_id
  );
end $$;
revoke all on function app.set_profile_role(uuid, public.app_role, uuid) from public, anon, authenticated;
grant execute on function app.set_profile_role(uuid, public.app_role, uuid) to authenticated, service_role;

-- Activation / suspension. Pending accounts become active on first admin
-- approval or email confirmation; suspension revokes all scoped access.
create or replace function app.set_profile_status(
  p_target uuid,
  p_status public.profile_status,
  p_request_id uuid default null
) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if not app.is_admin() and not app.is_service_role() then
    raise exception 'status changes require an administrator' using errcode = '42501';
  end if;
  perform set_config('app.trusted_role_change', 'on', true);
  update public.profiles
  set status = p_status,
      activated_at = case when p_status = 'active' then coalesce(activated_at, now()) else activated_at end
  where id = p_target;
  if not found then
    raise exception 'profile not found' using errcode = 'P0002';
  end if;
  insert into public.audit_events (actor_id, action, entity_type, entity_id, description, metadata, request_id)
  values (
    auth.uid(), 'profile.status_change', 'profile', p_target,
    'Status changed by administrator.',
    jsonb_build_object('to', p_status),
    p_request_id
  );
end $$;
revoke all on function app.set_profile_status(uuid, public.profile_status, uuid) from public, anon, authenticated;
grant execute on function app.set_profile_status(uuid, public.profile_status, uuid) to authenticated, service_role;

-- Clients invoke RPCs, never raw policy-bypass writes. Audit logging is for
-- signed-in callers and the server only; anonymous callers cannot log.
revoke all on function app.log_audit_event(text, text, uuid, text, jsonb, uuid) from public, anon;
grant execute on function app.log_audit_event(text, text, uuid, text, jsonb, uuid) to authenticated, service_role;

-- Data-partition access: same-row guarantees as the denied base tables, but
-- only the safe columns are ever projected. SECURITY INVOKER, so policies on
-- the base tables apply inside every reader query.
create or replace function app.turn_slice(p_attempt uuid)
returns table (
  turn_id uuid, turn_index integer, question_text text, asked_by public.turn_asked_by,
  difficulty text, question_source public.question_source, presented_at timestamptz, answered_at timestamptz
)
language sql stable security invoker set search_path = '' as $$
  select t.id, t.turn_index, t.question_text, t.asked_by, t.difficulty,
         t.question_source, t.presented_at, t.answered_at
  from public.interview_turns t
  where t.attempt_id = p_attempt
  order by t.turn_index
$$;

create or replace function app.transcript_slice(p_answer uuid)
returns table (version integer, engine text, language text, text_content text, is_final boolean, created_at timestamptz)
language sql stable security invoker set search_path = '' as $$
  select tr.version, tr.engine, tr.language, tr.text_content, tr.is_final, tr.created_at
  from public.transcripts tr
  where tr.answer_id = p_answer
  order by tr.version
$$;

create or replace function app.friendly_report_slice(p_report uuid)
returns table (
  report_type public.report_type, version integer, is_current boolean,
  overall_score integer, sections jsonb, recommendations text[], generated_by text, created_at timestamptz
)
language sql stable security invoker set search_path = '' as $$
  select r.report_type, r.version, r.is_current, r.overall_score,
         r.sections, r.recommendations, r.generated_by, r.created_at
  from public.reports r
  where r.id = p_report
$$;

revoke all on function app.turn_slice(uuid) from public, anon;
revoke all on function app.transcript_slice(uuid) from public, anon;
revoke all on function app.friendly_report_slice(uuid) from public, anon;
grant execute on function app.turn_slice(uuid) to authenticated, service_role;
grant execute on function app.transcript_slice(uuid) to authenticated, service_role;
grant execute on function app.friendly_report_slice(uuid) to authenticated, service_role;

-- Aggregate reports: a single entry point that refuses any scope outside the
-- caller's role. Students cannot read class/course/department aggregates.
create or replace function app.aggregate_report(
  p_report_type public.report_type,
  p_class_id uuid default null,
  p_course_id uuid default null,
  p_department_id uuid default null
)
returns table (
  attempts bigint, students bigint, avg_score numeric,
  min_score integer, max_score integer, completed_at timestamptz
)
language sql stable security invoker set search_path = '' as $$
  with scope_attempts as (
    select a.id, a.student_id, r.overall_score
    from public.interview_attempts a
    left join public.reports r
      on r.attempt_id = a.id and r.report_type = 'individual' and r.is_current
    join public.enrollments e on e.student_id = a.student_id
    where a.status = 'completed'
      and (
        (p_report_type = 'class' and e.class_id = p_class_id)
        or (p_report_type = 'course'
            and e.class_id in (select c.id from public.classes c where c.course_id = p_course_id))
        or (p_report_type = 'department'
            and e.class_id in (
              select c.id from public.classes c
              join public.courses co on co.id = c.course_id
              where co.department_id = p_department_id
            ))
      )
      and app.can_read_student(a.student_id)
      and (
        app.is_admin()
        or (
          p_report_type = 'class' and p_class_id is not null
          and (app.teaches_class(p_class_id) or app.coordinator_covers_class(p_class_id))
        )
        or (
          p_report_type = 'course' and p_course_id is not null
          and app.coordinator_covers_course(p_course_id)
        )
        or (
          p_report_type = 'department' and p_department_id is not null
          and exists (
            select 1 from public.coordinator_assignments ca
            where ca.coordinator_id = auth.uid()
              and ca.scope_type = 'department' and ca.department_id = p_department_id
          )
        )
      )
  )
  select count(*)::bigint, count(distinct student_id)::bigint,
         round(avg(overall_score), 1), min(overall_score), max(overall_score), now()
  from scope_attempts
$$;

revoke all on function app.aggregate_report(public.report_type, uuid, uuid, uuid) from public, anon;
grant execute on function app.aggregate_report(public.report_type, uuid, uuid, uuid) to authenticated, service_role;

-- Aggregate reports are written only by the trusted server.
create or replace function app.guard_report_write() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' and new.report_type <> 'individual'
     and not app.is_service_role()
     and coalesce(current_setting('app.trusted_role_change', true), 'off') <> 'on' then
    raise exception 'aggregate reports are written by the trusted server only'
      using errcode = '42501';
  end if;
  return new;
end $$;
drop trigger if exists reports_aggregate_guard on public.reports;
create trigger reports_aggregate_guard before insert on public.reports
  for each row execute function app.guard_report_write();
