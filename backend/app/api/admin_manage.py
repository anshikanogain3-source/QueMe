"""Administrator management endpoints (accounts, academic structure,
enrollments, assignments, interview assignments, audit trail).

Every route depends on require_admin: authorization is enforced on the
server, never by UI visibility. Writes run as service_role, and every
mutation records an audit event with the acting administrator."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import Principal, require_admin
from ..config import Settings, get_settings
from ..database import connect_database
from ..schemas import (
    BatchCreate, BatchUpdate, ClassCreate, ClassUpdate,
    CoordinatorAssignmentCreate, CourseCreate, CourseUpdate,
    DepartmentCreate, EnrollmentCreate, InterviewAssignmentCreate,
    InterviewAssignmentUpdate, InviteAccount, PageResult,
    SemesterCreate, SemesterUpdate, TeacherAssignmentCreate, CreateManagedUser,
)
from .admin import _create_auth_user, _delete_auth_user

router = APIRouter(prefix="/admin", tags=["administration"])


def _pg_error(exc: asyncpg.PostgresError) -> HTTPException | None:
    """Map database errors to friendly, non-leaky HTTP responses."""
    if isinstance(exc, asyncpg.UniqueViolationError):
        return HTTPException(status_code=409, detail="A record with these values already exists.")
    if isinstance(exc, asyncpg.ForeignKeyViolationError):
        return HTTPException(status_code=409, detail="The referenced record does not exist, or it is still in use by other data.")
    if isinstance(exc, asyncpg.CheckViolationError):
        return HTTPException(status_code=422, detail=f"A value violates a data rule: {exc.message or exc.constraint_name}")
    if isinstance(exc, asyncpg.exceptions.PermissionDeniedError):
        return HTTPException(status_code=403, detail=exc.message)
    if isinstance(exc, asyncpg.exceptions.NoDataFoundError):
        return HTTPException(status_code=404, detail="The requested record was not found.")
    return None


async def _exec(conn: asyncpg.Connection, sql: str, *args):
    try:
        return await conn.execute(sql, *args)
    except asyncpg.PostgresError as exc:
        mapped = _pg_error(exc)
        if mapped:
            raise mapped from exc
        raise


async def _audit(
    conn: asyncpg.Connection,
    principal: Principal,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    description: str,
    metadata: dict | None = None,
) -> None:
    await _exec(
        conn,
        """
        insert into public.audit_events (actor_id, action, entity_type, entity_id, description, metadata)
        values ($1, $2, $3, $4, $5, $6)
        """,
        principal.user_id, action, entity_type, entity_id, description, json.dumps(metadata or {}),
    )


@asynccontextmanager
async def _admin_db(settings: Settings):
    conn = await connect_database(settings)
    try:
        await _exec(conn, "set role service_role")
        yield conn
    finally:
        await conn.close()


async def _list(
    conn: asyncpg.Connection,
    select_sql: str,
    count_sql: str,
    params: list,
    page: int,
    page_size: int,
) -> dict:
    total = await conn.fetchval(count_sql, *params) if params else await conn.fetchval(count_sql)
    rows = await conn.fetch(
        f"{select_sql} limit ${len(params) + 1} offset ${len(params) + 2}",
        *params, page_size, (page - 1) * page_size,
    )
    return {"items": [dict(row) for row in rows], "total": total or 0, "page": page, "page_size": page_size}


async def _fetch_profile(conn: asyncpg.Connection, user_id: UUID) -> dict:
    row = await conn.fetchrow("select id, email, full_name, role::text as role, status::text as status from public.profiles where id = $1", user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return dict(row)


async def _require_role(conn: asyncpg.Connection, user_id: UUID, expected: str, what: str) -> None:
    row = await conn.fetchrow("select role::text as role from public.profiles where id = $1", user_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} account not found.")
    if row["role"] != expected:
        raise HTTPException(status_code=422, detail=f"This operation requires a {expected} account.")


async def _fetchrow(conn: asyncpg.Connection, sql: str, *args):
    try:
        return await conn.fetchrow(sql, *args)
    except asyncpg.PostgresError as exc:
        mapped = _pg_error(exc)
        if mapped:
            raise mapped from exc
        raise


def _set_clause(data: dict) -> tuple[str, list]:
    values = []
    parts = []
    for index, (key, value) in enumerate(data.items(), start=1):
        parts.append(f"{key} = ${index}")
        values.append(value)
    return ", ".join(parts), values


# ---------------------------------------------------------------- accounts

@router.get("/accounts", response_model=PageResult)
async def list_accounts(
    search: str | None = Query(default=None, max_length=120),
    role: str | None = Query(default=None, max_length=30),
    status: str | None = Query(default=None, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "(email ilike $1 or full_name ilike $1) and ($2 = '' or role::text = $2) and ($3 = '' or status::text = $3)"
    params = [f"%{search}%" if search else "", role or "", status or ""]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select id, email, full_name, role::text as role, status::text as status, "
            "activated_at, created_at from public.profiles "
            f"where {where} order by created_at desc",
            f"select count(*) from public.profiles where {where}",
            params, page, page_size,
        )


@router.post("/invitations", status_code=201)
async def invite_account(
    payload: InviteAccount,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Invite a student/teacher/coordinator: creates the Auth account, assigns
    the role through the audited admin RPC, and returns a single-use invite
    link (works without outbound email)."""
    try:
        user = await _create_auth_user(
            CreateManagedUser(email=payload.email, full_name=payload.full_name, role=payload.role),
            settings,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
        raise
    try:
        async with _admin_db(settings) as conn:
            async with conn.transaction():
                await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", principal.user_id)
                await _exec(conn, "select app.set_profile_role($1::uuid, $2::public.app_role)", user["id"], payload.role)
            await _audit(
                conn, principal, "account.invited", "profile", UUID(user["id"]),
                f"Invited {payload.email} as {payload.role}.", {"role": payload.role},
            )
    except Exception:
        await _delete_auth_user(user["id"], settings)
        raise

    invite_link = None
    if settings.supabase_url and settings.supabase_service_role_key:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/generate_link",
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                },
                json={"type": "invite", "email": payload.email},
            )
        if response.status_code == 200:
            invite_link = response.json().get("action_link")
    return {"id": user["id"], "email": payload.email, "role": payload.role, "invite_link": invite_link}


async def _change_status(user_id: UUID, status: str, principal: Principal, settings: Settings) -> dict:
    async with _admin_db(settings) as conn:
        profile = await _fetch_profile(conn, user_id)
        if user_id == UUID(principal.user_id) and status != "active":
            raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
        if status != "active" and profile["role"] == "admin" and profile["status"] == "active":
            active_admins = await conn.fetchval(
                "select count(*) from public.profiles where role = 'admin' and status = 'active'"
            )
            if (active_admins or 0) <= 1:
                raise HTTPException(status_code=409, detail="The last active administrator cannot be deactivated.")
        async with conn.transaction():
            await conn.execute("select set_config('request.jwt.claim.sub', $1, true)", principal.user_id)
            await _exec(conn, "select app.set_profile_status($1::uuid, $2::public.profile_status)", user_id, status)
        return await _fetch_profile(conn, user_id)


@router.post("/accounts/{user_id}/activate")
async def activate_account(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    return await _change_status(user_id, "active", principal, settings)


@router.post("/accounts/{user_id}/deactivate")
async def deactivate_account(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Deactivation is reversible and never deletes data; permanent deletion
    is the separate DELETE endpoint below."""
    return await _change_status(user_id, "deactivated", principal, settings)


@router.delete("/accounts/{user_id}")
async def delete_account(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        profile = await _fetch_profile(conn, user_id)
        if user_id == UUID(principal.user_id):
            raise HTTPException(status_code=409, detail="You cannot delete your own account.")
        if profile["role"] == "admin":
            others = await conn.fetchval(
                "select count(*) from public.profiles where role = 'admin' and id <> $1", user_id
            )
            if not others:
                raise HTTPException(status_code=409, detail="The last administrator cannot be deleted; deactivate instead.")
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Account deletion is not configured.")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.delete(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Account not found.")
    if response.status_code >= 400:
        raise HTTPException(status_code=503, detail="The account could not be deleted.")
    async with _admin_db(settings) as conn:
        await _audit(
            conn, principal, "account.deleted", "profile", user_id,
            f"Permanently deleted account {profile['email']}.",
            {"email": profile["email"], "role": profile["role"], "status": profile["status"]},
        )
    return {"deleted": True, "email": profile["email"]}


# ------------------------------------------------------- academic structure

@router.get("/departments", response_model=PageResult)
async def list_departments(
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1 = '' or code ilike $1 or name ilike $1)"
    params = [f"%{search}%" if search else ""]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            f"select id, code, name, created_at from public.departments where {where} order by code",
            f"select count(*) from public.departments where {where}",
            params, page, page_size,
        )


@router.post("/departments", status_code=201)
async def create_department(
    payload: DepartmentCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "insert into public.departments (code, name) values ($1, $2) "
            "returning id, code, name, created_at",
            payload.code, payload.name,
        )
        await _audit(conn, principal, "department.created", "department", row["id"],
                     f"Created department {payload.code}.", {"code": payload.code})
        return dict(row)


@router.get("/courses", response_model=PageResult)
async def list_courses(
    department_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1 = '' or c.code ilike $1 or c.name ilike $1) and ($2::uuid is null or c.department_id = $2) and ($3 or c.is_active)"
    params: list = [f"%{search}%" if search else "", department_id, include_inactive]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select c.id, c.department_id, c.code, c.name, c.program_level, "
            "c.duration_semesters, c.is_active, c.created_at, d.code as department_code "
            "from public.courses c join public.departments d on d.id = c.department_id "
            f"where {where} order by c.code",
            f"select count(*) from public.courses c where {where}",
            params, page, page_size,
        )


@router.post("/courses", status_code=201)
async def create_course(
    payload: CourseCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "insert into public.courses (department_id, code, name, program_level, duration_semesters, is_active) "
            "values ($1, $2, $3, $4, $5, $6) "
            "returning id, department_id, code, name, program_level, duration_semesters, is_active, created_at",
            payload.department_id, payload.code, payload.name,
            payload.program_level, payload.duration_semesters, payload.is_active,
        )
        await _audit(conn, principal, "course.created", "course", row["id"],
                     f"Created course {payload.code}.", {"code": payload.code, "name": payload.name})
        return dict(row)


@router.patch("/courses/{course_id}")
async def update_course(
    course_id: UUID,
    payload: CourseUpdate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update.")
    sets, values = _set_clause(data)
    values.append(course_id)
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            f"update public.courses set {sets} where id = ${len(values)} "
            "returning id, department_id, code, name, program_level, duration_semesters, is_active",
            *values,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        await _audit(conn, principal, "course.updated", "course", course_id,
                     f"Updated course {row['code']}.", {"fields": sorted(data)})
        return dict(row)


@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(conn, "delete from public.courses where id = $1 returning id, code", course_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        await _audit(conn, principal, "course.deleted", "course", course_id,
                     f"Deleted course {row['code']}.", {"code": row["code"]})
    return {"deleted": True}


@router.get("/semesters", response_model=PageResult)
async def list_semesters(
    course_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1::uuid is null or s.course_id = $1)"
    params: list = [course_id]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select s.id, s.course_id, s.number, s.label, s.created_at, c.code as course_code "
            "from public.semesters s join public.courses c on c.id = s.course_id "
            f"where {where} order by s.number",
            f"select count(*) from public.semesters s where {where}",
            params, page, page_size,
        )


@router.post("/semesters", status_code=201)
async def create_semester(
    payload: SemesterCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "insert into public.semesters (course_id, number, label) values ($1, $2, $3) "
            "returning id, course_id, number, label, created_at",
            payload.course_id, payload.number, payload.label,
        )
        await _audit(conn, principal, "semester.created", "semester", row["id"],
                     f"Created semester {payload.number} ({payload.label}).", {"number": payload.number})
        return dict(row)


@router.patch("/semesters/{semester_id}")
async def update_semester(
    semester_id: UUID,
    payload: SemesterUpdate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update.")
    sets, values = _set_clause(data)
    values.append(semester_id)
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            f"update public.semesters set {sets} where id = ${len(values)} "
            "returning id, course_id, number, label",
            *values,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Semester not found.")
        await _audit(conn, principal, "semester.updated", "semester", semester_id,
                     "Updated semester.", {"fields": sorted(data)})
        return dict(row)


@router.delete("/semesters/{semester_id}")
async def delete_semester(
    semester_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(conn, "delete from public.semesters where id = $1 returning id, number", semester_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Semester not found.")
        await _audit(conn, principal, "semester.deleted", "semester", semester_id,
                     f"Deleted semester {row['number']}.", {"number": row["number"]})
    return {"deleted": True}


@router.get("/batches", response_model=PageResult)
async def list_batches(
    course_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1::uuid is null or b.course_id = $1)"
    params: list = [course_id]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select b.id, b.course_id, b.start_year, b.label, b.created_at, c.code as course_code "
            "from public.batches b join public.courses c on c.id = b.course_id "
            f"where {where} order by b.start_year desc",
            f"select count(*) from public.batches b where {where}",
            params, page, page_size,
        )


@router.post("/batches", status_code=201)
async def create_batch(
    payload: BatchCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "insert into public.batches (course_id, start_year, label) values ($1, $2, $3) "
            "returning id, course_id, start_year, label, created_at",
            payload.course_id, payload.start_year, payload.label,
        )
        await _audit(conn, principal, "batch.created", "batch", row["id"],
                     f"Created batch {payload.label} ({payload.start_year}).", {"start_year": payload.start_year})
        return dict(row)


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(conn, "delete from public.batches where id = $1 returning id, label", batch_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Batch not found.")
        await _audit(conn, principal, "batch.deleted", "batch", batch_id,
                     f"Deleted batch {row['label']}.", {"label": row["label"]})
    return {"deleted": True}


@router.get("/classes", response_model=PageResult)
async def list_classes(
    course_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1 = '' or cl.name ilike $1 or cl.section ilike $1) and ($2::uuid is null or cl.course_id = $2)"
    params: list = [f"%{search}%" if search else "", course_id]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select cl.id, cl.course_id, cl.semester_id, cl.batch_id, cl.section, cl.name, cl.created_at, "
            "co.code as course_code, s.label as semester_label, b.label as batch_label "
            "from public.classes cl "
            "join public.courses co on co.id = cl.course_id "
            "join public.semesters s on s.id = cl.semester_id "
            "join public.batches b on b.id = cl.batch_id "
            f"where {where} order by co.code, s.number, b.start_year, cl.section",
            f"select count(*) from public.classes cl where {where}",
            params, page, page_size,
        )


@router.post("/classes", status_code=201)
async def create_class(
    payload: ClassCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "insert into public.classes (course_id, semester_id, batch_id, section, name) "
            "values ($1, $2, $3, $4, $5) "
            "returning id, course_id, semester_id, batch_id, section, name, created_at",
            payload.course_id, payload.semester_id, payload.batch_id, payload.section, payload.name,
        )
        await _audit(conn, principal, "class.created", "class", row["id"],
                     f"Created class {payload.name} (section {payload.section}).",
                     {"section": payload.section, "course_id": str(payload.course_id)})
        return dict(row)


@router.patch("/classes/{class_id}")
async def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update.")
    sets, values = _set_clause(data)
    values.append(class_id)
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            f"update public.classes set {sets} where id = ${len(values)} "
            "returning id, course_id, semester_id, batch_id, section, name",
            *values,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Class not found.")
        await _audit(conn, principal, "class.updated", "class", class_id,
                     f"Updated class {row['name']}.", {"fields": sorted(data)})
        return dict(row)


@router.delete("/classes/{class_id}")
async def delete_class(
    class_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(conn, "delete from public.classes where id = $1 returning id, name", class_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Class not found.")
        await _audit(conn, principal, "class.deleted", "class", class_id,
                     f"Deleted class {row['name']}.", {"name": row["name"]})
    return {"deleted": True}


# ------------------------------------------------- enrollment & assignments

@router.get("/enrollments", response_model=PageResult)
async def list_enrollments(
    class_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "(p.email ilike $1 or p.full_name ilike $1) and ($2::uuid is null or e.class_id = $2)"
    params: list = [f"%{search}%" if search else "", class_id]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select e.id, e.student_id, e.class_id, e.status::text as status, e.enrolled_at, e.notes, "
            "p.email as student_email, p.full_name as student_name, c.name as class_name, "
            "co.code as course_code "
            "from public.enrollments e "
            "join public.profiles p on p.id = e.student_id "
            "join public.classes c on c.id = e.class_id "
            "join public.courses co on co.id = c.course_id "
            f"where {where} order by e.enrolled_at desc",
            "select count(*) from public.enrollments e join public.profiles p on p.id = e.student_id "
            f"where {where}",
            params, page, page_size,
        )


@router.post("/enrollments", status_code=201)
async def create_enrollment(
    payload: EnrollmentCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        await _require_role(conn, payload.student_id, "student", "Student")
        try:
            row = await _fetchrow(
                conn,
                "insert into public.enrollments (student_id, class_id, status, notes) "
                "values ($1, $2, $3::public.enrollment_status, $4) "
                "returning id, student_id, class_id, status::text as status, enrolled_at, notes",
                payload.student_id, payload.class_id, payload.status, payload.notes,
            )
        except HTTPException as exc:
            if exc.status_code == 409 and "already exists" in exc.detail:
                raise HTTPException(status_code=409, detail="This student is already enrolled in that class.") from exc
            raise
        await _audit(conn, principal, "student.enrolled", "enrollment", row["id"],
                     f"Enrolled student in class {payload.class_id}.",
                     {"student_id": str(payload.student_id), "class_id": str(payload.class_id),
                      "status": payload.status})
        return dict(row)


@router.delete("/enrollments/{enrollment_id}")
async def delete_enrollment(
    enrollment_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "delete from public.enrollments where id = $1 returning id, student_id, class_id, status::text as status",
            enrollment_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Enrollment not found.")
        await _audit(conn, principal, "enrollment.removed", "enrollment", enrollment_id,
                     "Removed student enrollment.",
                     {"student_id": str(row["student_id"]), "class_id": str(row["class_id"]),
                      "previous_status": row["status"]})
    return {"deleted": True}


@router.get("/teacher-assignments", response_model=PageResult)
async def list_teacher_assignments(
    class_id: UUID | None = None,
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "(p.email ilike $1 or p.full_name ilike $1) and ($2::uuid is null or ta.class_id = $2)"
    params: list = [f"%{search}%" if search else "", class_id]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select ta.id, ta.teacher_id, ta.class_id, ta.assigned_at, "
            "p.email as teacher_email, p.full_name as teacher_name, c.name as class_name "
            "from public.teacher_assignments ta "
            "join public.profiles p on p.id = ta.teacher_id "
            "join public.classes c on c.id = ta.class_id "
            f"where {where} order by p.email, c.name",
            "select count(*) from public.teacher_assignments ta "
            "join public.profiles p on p.id = ta.teacher_id "
            f"where {where}",
            params, page, page_size,
        )


@router.post("/teacher-assignments", status_code=201)
async def create_teacher_assignment(
    payload: TeacherAssignmentCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        await _require_role(conn, payload.teacher_id, "teacher", "Teacher")
        try:
            row = await _fetchrow(
                conn,
                "insert into public.teacher_assignments (teacher_id, class_id, assigned_by) "
                "values ($1, $2, $3) returning id, teacher_id, class_id, assigned_at",
                payload.teacher_id, payload.class_id, principal.user_id,
            )
        except HTTPException as exc:
            if exc.status_code == 409 and "already exists" in exc.detail:
                raise HTTPException(status_code=409, detail="This teacher is already assigned to that class.") from exc
            raise
        await _audit(conn, principal, "teacher.assigned", "teacher_assignment", row["id"],
                     "Assigned teacher to class.",
                     {"teacher_id": str(payload.teacher_id), "class_id": str(payload.class_id)})
        return dict(row)


@router.delete("/teacher-assignments/{assignment_id}")
async def delete_teacher_assignment(
    assignment_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "delete from public.teacher_assignments where id = $1 returning id, teacher_id, class_id",
            assignment_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Teacher assignment not found.")
        await _audit(conn, principal, "teacher.unassigned", "teacher_assignment", assignment_id,
                     "Removed teacher from class.",
                     {"teacher_id": str(row["teacher_id"]), "class_id": str(row["class_id"])})
    return {"deleted": True}


@router.get("/coordinator-assignments", response_model=PageResult)
async def list_coordinator_assignments(
    scope_type: str | None = Query(default=None, max_length=20),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "(p.email ilike $1 or p.full_name ilike $1) and ($2 = '' or ca.scope_type::text = $2)"
    params: list = [f"%{search}%" if search else "", scope_type or ""]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select ca.id, ca.coordinator_id, ca.scope_type::text as scope_type, "
            "ca.class_id, ca.semester_id, ca.course_id, ca.department_id, ca.assigned_at, "
            "p.email as coordinator_email, p.full_name as coordinator_name "
            "from public.coordinator_assignments ca "
            "join public.profiles p on p.id = ca.coordinator_id "
            f"where {where} order by p.email",
            "select count(*) from public.coordinator_assignments ca "
            "join public.profiles p on p.id = ca.coordinator_id "
            f"where {where}",
            params, page, page_size,
        )


@router.post("/coordinator-assignments", status_code=201)
async def create_coordinator_assignment(
    payload: CoordinatorAssignmentCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        await _require_role(conn, payload.coordinator_id, "coordinator", "Coordinator")
        try:
            row = await _fetchrow(
                conn,
                "insert into public.coordinator_assignments "
                "(coordinator_id, scope_type, class_id, semester_id, course_id, department_id, assigned_by) "
                "values ($1, $2::public.coordinator_scope, $3, $4, $5, $6, $7) "
                "returning id, coordinator_id, scope_type::text as scope_type, "
                "class_id, semester_id, course_id, department_id, assigned_at",
                payload.coordinator_id, payload.scope_type, payload.class_id,
                payload.semester_id, payload.course_id, payload.department_id, principal.user_id,
            )
        except HTTPException as exc:
            if exc.status_code == 409 and "already exists" in exc.detail:
                raise HTTPException(status_code=409, detail="That coordinator scope is already assigned.") from exc
            raise
        await _audit(conn, principal, "coordinator.assigned", "coordinator_assignment", row["id"],
                     f"Assigned coordinator to {payload.scope_type} scope.",
                     {"coordinator_id": str(payload.coordinator_id), "scope_type": payload.scope_type})
        return dict(row)


@router.delete("/coordinator-assignments/{assignment_id}")
async def delete_coordinator_assignment(
    assignment_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "delete from public.coordinator_assignments where id = $1 "
            "returning id, coordinator_id, scope_type::text as scope_type",
            assignment_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Coordinator assignment not found.")
        await _audit(conn, principal, "coordinator.unassigned", "coordinator_assignment", assignment_id,
                     f"Removed coordinator {row['scope_type']} scope.",
                     {"coordinator_id": str(row["coordinator_id"]), "scope_type": row["scope_type"]})
    return {"deleted": True}


# ------------------------------------------------------ interview assignments

@router.get("/interview-assignments", response_model=PageResult)
async def list_interview_assignments(
    class_id: UUID | None = None,
    status: str | None = Query(default=None, max_length=30),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = ("(p.email ilike $1 or p.full_name ilike $1) "
             "and ($2::uuid is null or ia.class_id = $2) "
             "and ($3 = '' or ia.status = $3)")
    params: list = [f"%{search}%" if search else "", class_id, status or ""]
    async with _admin_db(settings) as conn:
        return await _list(
            conn,
            "select ia.id, ia.student_id, ia.class_id, ia.interview_type, ia.target_role, "
            "ia.experience_level, ia.difficulty, ia.question_target_count, ia.due_at, "
            "ia.status, ia.created_at, "
            "p.email as student_email, p.full_name as student_name, c.name as class_name "
            "from public.interview_assignments ia "
            "join public.profiles p on p.id = ia.student_id "
            "join public.classes c on c.id = ia.class_id "
            f"where {where} order by ia.created_at desc",
            "select count(*) from public.interview_assignments ia "
            "join public.profiles p on p.id = ia.student_id "
            f"where {where}",
            params, page, page_size,
        )


@router.post("/interview-assignments", status_code=201)
async def create_interview_assignment(
    payload: InterviewAssignmentCreate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        await _require_role(conn, payload.student_id, "student", "Student")
        enrolled = await conn.fetchval(
            "select exists(select 1 from public.enrollments where student_id = $1 and class_id = $2)",
            payload.student_id, payload.class_id,
        )
        if not enrolled:
            raise HTTPException(status_code=409, detail="This student is not enrolled in the selected class.")
        row = await _fetchrow(
            conn,
            "insert into public.interview_assignments "
            "(student_id, class_id, created_by, interview_type, target_role, experience_level, "
            " difficulty, question_target_count, due_at) "
            "values ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
            "returning id, student_id, class_id, interview_type, target_role, experience_level, "
            "difficulty, question_target_count, due_at, status, created_at",
            payload.student_id, payload.class_id, principal.user_id,
            payload.interview_type, payload.target_role, payload.experience_level,
            payload.difficulty, payload.question_target_count, payload.due_at,
        )
        await _audit(conn, principal, "interview.assigned", "interview_assignment", row["id"],
                     f"Assigned interview {payload.interview_type} to student.",
                     {"student_id": str(payload.student_id), "class_id": str(payload.class_id),
                      "due_at": payload.due_at.isoformat() if payload.due_at else None})
        return dict(row)


@router.patch("/interview-assignments/{assignment_id}")
async def update_interview_assignment(
    assignment_id: UUID,
    payload: InterviewAssignmentUpdate,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=422, detail="No fields provided to update.")
    sets, values = _set_clause(data)
    values.append(assignment_id)
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            f"update public.interview_assignments set {sets} where id = ${len(values)} "
            "returning id, student_id, class_id, interview_type, target_role, experience_level, "
            "difficulty, question_target_count, due_at, status",
            *values,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Interview assignment not found.")
        await _audit(conn, principal, "interview.assignment_updated", "interview_assignment", assignment_id,
                     "Updated interview assignment.", {"fields": sorted(data)})
        return dict(row)


@router.delete("/interview-assignments/{assignment_id}")
async def delete_interview_assignment(
    assignment_id: UUID,
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    async with _admin_db(settings) as conn:
        row = await _fetchrow(
            conn,
            "delete from public.interview_assignments where id = $1 returning id, student_id, interview_type",
            assignment_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Interview assignment not found.")
        await _audit(conn, principal, "interview.assignment_removed", "interview_assignment", assignment_id,
                     f"Removed interview assignment {row['interview_type']}.",
                     {"student_id": str(row["student_id"]), "interview_type": row["interview_type"]})
    return {"deleted": True}


# ------------------------------------------------------------------ audit log

@router.get("/audit-events", response_model=PageResult)
async def list_audit_events(
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    principal: Principal = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    where = "($1 = '' or a.action ilike $1) and ($2 = '' or a.entity_type = $2)"
    params: list = [f"%{action}%" if action else "", entity_type or ""]
    async with _admin_db(settings) as conn:
        result = await _list(
            conn,
            "select a.id, a.action, a.entity_type, a.entity_id, a.description, a.metadata, "
            "a.created_at, coalesce(p.email, '(deleted user)') as actor_email "
            "from public.audit_events a "
            "left join public.profiles p on p.id = a.actor_id "
            f"where {where} order by a.created_at desc",
            f"select count(*) from public.audit_events a where {where}",
            params, page, page_size,
        )
    for item in result["items"]:
        metadata = item.get("metadata")
        if isinstance(metadata, str):
            try:
                item["metadata"] = json.loads(metadata or "{}")
            except ValueError:
                item["metadata"] = {}
    return result


