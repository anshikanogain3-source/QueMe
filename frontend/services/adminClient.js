// QueMe administrative API client.
//
// All routes are served by the FastAPI backend under /api/v1/admin/*.  The
// React app never duplicates a single line of business logic; it only sends a
// request and renders the response.  The backend enforces require_admin / DB
// RLS on every operation, so authorization lives on the server.

const BASE = "/api/v1/admin";

async function request(path, options = {}) {
  const { method = "get", body, params, query, headers, token } = options;
  const url = new URL(`${BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  if (query) {
    Object.entries(query).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`);
    err.status = res.status;
    err.code = data?.code || "admin_error";
    err.data = data;
    throw err;
  }
  return data;
}

/**
 * Accounts, invitations, and lifecycle.
 */
export async function adminListAccounts({ page = 1, page_size = 25, q = "", role, status }) {
  return request("/accounts", { params: { page, page_size, q, role, status } });
}

export async function adminInviteAccount({ email, full_name, role }) {
  return request("/invitations", { method: "post", body: { email, full_name, role } });
}

export async function adminActivateAccount(id) {
  return request(`/accounts/${id}/activate`, { method: "post" });
}

export async function adminDeactivateAccount(id) {
  return request(`/accounts/${id}/deactivate`, { method: "post" });
}

/**
 * Academic structure.
 */
export async function adminListDepartments({ page = 1, page_size = 25, q = "" }) {
  return request("/departments", { params: { page, page_size, q } });
}

export async function adminCreateDepartment({ code, name }) {
  return request("/departments", { method: "post", body: { code, name } });
}

export async function adminUpdateDepartment(id, patch) {
  return request(`/departments/${id}`, { method: "patch", body: patch });
}

export async function adminListCourses({ page = 1, page_size = 25, q = "", department_id }) {
  return request("/courses", { params: { page, page_size, q, department_id } });
}

export async function adminCreateCourse({ department_id, code, name, program_level, duration_semesters }) {
  return request("/courses", { method: "post", body: { department_id, code, name, program_level, duration_semesters } });
}

export async function adminUpdateCourse(id, patch) {
  return request(`/courses/${id}`, { method: "patch", body: patch });
}

export async function adminListSemesters({ page = 1, page_size = 25, q = "", course_id }) {
  return request("/semesters", { params: { page, page_size, q, course_id } });
}

export async function adminCreateSemester({ course_id, number, label }) {
  return request("/semesters", { method: "post", body: { course_id, number, label } });
}

export async function adminUpdateSemester(id, patch) {
  return request(`/semesters/${id}`, { method: "patch", body: patch });
}

export async function adminListBatches({ page = 1, page_size = 25, q = "", course_id }) {
  return request("/batches", { params: { page, page_size, q, course_id } });
}

export async function adminCreateBatch({ course_id, start_year, label }) {
  return request("/batches", { method: "post", body: { course_id, start_year, label } });
}

export async function adminListClasses({ page = 1, page_size = 25, q = "", course_id, semester_id, batch_id }) {
  return request("/classes", { params: { page, page_size, q, course_id, semester_id, batch_id } });
}

export async function adminCreateClass({ course_id, semester_id, batch_id, section, name }) {
  return request("/classes", { method: "post", body: { course_id, semester_id, batch_id, section, name } });
}

/**
 * People management: enrollment, teacher assignment, coordinator scope,
 * interviews, audit trail.
 */
export async function adminListEnrollments({ page = 1, page_size = 25, q = "", class_id, status }) {
  return request("/enrollments", { params: { page, page_size, q, class_id, status } });
}

export async function adminCreateEnrollment({ student_id, class_id, status, notes }) {
  return request("/enrollments", { method: "post", body: { student_id, class_id, status, notes } });
}

export async function adminListTeacherAssignments({ page = 1, page_size = 25, q = "", class_id }) {
  return request("/teacher-assignments", { params: { page, page_size, q, class_id } });
}

export async function adminCreateTeacherAssignment({ teacher_id, class_id }) {
  return request("/teacher-assignments", { method: "post", body: { teacher_id, class_id } });
}

export async function adminListCoordinatorAssignments({ page = 1, page_size = 25, q = "", scope_type }) {
  return request("/coordinator-assignments", { params: { page, page_size, q, scope_type } });
}

export async function adminCreateCoordinatorAssignment({ coordinator_id, scope_type, class_id, semester_id, course_id, department_id }) {
  return request("/coordinator-assignments", { method: "post", body: { coordinator_id, scope_type, class_id, semester_id, course_id, department_id } });
}

export async function adminListInterviewAssignments({ page = 1, page_size = 25, q = "", student_id, class_id, status }) {
  return request("/interview-assignments", { params: { page, page_size, q, student_id, class_id, status } });
}

export async function adminCreateInterviewAssignment({ student_id, class_id, interview_type, target_role, experience_level, difficulty, question_target_count, due_at }) {
  return request("/interview-assignments", { method: "post", body: { student_id, class_id, interview_type, target_role, experience_level, difficulty, question_target_count, due_at } });
}

export async function adminUpdateInterviewAssignment(id, patch) {
  return request(`/interview-assignments/${id}`, { method: "patch", body: patch });
}

export async function adminListAuditEvents({ page = 1, page_size = 25, q = "", action, actor_id }) {
  return request("/audit-events", { params: { page, page_size, q, action, actor_id } });
}
