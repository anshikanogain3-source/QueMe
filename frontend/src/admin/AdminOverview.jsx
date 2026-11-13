import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  Download,
  FileBarChart2,
  FileSpreadsheet,
  FileText,
  GraduationCap,
  Scale,
  Settings2,
  ShieldCheck,
  TrendingUp,
  UserCheck,
  Users,
  XCircle,
} from "lucide-react";
import { api } from "../api.js";
import { AdminWorkspace } from "./AdminWorkspace.jsx";

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AdminOverview({ user }) {
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [pendingUsers, setPendingUsers] = useState([]);
  const [recentReports, setRecentReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [processingId, setProcessingId] = useState(null);
  const [exporting, setExporting] = useState(false);

  async function loadData() {
    try {
      setLoading(true);
      const [stats, accountRows, reportRows] = await Promise.all([
        api("/admin/analytics").catch(() => null),
        api("/admin/users?account_status=PENDING").catch(() => []),
        api("/admin/reports").catch(() => []),
      ]);
      setAnalytics(stats);
      setPendingUsers(Array.isArray(accountRows) ? accountRows : []);
      setRecentReports(Array.isArray(reportRows) ? reportRows.slice(0, 5) : []);
    } catch (err) {
      setError(err?.message || "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function flash(msg) {
    setNotice(msg);
    window.setTimeout(() => setNotice(""), 4000);
  }

  async function handleUpdateStatus(userId, status) {
    try {
      setProcessingId(userId);
      setError("");
      await api(`/admin/users/${userId}/status`, {
        method: "POST",
        body: JSON.stringify({ account_status: status }),
      });
      setPendingUsers((prev) => prev.filter((p) => p.user_id !== userId));
      flash(`Account ${status === "ACTIVE" ? "approved" : "rejected"} successfully.`);
      // Refresh stats
      api("/admin/analytics").then(setAnalytics).catch(() => {});
    } catch (err) {
      setError(err?.message || "Failed to update user status.");
    } finally {
      setProcessingId(null);
    }
  }

  async function handleExportReports() {
    try {
      setExporting(true);
      const blob = await api("/admin/reports.xlsx");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `queme-campus-reports-${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      flash("Exported campus reports spreadsheet.");
    } catch (err) {
      setError(err?.message || "Failed to export reports.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <AdminWorkspace
      user={user}
      active="overview"
      pageTitle="Platform Overview"
      pageSubtitle="Institutional metrics, pending candidate authorizations, and campus-wide interview performance."
      actions={
        <button
          type="button"
          className="admin-primary-btn"
          onClick={handleExportReports}
          disabled={exporting}
        >
          <FileSpreadsheet size={15} />
          <span>{exporting ? "Exporting..." : "Export Reports (.xlsx)"}</span>
        </button>
      }
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

        {/* Welcome Banner */}
        <div className="admin-welcome-banner">
          <div className="welcome-banner-copy">
            <span className="eyebrow-tag">CAMPUS GOVERNANCE</span>
            <h2>Welcome back, {user?.full_name?.split(" ")[0] || "Administrator"}.</h2>
            <p>
              Here is your high-level overview of campus user activity, interview completion rates,
              and pending account verifications.
            </p>
          </div>
          <div className="welcome-banner-actions">
            <Link to="/admin/users" className="admin-outline-btn welcome-action-btn">
              <Users size={15} />
              <span>Manage Accounts</span>
            </Link>
            <Link to="/admin/reports" className="admin-primary-btn welcome-action-btn">
              <FileBarChart2 size={15} />
              <span>View All Reports</span>
            </Link>
          </div>
        </div>

        {/* 6 Essential KPI Cards */}
        <div className="admin-kpi-grid">
          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap primary">
              <Users size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Active Students</span>
              <strong className="kpi-value">{analytics?.active_students ?? "—"}</strong>
              <small className="kpi-sub">Enrolled &amp; authorized</small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap success">
              <GraduationCap size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Active Faculty</span>
              <strong className="kpi-value">{analytics?.active_teachers ?? "—"}</strong>
              <small className="kpi-sub">Instructors &amp; evaluators</small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap info">
              <BarChart3 size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Total Interviews</span>
              <strong className="kpi-value">{analytics?.interview_count ?? "—"}</strong>
              <small className="kpi-sub">
                {analytics?.completed_interviews ?? 0} completed
              </small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap purple">
              <TrendingUp size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Average Score</span>
              <strong className="kpi-value">
                {analytics?.average_score != null ? `${Number(analytics.average_score).toFixed(1)}/10` : "—"}
              </strong>
              <small className="kpi-sub">Across campus evaluations</small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap warning">
              <UserCheck size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Pending Accounts</span>
              <strong className="kpi-value">{pendingUsers.length}</strong>
              <small className="kpi-sub">Awaiting verification</small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap danger">
              <FileText size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Reports Needing Review</span>
              <strong className="kpi-value">
                {analytics?.reports_needing_review ?? 0}
              </strong>
              <small className="kpi-sub">Pending faculty sign-off</small>
            </div>
          </div>
        </div>

        {/* 2-Column Split: Actionable Pending Approvals & Quick Shortcuts */}
        <div className="admin-overview-grid">
          {/* Urgent Pending Approvals */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Pending Account Approvals</h3>
                <p>New student and faculty registrations awaiting your administrative approval.</p>
              </div>
              <Link to="/admin/users" className="admin-card-link">
                <span>View all</span>
                <ArrowRight size={13} />
              </Link>
            </div>

            {loading ? (
              <div className="admin-empty-state compact">
                <div className="admin-spinner" />
                <p>Loading registrations...</p>
              </div>
            ) : pendingUsers.length === 0 ? (
              <div className="admin-empty-state compact">
                <CheckCircle2 size={36} className="admin-empty-icon text-success" />
                <h4>No pending accounts</h4>
                <p>All student and instructor registrations have been reviewed.</p>
              </div>
            ) : (
              <div className="admin-approval-list">
                {pendingUsers.slice(0, 5).map((person) => (
                  <div key={person.user_id} className="admin-approval-item">
                    <div className="approval-user-info">
                      <div className="avatar user-sm-avatar">
                        {person.full_name?.[0]?.toUpperCase() || "U"}
                      </div>
                      <div className="approval-user-copy">
                        <div className="user-name-role">
                          <strong>{person.full_name}</strong>
                          <span className={`role-badge role-${person.role}`}>{person.role}</span>
                        </div>
                        <span className="user-email">{person.email}</span>
                      </div>
                    </div>
                    <div className="approval-actions">
                      <button
                        type="button"
                        className="admin-primary-btn btn-sm"
                        disabled={processingId === person.user_id}
                        onClick={() => handleUpdateStatus(person.user_id, "ACTIVE")}
                      >
                        <UserCheck size={13} />
                        <span>Approve</span>
                      </button>
                      <button
                        type="button"
                        className="admin-danger-btn btn-sm"
                        disabled={processingId === person.user_id}
                        onClick={() => handleUpdateStatus(person.user_id, "REJECTED")}
                      >
                        <XCircle size={13} />
                        <span>Reject</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Access & Recent Reports Card */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Recent Campus Interviews</h3>
                <p>Latest completed assessments across academic cohorts.</p>
              </div>
              <Link to="/admin/reports" className="admin-card-link">
                <span>View all reports</span>
                <ArrowRight size={13} />
              </Link>
            </div>

            {loading ? (
              <div className="admin-empty-state compact">
                <div className="admin-spinner" />
                <p>Loading recent reports...</p>
              </div>
            ) : recentReports.length === 0 ? (
              <div className="admin-empty-state compact">
                <FileBarChart2 size={36} className="admin-empty-icon" />
                <h4>No interview reports yet</h4>
                <p>Completed interview reports will appear here automatically.</p>
              </div>
            ) : (
              <div className="admin-recent-reports-list">
                {recentReports.map((report) => (
                  <div key={report.report_id} className="recent-report-row">
                    <div className="recent-report-info">
                      <strong>{report.template_title || `Interview #${report.interview_id}`}</strong>
                      <span className="recent-report-sub">
                        {report.student_name || "Student"} &middot;{" "}
                        {report.final_score != null ? `${Number(report.final_score).toFixed(1)}/10` : "Pending score"}
                      </span>
                    </div>
                    <Link
                      to={`/interviews/${report.interview_id}/report`}
                      className="admin-outline-btn btn-sm"
                    >
                      View Report
                    </Link>
                  </div>
                ))}
              </div>
            )}

            <div className="admin-quick-links-panel">
              <span className="quick-links-title">Quick Administration Actions</span>
              <div className="quick-links-grid">
                <Link to="/admin/settings" className="quick-link-tile">
                  <Settings2 size={16} />
                  <span>Configure Scoring Weights</span>
                </Link>
                <Link to="/admin/settings" className="quick-link-tile">
                  <GraduationCap size={16} />
                  <span>Create Class Cohort</span>
                </Link>
                <Link to="/admin/analytics" className="quick-link-tile">
                  <TrendingUp size={16} />
                  <span>Validation Analytics</span>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AdminWorkspace>
  );
}

