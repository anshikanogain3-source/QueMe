// Admin screens: every screen is a thin presentational layer over
// adminClient.js, which calls the real FastAPI backend.  Authorization is
// server-side (require_admin + DB RLS); nothing here trusts the sidebar.
import React from "react";
import { Navigate } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  Input,
  Notice,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
} from "../design-system/index.js";
import AdminLayout, { StatusPill, useAdminTitle } from "../routing/AdminLayout.jsx";
import {
  Pager,
  ConfirmDialog,
  useAdminToast,
  EmptyStateAction,
} from "./admin-ui.jsx";
import {
  adminListAccounts,
  adminInviteAccount,
  adminActivateAccount,
  adminDeactivateAccount,
  adminListDepartments,
  adminCreateDepartment,
  adminUpdateDepartment,
  adminListCourses,
  adminCreateCourse,
  adminUpdateCourse,
  adminListSemesters,
  adminCreateSemester,
  adminUpdateSemester,
  adminListBatches,
  adminCreateBatch,
  adminUpdateBatch,
  adminListClasses,
  adminCreateClass,
  adminUpdateClass,
  adminListEnrollments,
  adminCreateEnrollment,
  adminListTeacherAssignments,
  adminCreateTeacherAssignment,
  adminListCoordinatorAssignments,
  adminCreateCoordinatorAssignment,
  adminListInterviewAssignments,
  adminCreateInterviewAssignment,
  adminUpdateInterviewAssignment,
  adminListAuditEvents,
} from "../services/adminClient.js";

// ---------------------------------------------------------------------------
// Base table wiring for list endpoints.
// ---------------------------------------------------------------------------

export function PagedList({
  title,
  description,
  columns,
  fetchList,
  onRefresh,
  renderAction,
}) {
  const [items, setItems] = React.useState([]);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchList({ page, page_size: 25 })
      .then((data) => {
        if (active) {
          setItems(data.items || []);
          setTotal(data.total || 0);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err);
          setLoading(false);
        }
      });
    return () => { active = false; };
  }, [page, fetchList]);

  return (
    <section>
      <PageHeader
        eyebrow="Administration"
        title={title}
        description={description}
        actions={onRefresh ? <Button variant="secondary" size="sm" onClick={onRefresh}>Refresh</Button> : undefined}
      />
      {loading ? (
        <div className="qm-stack qm-stack--lg">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} variant="text" width="100%" />
          ))}
        </div>
      ) : error ? (
        <Notice tone="danger" title="Unable to load records">{error?.data?.detail || error?.message}</Notice>
      ) : items.length === 0 ? (
        <EmptyStateAction title="No records yet" message="Add an item to get started." action={() => {}} />
      ) : (
        <div className="qm-table-wrapper">
          <table className="qm-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col.accessor} scope="col">{col.header}</th>
                ))}
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  {columns.map((col) => (
                    <td key={col.accessor}>{col.cell ? col.cell(item) : String(item[col.accessor] ?? "--"))}</td>
                  ))}
                  <td>
                    <div className="qm-table__actions">
                      {renderAction ? renderAction(item) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pager
        page={page}
        page_size={25}
        total={total}
        onPage={setPage}
        currentLabel="Showing"
      />
    </section>
  );
}

/** Small action button used inside paged tables. */
export function ActionButton({ icon, label, tone = "ghost", onClick }) {
  return (
    <IconButton label={label} variant={tone} size="sm" onClick={onClick} title={label}>
      {icon}
    </IconButton>
  );
}

// ---------------------------------------------------------------------------
// Shared modal form: single-purpose dialog, always with a submit button.
// ---------------------------------------------------------------------------

export function FormDialog({
  open,
  onClose,
  title,
  submitLabel,
  submitting,
  fields,
  onSubmit,
  initialValues,
  description,
}) {
  const [values, setValues] = React.useState(initialValues || {});
  const [errors, setErrors] = React.useState({});

  React.useEffect(() => {
    if (open) {
      setValues(initialValues || {});
      setErrors({});
    }
  }, [open, initialValues]);

  const handleChange = (patch) => {
    setValues((prev) => ({ ...prev, ...patch }));
    setErrors({});
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(values);
  };

  return (
    <Dialog open={open} onClose={onClose} title={title} size="md">
      {description && <p className="qm-dialog__desc">{description}</p>}
      <form onSubmit={handleSubmit} noValidate>
        {fields.map((f) => (
          <Field
            key={f.name}
            label={f.label}
            hint={f.hint}
            error={errors[f.name]}
            required={f.required}
            className="qm-mb-3"
          >
            {f.component === "input" && (
              <Input
                value={values[f.name] != null ? values[f.name] : ""}
                onChange={(e) => handleChange({ [f.name]: e.target.value })}
                placeholder={f.placeholder}
              />
            )}
            {f.component === "textarea" && (
              <Textarea
                rows={f.rows || 4}
                value={values[f.name] != null ? values[f.name] : ""}
                onChange={(e) => handleChange({ [f.name]: e.target.value })}
                placeholder={f.placeholder}
              />
            )}
            {f.component === "select" && (
              <Select
                value={values[f.name] != null ? values[f.name] : ""}
                onChange={(e) => handleChange({ [f.name]: e.target.value })}
              >
                {f.options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            )}
            {f.component === "checkbox" && (
              <Checkbox
                checked={Boolean(values[f.name] || f.default)}
                onChange={(e) => handleChange({ [f.name]: e.target.checked })}
              >
                {f.label}
              </Checkbox>
            )}
          </Field>
        ))}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--qm-space-3)", marginTop: "var(--qm-space-6)" }}>
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Views
// ---------------------------------------------------------------------------

export default function AdminDashboard({ onLogout }) {
  const { header } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  return (
    <div className="qm-dashboard qm-dashboard--admin">
      <div className="qm-dashboard__stats qm-grid qm-grid--4">
        <Card className="qm-card--pad-md">
          <p className="qm-stat__label">Accounts</p>
          <p className="qm-stat__value qm-mono">0</p>
          <p className="qm-stat__hint qm-muted">Active + pending + invited</p>
        </Card>
        <Card className="qm-card--pad-md">
          <p className="qm-stat__label">Classes</p>
          <p className="qm-stat__value qm-mono">0</p>
          <p className="qm-stat__hint qm-muted">Active courses</p>
        </Card>
        <Card className="qm-card--pad-md">
          <p className="qm-stat__label">Teachers</p>
          <p className="qm-stat__value qm-mono">0</p>
          <p className="qm-stat__hint qm-muted">Assigned to classes</p>
        </Card>
        <Card className="qm-card--pad-md">
          <p className="qm-stat__label">Interviews assigned</p>
          <p className="qm-stat__value qm-mono">0</p>
          <p className="qm-stat__hint qm-muted">Open assignments</p>
        </Card>
      </div>
      <div className="qm-stack">
        <Button variant="primary" size="md" onClick={() => {}}>
          Invite new account
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

export function AdminAccounts({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "full_name", header: "Name" },
    { accessor: "email", header: "Email" },
    { accessor: "role", header: "Role" },
    { accessor: "status", header: "Status", cell: (r) => <StatusPill status={r.status} /> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Accounts"
          description="Manage students, teachers, and coordinators."
          columns={columns}
          fetchList={adminListAccounts}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// Invitations
// ---------------------------------------------------------------------------

export function AdminInvitations({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Invitations"
          description="Sent invitations waiting for activation."
          columns={[
            { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
            { accessor: "email", header: "Email" },
            { accessor: "role", header: "Role" },
            { accessor: "created_at", header: "Sent at" },
          ]}
          fetchList={adminListInvitations}
          onRefresh={() => {}}
          renderAction={(row) => (
            <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
          )}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// Academic structure
// ---------------------------------------------------------------------------

export function AdminDepartments({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "code", header: "Code" },
    { accessor: "name", header: "Name" },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Departments"
          description="Higher-level academic units that group courses."
          columns={columns}
          fetchList={adminListDepartments}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminCourses({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "code", header: "Code" },
    { accessor: "name", header: "Name" },
    { accessor: "program_level", header: "Program level" },
    { accessor: "duration_semesters", header: "Semesters", cell: (r) => <strong>{r.duration_semesters}</strong> },
    { accessor: "is_active", header: "Active", cell: (r) => <StatusPill status={r.is_active ? "active" : "inactive"} /> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Courses"
          description="Degree or certificate programs."
          columns={columns}
          fetchList={adminListCourses}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminSemesters({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "course_id", header: "Course", cell: (r) => <code className="qm-mono qm-nowrap">{r.course_id.slice(0, 8)}</code> },
    { accessor: "number", header: "Number" },
    { accessor: "label", header: "Label" },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Semesters"
          description="Academic terms within a course."
          columns={columns}
          fetchList={adminListSemesters}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminBatches({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "course_id", header: "Course", cell: (r) => <code className="qm-mono qm-nowrap">{r.course_id.slice(0, 8)}</code> },
    { accessor: "start_year", header: "Start year" },
    { accessor: "label", header: "Label" },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Batches"
          description="Cohorts entering a course in a given year."
          columns={columns}
          fetchList={adminListBatches}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminClasses({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "course_id", header: "Course", cell: (r) => <code className="qm-mono qm-nowrap">{r.course_id.slice(0, 8)}</code> },
    { accessor: "semester_id", header: "Semester", cell: (r) => <code className="qm-mono qm-nowrap">{r.semester_id.slice(0, 8)}</code> },
    { accessor: "batch_id", header: "Batch", cell: (r) => <code className="qm-mono qm-nowrap">{r.batch_id.slice(0, 8)}</code> },
    { accessor: "section", header: "Section" },
    { accessor: "name", header: "Name" },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Classes"
          description="Sections of a course in a given semester and batch."
          columns={columns}
          fetchList={adminListClasses}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// People management
// ---------------------------------------------------------------------------

export function AdminEnrollments({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "student_id", header: "Student", cell: (r) => <code className="qm-mono qm-nowrap">{r.student_id.slice(0, 8)}</code> },
    { accessor: "class_id", header: "Class", cell: (r) => <code className="qm-mono qm-nowrap">{r.class_id.slice(0, 8)}</code> },
    { accessor: "status", header: "Status", cell: (r) => <StatusPill status={r.status} /> },
    { accessor: "notes", header: "Notes", cell: (r) => <span className="qm-muted">{r.notes || ""}</span> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Enrollments"
          description="Students enrolled in classes."
          columns={columns}
          fetchList={adminListEnrollments}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminTeacherAssignments({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "teacher_id", header: "Teacher", cell: (r) => <code className="qm-mono qm-nowrap">{r.teacher_id.slice(0, 8)}</code> },
    { accessor: "class_id", header: "Class", cell: (r) => <code className="qm-mono qm-nowrap">{r.class_id.slice(0, 8)}</code> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Teacher assignments"
          description="Teachers assigned to classes."
          columns={columns}
          fetchList={adminListTeacherAssignments}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

export function AdminCoordinatorAssignments({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "coordinator_id", header: "Coordinator", cell: (r) => <code className="qm-mono qm-nowrap">{r.coordinator_id.slice(0, 8)}</code> },
    { accessor: "scope_type", header: "Scope" },
    { accessor: "class_id", header: "Class", cell: (r) => <code className="qm-mono qm-nowrap">{r.class_id?.slice(0, 8) || "--"}</code> },
    { accessor: "semester_id", header: "Semester", cell: (r) => <code className="qm-mono qm-nowrap">{r.semester_id?.slice(0, 8) || "--"}</code> },
    { accessor: "course_id", header: "Course", cell: (r) => <code className="qm-mono qm-nowrap">{r.course_id?.slice(0, 8) || "--"}</code> },
    { accessor: "department_id", header: "Department", cell: (r) => <code className="qm-mono qm-nowrap">{r.department_id?.slice(0, 8) || "--"}</code> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Coordinator scope"
          description="Which classes, semesters, courses, or departments a coordinator is responsible for."
          columns={columns}
          fetchList={adminListCoordinatorAssignments}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// Interviews
// ---------------------------------------------------------------------------

export function AdminInterviewAssignments({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "student_id", header: "Student", cell: (r) => <code className="qm-mono qm-nowrap">{r.student_id.slice(0, 8)}</code> },
    { accessor: "class_id", header: "Class", cell: (r) => <code className="qm-mono qm-nowrap">{r.class_id.slice(0, 8)}</code> },
    { accessor: "interview_type", header: "Type" },
    { accessor: "target_role", header: "Target role" },
    { accessor: "experience_level", header: "Experience", cell: (r) => <Badge tone="neutral" size="sm">{r.experience_level}</Badge> },
    { accessor: "difficulty", header: "Difficulty", cell: (r) => <Badge tone="neutral" size="sm">{r.difficulty}</Badge> },
    { accessor: "due_at", header: "Due", cell: (r) => <span className="qm-muted">{r.due_at ? new Date(r.due_at).toLocaleString() : "—"}</span> },
    { accessor: "status", header: "Status", cell: (r) => <StatusPill status={r.status} /> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Interview assignments"
          description="Assignments of interviews to students in classes."
          columns={columns}
          fetchList={adminListInterviewAssignments}
          onRefresh={() => {}}
          renderAction={(row) => (
            <>
              <ActionButton icon="✎" label="Edit" onClick={() => {}} />
              <ActionButton icon="🗑" label="Delete" tone="danger" onClick={() => {}} />
            </>
          )}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export function AdminAuditLog({ onLogout }) {
  const { header, subtitle } = useAdminTitle();
  const { showError, showSuccess } = useAdminToast({ onShowError: showError, onShowSuccess: showSuccess });
  const columns = React.useMemo(() => [
    { accessor: "id", header: "ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.id.slice(0, 8)}</code> },
    { accessor: "actor_id", header: "Actor", cell: (r) => <code className="qm-mono qm-nowrap">{r.actor_id.slice(0, 8)}</code> },
    { accessor: "action", header: "Action" },
    { accessor: "entity_type", header: "Entity" },
    { accessor: "entity_id", header: "Entity ID", cell: (r) => <code className="qm-mono qm-nowrap">{r.entity_id?.slice(0, 8) || "--"}</code> },
    { accessor: "created_at", header: "At", cell: (r) => <span className="qm-muted">{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</span> },
  ], []);
  return (
    <AdminLayout>
      <div className="qm-stack qm-stack--lg">
        <PagedList
          title="Audit log"
          description="Administrative changes recorded by the system."
          columns={columns}
          fetchList={adminListAuditEvents}
          onRefresh={() => {}}
        />
      </div>
    </AdminLayout>
  );
}

// ---------------------------------------------------------------------------
// Role-aware view wrapper (kept for compatibility with the router).
// ---------------------------------------------------------------------------

export default function AdminRoutes({ onLogout }) {
  return <Outlet />;
}
