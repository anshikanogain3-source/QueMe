import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Eye,
  FileBarChart2,
  FileSpreadsheet,
  TrendingUp,
  Users,
} from "lucide-react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

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

function sessionScore(session) {
  const value = session.final_score ?? session.overall_score;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sessionName(session) {
  return session.student_name || session.student?.full_name || "Unknown student";
}

function sessionTitle(session) {
  return session.template_title || session.template?.title || session.title || "Interview";
}

function sessionDate(session) {
  return session.ended_at || session.completed_at || session.scheduled_at || null;
}

function PerformanceTrend({ sessions }) {
  const points = sessions
    .filter((session) => session.status === "COMPLETED" && sessionScore(session) !== null && sessionDate(session))
    .sort((a, b) => new Date(sessionDate(a)) - new Date(sessionDate(b)))
    .map((session) => ({ session, score: sessionScore(session) }));

  if (points.length < 2) {
    return (
      <div className="teacher-chart-empty">
        <TrendingUp size={20} aria-hidden="true" />
        <p>At least two scored interviews are needed to show a performance trend.</p>
      </div>
    );
  }

  const plotted = points.map(({ score }, index) => ({
    x: 38 + (index / (points.length - 1)) * 524,
    y: 145 - (Math.max(0, Math.min(10, score)) / 10) * 112,
  }));
  const line = plotted.map(({ x, y }) => `${x},${y}`).join(" ");
  const firstDate = new Date(sessionDate(points[0].session));
  const lastDate = new Date(sessionDate(points[points.length - 1].session));

  return (
    <div className="teacher-trend-chart">
      <div className="teacher-chart-scale" aria-hidden="true"><span>10</span><span>5</span><span>0</span></div>
      <svg viewBox="0 0 600 175" role="img" aria-label={`Interview scores from ${firstDate.toLocaleDateString()} to ${lastDate.toLocaleDateString()}`}>
        {[33, 89, 145].map((y) => <line key={y} x1="36" y1={y} x2="566" y2={y} className="teacher-chart-gridline" />)}
        <polyline points={line} className="teacher-chart-line" />
        {plotted.map(({ x, y }, index) => <circle key={`${x}-${index}`} cx={x} cy={y} r="4" className="teacher-chart-point" />)}
      </svg>
      <div className="teacher-chart-dates"><span>{firstDate.toLocaleDateString([], { month: "short", day: "numeric" })}</span><span>{lastDate.toLocaleDateString([], { month: "short", day: "numeric" })}</span></div>
    </div>
  );
}

export function TeacherReports() {
  const { user } = useAuth();
  const [interviews, setInterviews] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [statusFilter, setStatusFilter] = useState("COMPLETED");
  const [dateFilter, setDateFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      setLoading(true);
      const [sessionsData, analyticsData] = await Promise.all([
        api("/interviews").catch(() => []),
        api("/teacher/analytics").catch(() => null),
      ]);
      setInterviews(Array.isArray(sessionsData) ? sessionsData : []);
      setAnalytics(analyticsData);
    } catch (err) {
      setError(err?.message || "Failed to load reports and analytics.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  // Filter sessions
  const filteredInterviews = interviews.filter((s) => {
    if (statusFilter !== "all" && s.status !== statusFilter) return false;
    if (dateFilter !== "all") {
      const date = sessionDate(s);
      if (!date) return false;
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - Number(dateFilter));
      if (new Date(date) < cutoff) return false;
    }
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    return [sessionName(s), s.student_id, s.student?.email, sessionTitle(s)]
      .some((value) => String(value || "").toLowerCase().includes(q));
  });

  // Summaries are derived from the same interview records shown below.
  const completedList = interviews.filter((s) => s.status === "COMPLETED");
  const scoredList = completedList.filter((s) => sessionScore(s) !== null);
  const avgScore = scoredList.length
    ? (scoredList.reduce((total, session) => total + sessionScore(session), 0) / scoredList.length).toFixed(1)
    : "—";

  const completionRate = interviews.length
    ? `${Math.round((completedList.length / interviews.length) * 100)}%`
    : "0%";

  const studentStats = Object.values(interviews.reduce((byStudent, session) => {
    const studentId = session.student_id ?? session.student?.user_id;
    const name = sessionName(session);
    const key = studentId == null ? name : String(studentId);
    const student = byStudent[key] || {
      id: studentId,
      name,
      interviews: 0,
      scores: [],
      latestAt: null,
      latestCompletedId: null,
      latestCompletedAt: null,
    };
    student.interviews += 1;
    const score = sessionScore(session);
    if (session.status === "COMPLETED" && score !== null) student.scores.push(score);
    const date = sessionDate(session);
    if (date && (!student.latestAt || new Date(date) > new Date(student.latestAt))) {
      student.latestAt = date;
    }
    if (session.status === "COMPLETED" && (!student.latestCompletedAt || new Date(date || 0) >= new Date(student.latestCompletedAt))) {
      student.latestCompletedId = session.interview_id;
      student.latestCompletedAt = date;
    }
    byStudent[key] = student;
    return byStudent;
  }, {}))
    .map((student) => ({
      ...student,
      average: student.scores.length
        ? student.scores.reduce((sum, score) => sum + score, 0) / student.scores.length
        : null,
    }))
    .sort((a, b) => (b.average ?? -1) - (a.average ?? -1));
  const visibleStudentStats = studentStats.filter((student) =>
    !searchTerm.trim() || `${student.name} ${student.id ?? ""}`.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const statusCounts = ["COMPLETED", "SCHEDULED", "IN_PROGRESS", "CANCELLED"].map((status) => ({
    status,
    count: interviews.filter((session) => session.status === status).length,
  }));

  return (
    <TeacherWorkspace
      user={user}
      active="reports"
      pageTitle="Reports & Analytics"
      pageSubtitle="Monitor interview performance, student progress, and assessment reports."
      searchPlaceholder="Search student name, ID, or interview title..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="teacher-section">
        {error && (
          <div className="qm-alert qm-alert-error" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Summary metrics use live interview and analytics responses. */}
        <div className="teacher-kpi-grid">
          <div className="teacher-kpi-card">
            <div className="kpi-icon-wrap primary">
              <FileBarChart2 size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Total Interviews</span>
              <strong className="kpi-value">{analytics?.interview_count ?? interviews.length}</strong>
              <small className="kpi-sub">Assigned interview sessions</small>
            </div>
          </div>

          <div className="teacher-kpi-card">
            <div className="kpi-icon-wrap success">
              <CheckCircle2 size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Completed Interviews</span>
              <strong className="kpi-value">
                {analytics?.completed_interviews ?? completedList.length}
              </strong>
              <small className="kpi-sub">{completionRate} completion rate</small>
            </div>
          </div>

          <div className="teacher-kpi-card">
            <div className="kpi-icon-wrap info">
              <TrendingUp size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Average Score</span>
              <strong className="kpi-value">{analytics?.average_score != null ? Number(analytics.average_score).toFixed(1) : avgScore}<small className="kpi-unit">{(analytics?.average_score != null || avgScore !== "—") && "/10"}</small></strong>
              <small className="kpi-sub">Across scored interviews</small>
            </div>
          </div>

          <div className="teacher-kpi-card">
            <div className="kpi-icon-wrap warning">
              <Users size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Students with Interviews</span>
              <strong className="kpi-value">{analytics?.students_assigned ?? studentStats.length}</strong>
              <small className="kpi-sub">Students with assigned interviews</small>
            </div>
          </div>
        </div>

        <div className="teacher-analytics-grid">
          <section className="teacher-card teacher-chart-card">
            <div className="teacher-card-head">
              <div><h3>Interview Performance Trend</h3><p>Completed interview scores over time, on a 0–10 scale.</p></div>
            </div>
            {loading ? <div className="teacher-chart-empty">Loading score history…</div> : <PerformanceTrend sessions={interviews} />}
          </section>
          <section className="teacher-card teacher-chart-card">
            <div className="teacher-card-head">
              <div><h3>Interview Completion</h3><p>Session counts by current status.</p></div>
            </div>
            {interviews.length ? (
              <div className="teacher-status-chart">
                {statusCounts.filter(({ count }) => count > 0).map(({ status, count }) => (
                  <div className="teacher-status-row" key={status}>
                    <div><span>{status.replaceAll("_", " ").toLowerCase()}</span><strong>{count}</strong></div>
                    <div className="teacher-status-track"><span style={{ width: `${(count / interviews.length) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="teacher-chart-empty"><p>Interview status data will appear here when sessions are assigned.</p></div>
            )}
          </section>
        </div>

        {/* Filter and Control Bar */}
        <div className="teacher-card teacher-filter-toolbar">
          <div className="filter-pill-group">
            <button
              type="button"
              className={`filter-pill ${statusFilter === "COMPLETED" ? "active" : ""}`}
              onClick={() => setStatusFilter("COMPLETED")}
            >
              Completed ({interviews.filter((s) => s.status === "COMPLETED").length})
            </button>
            <button
              type="button"
              className={`filter-pill ${statusFilter === "all" ? "active" : ""}`}
              onClick={() => setStatusFilter("all")}
            >
              All Sessions ({interviews.length})
            </button>
            <button
              type="button"
              className={`filter-pill ${statusFilter === "SCHEDULED" ? "active" : ""}`}
              onClick={() => setStatusFilter("SCHEDULED")}
            >
              Scheduled ({interviews.filter((s) => s.status === "SCHEDULED").length})
            </button>
          </div>

          <div className="teacher-report-selectors">
            <label className="teacher-filter-select">
              <span>Date range</span>
              <select value={dateFilter} onChange={(event) => setDateFilter(event.target.value)} aria-label="Filter by date range">
                <option value="all">All dates</option>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
                <option value="365">Last 12 months</option>
              </select>
            </label>
          </div>
        </div>

        <section className="teacher-card teacher-student-performance">
          <div className="teacher-card-head">
            <div>
              <h3>Student Performance</h3>
              <p>Interview volume and average score for each student in your assigned sessions.</p>
            </div>
            <span className="teacher-card-meta">{visibleStudentStats.length} students</span>
          </div>
          {loading ? (
            <div className="teacher-empty-state"><div className="teacher-spinner" /><p>Loading student performance…</p></div>
          ) : visibleStudentStats.length === 0 ? (
            <div className="teacher-empty-state teacher-empty-compact">
              <Users size={28} className="teacher-empty-icon" />
              <p>{searchTerm ? "No students match this search." : "Student performance will appear after interviews are assigned."}</p>
            </div>
          ) : (
            <div className="teacher-table-responsive">
              <table className="teacher-table">
                <thead><tr><th>Student</th><th>Interviews</th><th>Average score</th><th>Last activity</th><th className="th-actions">Report</th></tr></thead>
                <tbody>
                  {visibleStudentStats.map((student) => (
                    <tr key={student.id ?? student.name}>
                      <td><div className="student-cell"><strong>{student.name}</strong><small>{student.id != null ? `Student ID ${student.id}` : "Student"}</small></div></td>
                      <td>{student.interviews}</td>
                      <td>{student.average != null ? <span className="score-badge"><strong>{student.average.toFixed(1)}/10</strong></span> : <span className="score-badge muted">Not scored</span>}</td>
                      <td><small className="date-cell">{formatDate(student.latestAt)}</small></td>
                      <td className="td-actions">{student.latestCompletedId ? <Link to={`/interviews/${student.latestCompletedId}/report`} className="teacher-outline-btn table-action-btn"><Eye size={13} /><span>View report</span></Link> : <span className="action-placeholder">No completed interview</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Reports Table Card */}
        <div className="teacher-card teacher-table-card">
          <div className="teacher-card-head">
            <div>
              <h3>Assessment Reports & Outcomes</h3>
              <p>Individual student transcripts, scoring metrics, and downloadable diagnostic files.</p>
            </div>
            <span className="teacher-card-meta">
              Showing {filteredInterviews.length} report entries
            </span>
          </div>

          {loading ? (
            <div className="teacher-empty-state">
              <div className="teacher-spinner" />
              <p>Loading assessment reports...</p>
            </div>
          ) : filteredInterviews.length === 0 ? (
            <div className="teacher-empty-state">
              <FileBarChart2 size={40} className="teacher-empty-icon" />
              <h3>No interview reports found</h3>
              <p>
                {searchTerm || statusFilter !== "all" || dateFilter !== "all"
                  ? "Try adjusting your search, date range, or status filter."
                  : "Completed student interviews and evaluations will appear here."}
              </p>
            </div>
          ) : (
            <div className="teacher-table-responsive">
              <table className="teacher-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Interview Title</th>
                    <th>Status</th>
                    <th>Score</th>
                    <th>Date Completed</th>
                    <th className="th-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredInterviews.map((session) => {
                    const score = sessionScore(session);
                    const isCompleted = session.status === "COMPLETED";

                    return (
                      <tr key={session.interview_id}>
                        <td>
                          <div className="student-cell">
                            <strong>{sessionName(session)}</strong>
                            <small>{session.student_id != null ? `Student ID ${session.student_id}` : session.student?.email || "—"}</small>
                          </div>
                        </td>
                        <td>
                          <div className="interview-title-cell">
                            <strong>{sessionTitle(session)}</strong>
                            <small>{session.template?.description || "Interview assessment"}</small>
                          </div>
                        </td>
                        <td>
                          <span className={`status-badge status-${session.status?.toLowerCase()}`}>
                            {session.status}
                          </span>
                        </td>
                        <td>
                          {score !== null ? (
                            <span className="score-badge">
                              <strong>{score.toFixed(1)}/10</strong>
                            </span>
                          ) : isCompleted ? (
                            <span className="score-badge muted">Pending</span>
                          ) : (
                            <span className="score-badge empty">—</span>
                          )}
                        </td>
                        <td>
                          <small className="date-cell">
                            {formatDate(sessionDate(session))}
                          </small>
                        </td>
                        <td className="td-actions">
                          {isCompleted ? (
                            <div className="action-buttons-group">
                              <Link
                                to={`/interviews/${session.interview_id}/report`}
                                className="teacher-outline-btn table-action-btn"
                                title="View Comprehensive Report"
                              >
                                <Eye size={13} />
                                <span>Report</span>
                              </Link>
                              <a
                                href={`/api/interviews/${session.interview_id}/report.pdf`}
                                target="_blank"
                                rel="noreferrer"
                                className="teacher-ghost-btn table-action-btn"
                                title="Download Official PDF Report"
                              >
                                <Download size={13} />
                                <span>PDF</span>
                              </a>
                              <a
                                href={`/api/interviews/${session.interview_id}/report.xlsx`}
                                target="_blank"
                                rel="noreferrer"
                                className="teacher-ghost-btn table-action-btn"
                                title="Download Excel Breakdown"
                              >
                                <FileSpreadsheet size={13} />
                                <span>XLSX</span>
                              </a>
                            </div>
                          ) : (
                            <span className="action-placeholder">Incomplete</span>
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
    </TeacherWorkspace>
  );
}

