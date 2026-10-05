-- Academic structure: departments, courses, semesters, batches, classes,
-- student enrollment, and explicit teacher/coordinator assignments.

do $$ begin
  create type public.enrollment_status as enum ('active','inactive','completed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.coordinator_scope as enum ('class','semester','course','department');
exception when duplicate_object then null; end $$;

create table if not exists public.departments (
  id uuid primary key default gen_random_uuid(),
  code text not null,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists departments_code_key on public.departments (upper(code));

create table if not exists public.courses (
  id uuid primary key default gen_random_uuid(),
  department_id uuid not null references public.departments(id) on delete restrict,
  code text not null,
  name text not null,
  program_level text not null,
  duration_semesters integer not null default 6 check (duration_semesters between 1 and 12),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists courses_code_key on public.courses (upper(code));
create index if not exists courses_department_idx on public.courses (department_id);

create table if not exists public.semesters (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses(id) on delete cascade,
  number integer not null check (number between 1 and 12),
  label text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists semesters_course_number_key on public.semesters (course_id, number);

create table if not exists public.batches (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses(id) on delete cascade,
  start_year integer not null check (start_year between 2000 and 2100),
  label text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists batches_course_year_key on public.batches (course_id, start_year);

create table if not exists public.classes (
  id uuid primary key default gen_random_uuid(),
  course_id uuid not null references public.courses(id) on delete cascade,
  semester_id uuid not null references public.semesters(id) on delete cascade,
  batch_id uuid not null references public.batches(id) on delete cascade,
  section text not null,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists classes_semester_batch_section_key on public.classes (semester_id, batch_id, section);
create index if not exists classes_course_idx on public.classes (course_id);

-- Academic tree edit-time integrity checks.
create or replace function app.assert_semester_course() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.semesters s where s.id = new.semester_id and s.course_id = new.course_id)
     or not exists (select 1 from public.batches b where b.id = new.batch_id and b.course_id = new.course_id) then
    raise exception 'class semester and batch must belong to its course' using errcode = '23514';
  end if;
  return new;
end $$;

drop trigger if exists classes_assert_tree on public.classes;
create trigger classes_assert_tree before insert or update on public.classes
  for each row execute function app.assert_semester_course();

create table if not exists public.enrollments (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.profiles(id) on delete cascade,
  class_id uuid not null references public.classes(id) on delete cascade,
  roll_number text not null,
  status public.enrollment_status not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists enrollments_class_student_key on public.enrollments (class_id, student_id);
create unique index if not exists enrollments_class_roll_key on public.enrollments (class_id, roll_number);
create index if not exists enrollments_student_idx on public.enrollments (student_id);

create table if not exists public.teacher_assignments (
  id uuid primary key default gen_random_uuid(),
  teacher_id uuid not null references public.profiles(id) on delete cascade,
  class_id uuid not null references public.classes(id) on delete cascade,
  assigned_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now()
);
create unique index if not exists teacher_assignments_key on public.teacher_assignments (teacher_id, class_id);
create index if not exists teacher_assignments_class_idx on public.teacher_assignments (class_id);

create table if not exists public.coordinator_assignments (
  id uuid primary key default gen_random_uuid(),
  coordinator_id uuid not null references public.profiles(id) on delete cascade,
  scope_type public.coordinator_scope not null,
  department_id uuid references public.departments(id) on delete cascade,
  course_id uuid references public.courses(id) on delete cascade,
  semester_id uuid references public.semesters(id) on delete cascade,
  class_id uuid references public.classes(id) on delete cascade,
  assigned_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  constraint coordinator_scope_target check (
    (scope_type = 'department' and department_id is not null and course_id is null and semester_id is null and class_id is null)
    or (scope_type = 'course' and course_id is not null and department_id is null and semester_id is null and class_id is null)
    or (scope_type = 'semester' and semester_id is not null and department_id is null and course_id is null and class_id is null)
    or (scope_type = 'class' and class_id is not null and department_id is null and course_id is null and semester_id is null)
  )
);
create unique index if not exists coordinator_dept_key on public.coordinator_assignments (coordinator_id, department_id) where scope_type = 'department';
create unique index if not exists coordinator_course_key on public.coordinator_assignments (coordinator_id, course_id) where scope_type = 'course';
create unique index if not exists coordinator_semester_key on public.coordinator_assignments (coordinator_id, semester_id) where scope_type = 'semester';
create unique index if not exists coordinator_class_key on public.coordinator_assignments (coordinator_id, class_id) where scope_type = 'class';

-- Assignment role integrity: assignments only apply to appropriately-roled profiles.
create or replace function app.assert_teacher_role() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.profiles p where p.id = new.teacher_id and p.role = 'teacher') then
    raise exception 'teacher_assignments require a teacher profile' using errcode = '23514';
  end if;
  return new;
end $$;
create or replace function app.assert_coordinator_role() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if not exists (select 1 from public.profiles p where p.id = new.coordinator_id and p.role in ('coordinator','admin')) then
    raise exception 'coordinator_assignments require a coordinator profile' using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists teacher_assignments_role_check on public.teacher_assignments;
create trigger teacher_assignments_role_check before insert or update on public.teacher_assignments
  for each row execute function app.assert_teacher_role();
drop trigger if exists coordinator_assignments_role_check on public.coordinator_assignments;
create trigger coordinator_assignments_role_check before insert or update on public.coordinator_assignments
  for each row execute function app.assert_coordinator_role();

-- Scoped authorization helpers (security definer: avoids RLS recursion).
create or replace function app.teaches_class(target_class uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.teacher_assignments ta
    where ta.class_id = target_class and ta.teacher_id = auth.uid()
  )
$$;

create or replace function app.teaches_student(target_student uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from public.enrollments e
    join public.teacher_assignments ta on ta.class_id = e.class_id
    where e.student_id = target_student and ta.teacher_id = auth.uid()
  )
$$;

create or replace function app.coordinator_covers_class(target_class uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from public.coordinator_assignments ca
    join public.classes c on c.id = target_class
    join public.courses co on co.id = c.course_id
    where ca.coordinator_id = auth.uid()
      and (
        (ca.scope_type = 'class' and ca.class_id = c.id)
        or (ca.scope_type = 'semester' and ca.semester_id = c.semester_id)
        or (ca.scope_type = 'course' and ca.course_id = c.course_id)
        or (ca.scope_type = 'department' and ca.department_id = co.department_id)
      )
  )
$$;

create or replace function app.coordinator_covers_course(target_course uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from public.coordinator_assignments ca
    join public.courses co on co.id = target_course
    where ca.coordinator_id = auth.uid()
      and (
        (ca.scope_type = 'course' and ca.course_id = co.id)
        or (ca.scope_type = 'department' and ca.department_id = co.department_id)
      )
  )
$$;

create or replace function app.coordinator_covers_student(target_student uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from public.enrollments e
    join public.classes c on c.id = e.class_id
    join public.courses co on co.id = c.course_id
    left join public.coordinator_assignments ca on ca.coordinator_id = auth.uid()
    where e.student_id = target_student
      and (
        (ca.scope_type = 'class' and ca.class_id = c.id)
        or (ca.scope_type = 'semester' and ca.semester_id = c.semester_id)
        or (ca.scope_type = 'course' and ca.course_id = co.id)
        or (ca.scope_type = 'department' and ca.department_id = co.department_id)
      )
  )
$$;

create or replace function app.can_read_student(target_student uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select case
    when target_student is null then false
    when app.current_profile_id() is null then false
    when target_student = auth.uid() then true
    when app.is_admin() then true
    when app.has_role('teacher') then app.teaches_student(target_student)
    when app.has_role('coordinator') then app.coordinator_covers_student(target_student)
    else false
  end
$$;

alter table public.departments enable row level security;
alter table public.courses enable row level security;
alter table public.semesters enable row level security;
alter table public.batches enable row level security;
alter table public.classes enable row level security;
alter table public.enrollments enable row level security;
alter table public.teacher_assignments enable row level security;
alter table public.coordinator_assignments enable row level security;

-- Academic structure is read-only for authenticated users; admins manage it via the server.
revoke all on public.departments, public.courses, public.semesters, public.batches, public.classes,
  public.enrollments, public.teacher_assignments, public.coordinator_assignments from anon, authenticated;
grant select on public.departments, public.courses, public.semesters, public.batches, public.classes,
  public.enrollments, public.teacher_assignments, public.coordinator_assignments to authenticated;
grant select, insert, update, delete on public.departments, public.courses, public.semesters, public.batches, public.classes,
  public.enrollments, public.teacher_assignments, public.coordinator_assignments to service_role;
