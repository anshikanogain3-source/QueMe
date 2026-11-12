import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Eye,
  FileBarChart2,
  FileSpreadsheet,
  FileText,
  Filter,
  GraduationCap,
  Search,
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

export function AdminReports({ user }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [exporting, setExporting] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);

  function flash(msg) {
    setNotice(msg);
    window.setTimeout(() => setNotice(""), 4000);
  }

  function fail(err) {
    setError(err?.message || "Operation failed.");
    window.setTimeout(() => setError(""), 5000);
  }

  async function loadReports() {
    try {
      setLoading(true);
      const data = await api("/admin/reports");
      setReports(Array.isArray(data) ? data : []);
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReports();
  }, []);

  async function handleExportAll() {
    try {
      setExporting(true);
      const blob = await api("/admin/reports.xlsx");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `queme-campus-reports-${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      flash("Exported all campus reports to Excel.");
    } catch (err) {
      fail(err);
    } finally {
      setExporting(false);
    }
  }

  async function handleDownloadIndividual(path, filename) {
    try {
      setDownloadingId(path);
      const blob = await api(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      fail(err);
    } finally {
      setDownloadingId(null);
    }
  }

  // Filter reports
  const filteredReports = reports.filter((r) => {
    if (statusFilter !== "all" && r.report_status !== statusFilter) return false;
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    const candidateMatch = r.student_name?.toLowerCase().includes(q);
    const teacherMatch = r.teacher_name?.toLowerCase().includes(q);
    const titleMatch = r.template_title?.toLowerCase().includes(q);
    return candidateMatch || teacherMatch || titleMatch;
  });

  return (
    <AdminWorkspace
      user={user}
      active="reports"
      pageTitle="Campus Interview Reports"
      pageSubtitle="Comprehensive evaluation records, AI diagnostic scores, teacher sign-offs, and data exports."
      searchPlaceholder="Search candidate, instructor, or interview title..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
      actions={
        <button
          type="button"
          className="admin-primary-btn"
          onClick={handleExportAll}
          disabled={exporting}
        >
          <FileSpreadsheet size={15} />
          <span>{exporting ? "Exporting..." : "Export All Reports (.xlsx)"}</span>
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

        {/* Filter Bar */}
        <div className="admin-card admin-filter-toolbar">
          <div className="filter-pill-group">
            <button
              type="button"
              className={`filter-pill ${statusFilter === "all" ? "active" : ""}`}
              onClick={() => setStatusFilter("all")}
            >
              All Reports ({reports.length})
            </button>
            <button
              type="button"
              className={`filter-pill ${statusFilter === "PUBLISHED" ? "active" : ""}`}
              onClick={() => setStatusFilter("PUBLISHED")}
            >
              Published ({reports.filter((r) => r.report_status === "PUBLISHED").length})
            </button>
            <button
              type="button"
              className={`filter-pill alert-pill ${statusFilter === "NEEDS_REVIEW" ? "active" : ""}`}
              onClick={() => setStatusFilter("NEEDS_REVIEW")}
            >
              Needs Review ({reports.filter((r) => r.report_status === "NEEDS_REVIEW").length})
            </button>
          </div>

          <div className="admin-card-meta">
            Showing {filteredReports.length} of {reports.length} campus assessment records
          </div>
        </div>

        {/* Reports Table Card */}
        <div className="admin-card admin-table-card">
          <div className="admin-card-head">
            <div>
              <h3>Institutional Assessment Records</h3>
              <p>Evaluated interview sessions, scoring breakdowns, and printable PDF/Excel archives.</p>
            </div>
          </div>

          {loading ? (
            <div className="admin-empty-state">
              <div className="admin-spinner" />
              <p>Loading campus reports...</p>
            </div>
          ) : filteredReports.length === 0 ? (
            <div className="admin-empty-state">
              <FileBarChart2 size={40} className="admin-empty-icon" />
              <h3>No interview reports found</h3>
              <p>
                {searchTerm || statusFilter !== "all"
                  ? "Try adjusting your search query or status filter."
                  : "Completed candidate interviews will generate evaluation reports here."}
              </p>
            </div>
          ) : (
            <div className="admin-table-responsive">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Interview Title</th>
                    <th>Instructor</th>
                    <th>Final Score</th>
                    <th>Status</th>
                    <th>Date</th>
                    <th className="th-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredReports.map((report) => (
                    <tr key={report.report_id}>
                      <td>
                        <div className="candidate-cell">
                          <strong>{report.student_name || "Unknown Candidate"}</strong>
                          <small>Student ID: #{report.student_id || "—"}</small>
                        </div>
                      </td>
                      <td>
                        <div className="interview-title-cell">
                          <strong>
                            {report.template_title || `Interview #${report.interview_id}`}
                          </strong>
                          <small>Session #{report.interview_id}</small>
                        </div>
                      </td>
                      <td>
                        <span className="teacher-name-cell">
                          {report.teacher_name || "Self-practice"}
                        </span>
                      </td>
                      <td>
                        {report.final_score != null ? (
                          <span className="score-badge">
                            <strong>{report.final_score}%</strong>
                          </span>
                        ) : (
                          <span className="score-badge muted">Pending review</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={`status-badge status-${report.report_status?.toLowerCase()}`}
                        >
                          {report.report_status?.replaceAll("_", " ")}
                        </span>
                      </td>
                      <td>
                        <small className="date-cell">{formatDate(report.created_at)}</small>
                      </td>
                      <td className="td-actions">
                        <div className="action-buttons-group">
                          <Link
                            to={`/interviews/${report.interview_id}/report`}
                            className="admin-outline-btn table-action-btn"
                            title="View Full Report"
                          >
                            <Eye size={13} />
                            <span>View</span>
                          </Link>
                          <button
                            type="button"
                            className="admin-ghost-btn table-action-btn"
                            disabled={downloadingId === `/interviews/${report.interview_id}/report.pdf`}
                            onClick={() =>
                              handleDownloadIndividual(
                                `/interviews/${report.interview_id}/report.pdf`,
                                `queme-interview-${report.interview_id}.pdf`
                              )
                            }
                            title="Download PDF"
                          >
                            <Download size={13} />
                            <span>PDF</span>
                          </button>
                          <button
                            type="button"
                            className="admin-ghost-btn table-action-btn"
                            disabled={downloadingId === `/interviews/${report.interview_id}/report.xlsx`}
                            onClick={() =>
                              handleDownloadIndividual(
                                `/interviews/${report.interview_id}/report.xlsx`,
                                `queme-interview-${report.interview_id}.xlsx`
                              )
                            }
                            title="Download XLSX"
                          >
                            <FileSpreadsheet size={13} />
                            <span>XLSX</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AdminWorkspace>
  );
}

