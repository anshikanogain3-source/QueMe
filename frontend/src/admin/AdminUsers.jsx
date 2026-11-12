import { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Filter,
  GraduationCap,
  Mail,
  Search,
  ShieldAlert,
  UserCheck,
  UserMinus,
  Users,
  XCircle,
} from "lucide-react";
import { api } from "../api.js";
import { AdminWorkspace } from "./AdminWorkspace.jsx";

export function AdminUsers({ user }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("all"); // 'all' | 'pending' | 'students' | 'teachers'
  const [statusFilter, setStatusFilter] = useState("all"); // 'all' | 'ACTIVE' | 'PENDING' | 'REJECTED'
  const [processingId, setProcessingId] = useState(null);

  function flash(msg) {
    setNotice(msg);
    window.setTimeout(() => setNotice(""), 4000);
  }

  function fail(err) {
    setError(err?.message || "Operation failed.");
    window.setTimeout(() => setError(""), 5000);
  }

  async function loadUsers() {
    try {
      setLoading(true);
      const data = await api("/admin/users");
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  async function handleUpdateStatus(userId, status) {
    try {
      setProcessingId(userId);
      setError("");
      await api(`/admin/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ account_status: status }),
      });
      setUsers((prev) =>
        prev.map((u) => (u.user_id === userId ? { ...u, account_status: status } : u))
      );
      flash(`User account has been set to ${status}.`);
    } catch (err) {
      fail(err);
    } finally {
      setProcessingId(null);
    }
  }

  // Filter accounts
  const pendingCount = users.filter((u) => u.account_status === "PENDING").length;
  const studentsCount = users.filter((u) => u.role === "student").length;
  const teachersCount = users.filter((u) => u.role === "teacher").length;

  const filteredUsers = users.filter((u) => {
    if (activeTab === "pending" && u.account_status !== "PENDING") return false;
    if (activeTab === "students" && u.role !== "student") return false;
    if (activeTab === "teachers" && u.role !== "teacher") return false;

    if (activeTab !== "pending" && statusFilter !== "all" && u.account_status !== statusFilter) {
      return false;
    }

    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    const nameMatch = u.full_name?.toLowerCase().includes(q);
    const emailMatch = u.email?.toLowerCase().includes(q);
    const rollMatch = u.student_profile?.roll_number?.toLowerCase().includes(q);
    const empMatch = u.teacher_profile?.employee_id?.toLowerCase().includes(q);
    return nameMatch || emailMatch || rollMatch || empMatch;
  });

  return (
    <AdminWorkspace
      user={user}
      active="users"
      pageTitle="User & Access Management"
      pageSubtitle="Authorize student and faculty accounts, verify academic credentials, and manage platform permissions."
      searchPlaceholder="Search by name, email, roll number, or employee ID..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="admin-section">
        {error && (
          <div className="qm-alert qm-alert-error" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
        {notice && (
          <div className="qm-alert qm-alert-success" role="status">
            <CheckCircle2 size={16} />
            <span>{notice}</span>
          </div>
        )}

        {/* Directory Navigation Tabs & Secondary Filters */}
        <div className="admin-card admin-filter-toolbar">
          <div className="filter-pill-group">
            <button
              type="button"
              className={`filter-pill ${activeTab === "all" ? "active" : ""}`}
              onClick={() => setActiveTab("all")}
            >
              All Users ({users.length})
            </button>
            <button
              type="button"
              className={`filter-pill alert-pill ${activeTab === "pending" ? "active" : ""}`}
              onClick={() => setActiveTab("pending")}
            >
              Pending Approval ({pendingCount})
            </button>
            <button
              type="button"
              className={`filter-pill ${activeTab === "students" ? "active" : ""}`}
              onClick={() => setActiveTab("students")}
            >
              Students ({studentsCount})
            </button>
            <button
              type="button"
              className={`filter-pill ${activeTab === "teachers" ? "active" : ""}`}
              onClick={() => setActiveTab("teachers")}
            >
              Faculty ({teachersCount})
            </button>
          </div>

          {activeTab !== "pending" && (
            <div className="status-dropdown-wrap">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="status-select"
                aria-label="Filter by account status"
              >
                <option value="all">All Account Statuses</option>
                <option value="ACTIVE">Active Accounts</option>
                <option value="PENDING">Pending Accounts</option>
                <option value="REJECTED">Rejected Accounts</option>
              </select>
            </div>
          )}
        </div>

        {/* Users Table Card */}
        <div className="admin-card admin-table-card">
          <div className="admin-card-head">
            <div>
              <h3>Campus Directory</h3>
              <p>Registered university members, academic profiles, and authorization status.</p>
            </div>
            <span className="admin-card-meta">
              Showing {filteredUsers.length} of {users.length} accounts
            </span>
          </div>

          {loading ? (
            <div className="admin-empty-state">
              <div className="admin-spinner" />
              <p>Loading user accounts...</p>
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="admin-empty-state">
              <Users size={40} className="admin-empty-icon" />
              <h3>No users found</h3>
              <p>
                {searchTerm || statusFilter !== "all" || activeTab !== "all"
                  ? "Try resetting your search query or role filter."
                  : "Registered accounts will appear here."}
              </p>
            </div>
          ) : (
            <div className="admin-table-responsive">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>User &amp; Contact</th>
                    <th>Role</th>
                    <th>Academic Details</th>
                    <th>Account Status</th>
                    <th className="th-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((person) => {
                    const isStudent = person.role === "student";
                    const isTeacher = person.role === "teacher";
                    const isSelf = person.user_id === user?.user_id;
                    const isPending = person.account_status === "PENDING";
                    const isActive = person.account_status === "ACTIVE";

                    return (
                      <tr key={person.user_id}>
                        <td>
                          <div className="user-profile-cell">
                            <span className="avatar user-table-avatar">
                              {person.full_name?.[0]?.toUpperCase() || "U"}
                            </span>
                            <div className="user-table-copy">
                              <strong>{person.full_name}</strong>
                              <small>{person.email}</small>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className={`role-badge role-${person.role}`}>{person.role}</span>
                        </td>
                        <td>
                          {isStudent && person.student_profile ? (
                            <div className="academic-cell">
                              <span>
                                Roll: <strong>{person.student_profile.roll_number || "—"}</strong>
                              </span>
                              <small>
                                {person.student_profile.batch?.course?.code || "Course"} &middot; Sem{" "}
                                {person.student_profile.batch?.semester || "—"}
                              </small>
                            </div>
                          ) : isTeacher && person.teacher_profile ? (
                            <div className="academic-cell">
                              <span>
                                Emp ID:{" "}
                                <strong>{person.teacher_profile.employee_id || "—"}</strong>
                              </span>
                              <small>Department Faculty</small>
                            </div>
                          ) : (
                            <span className="muted-dash">—</span>
                          )}
                        </td>
                        <td>
                          <span
                            className={`status-badge status-${person.account_status?.toLowerCase()}`}
                          >
                            {person.account_status}
                          </span>
                        </td>
                        <td className="td-actions">
                          {isSelf ? (
                            <span className="action-placeholder">Current Admin</span>
                          ) : (
                            <div className="action-buttons-group">
                              {isPending ? (
                                <>
                                  <button
                                    type="button"
                                    className="admin-primary-btn table-action-btn"
                                    disabled={processingId === person.user_id}
                                    onClick={() => handleUpdateStatus(person.user_id, "ACTIVE")}
                                  >
                                    <UserCheck size={13} />
                                    <span>Approve</span>
                                  </button>
                                  <button
                                    type="button"
                                    className="admin-danger-btn table-action-btn"
                                    disabled={processingId === person.user_id}
                                    onClick={() => handleUpdateStatus(person.user_id, "REJECTED")}
                                  >
                                    <XCircle size={13} />
                                    <span>Reject</span>
                                  </button>
                                </>
                              ) : isActive ? (
                                <button
                                  type="button"
                                  className="admin-outline-btn table-action-btn"
                                  disabled={processingId === person.user_id}
                                  onClick={() => handleUpdateStatus(person.user_id, "REJECTED")}
                                  title="Revoke access"
                                >
                                  <UserMinus size={13} />
                                  <span>Deactivate</span>
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="admin-primary-btn table-action-btn"
                                  disabled={processingId === person.user_id}
                                  onClick={() => handleUpdateStatus(person.user_id, "ACTIVE")}
                                  title="Reactivate account"
                                >
                                  <UserCheck size={13} />
                                  <span>Reactivate</span>
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AdminWorkspace>
  );
}

