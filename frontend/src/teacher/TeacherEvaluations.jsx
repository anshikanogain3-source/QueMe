import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  Award,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  FileBarChart2,
  Search,
  User,
} from "lucide-react";
import { api } from "../api.js";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

export function TeacherEvaluations({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [evalFilter, setEvalFilter] = useState("all"); // 'all' | 'pending' | 'reviewed'
  const [searchTerm, setSearchTerm] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    api("/interviews")
      .then((data) => {
        if (active) {
          // Evaluations only apply to completed interviews
          const completed = (data || []).filter((i) => i.status === "COMPLETED");
          setInterviews(completed);
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const counts = useMemo(() => {
    const pending = interviews.filter((i) => i.teacher_review_status === "PENDING").length;
    const reviewed = interviews.filter((i) => i.teacher_review_status === "REVIEWED").length;
    return { all: interviews.length, pending, reviewed };
  }, [interviews]);

  const filteredEvals = useMemo(() => {
    let list = interviews;
    if (evalFilter === "pending") {
      list = list.filter((i) => i.teacher_review_status === "PENDING");
    } else if (evalFilter === "reviewed") {
      list = list.filter((i) => i.teacher_review_status === "REVIEWED");
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(
        (i) =>
          (i.student_name && i.student_name.toLowerCase().includes(q)) ||
          (i.template_title && i.template_title.toLowerCase().includes(q))
      );
    }

    return list;
  }, [interviews, evalFilter, searchTerm]);

  return (
    <TeacherWorkspace
      user={user}
      active="evaluations"
      pageTitle="Assessments & Reviews"
      pageSubtitle="Student Interview Submissions"
      searchPlaceholder="Search candidate or interview title..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="teacher-evaluations-page">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* Top Metric Bar */}
        <div className="practice-toolbar">
          <div className="filter-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={evalFilter === "all"}
              className={`filter-tab${evalFilter === "all" ? " active" : ""}`}
              onClick={() => setEvalFilter("all")}
            >
              All Submissions <span className="tab-count">{counts.all}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={evalFilter === "pending"}
              className={`filter-tab${evalFilter === "pending" ? " active" : ""}`}
              onClick={() => setEvalFilter("pending")}
            >
              Pending Review <span className="tab-count">{counts.pending}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={evalFilter === "reviewed"}
              className={`filter-tab${evalFilter === "reviewed" ? " active" : ""}`}
              onClick={() => setEvalFilter("reviewed")}
            >
              Reviewed <span className="tab-count">{counts.reviewed}</span>
            </button>
          </div>

          <div className="toolbar-status">
            <span>
              Showing {filteredEvals.length} of {interviews.length} completed session
              {interviews.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {/* Submissions List */}
        {busy ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Loading completed submissions…</span>
          </div>
        ) : filteredEvals.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <ClipboardCheck size={24} />
            </div>
            <h3>
              {searchTerm || evalFilter !== "all"
                ? "No matching interview submissions"
                : "No interview submissions to review yet"}
            </h3>
            <p>
              When students complete their assigned practice interviews, their responses and AI
              rubric evaluations will appear here for your review and scoring.
            </p>
          </div>
        ) : (
          <section className="overview-panel">
            <div className="history-table-wrapper">
              <table className="saas-table">
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Interview Title</th>
                    <th>Completed Date</th>
                    <th>Score</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvals.map((item) => {
                    const isReviewed = item.teacher_review_status === "REVIEWED";
                    const dateFormatted = item.ended_at
                      ? new Date(item.ended_at).toLocaleDateString([], {
                          dateStyle: "medium",
                        })
                      : "Recently";

                    return (
                      <tr key={item.interview_id}>
                        <td>
                          <div className="table-user-cell">
                            <span className="table-avatar">
                              {item.student_name?.[0]?.toUpperCase() || "S"}
                            </span>
                            <strong>{item.student_name || "Student"}</strong>
                          </div>
                        </td>
                        <td>
                          <strong>{item.template_title || "Mock Interview"}</strong>
                        </td>
                        <td>{dateFormatted}</td>
                        <td>
                          <span className="table-score-badge">
                            {item.final_score != null ? `${item.final_score}/10` : "Pending"}
                          </span>
                        </td>
                        <td>
                          {isReviewed ? (
                            <span className="status-pill status-completed">Reviewed</span>
                          ) : (
                            <span className="status-pill status-in_progress">Needs Review</span>
                          )}
                        </td>
                        <td>
                          <button
                            type="button"
                            className={`button button-small ${
                              isReviewed ? "button-outline" : "button-primary"
                            }`}
                            onClick={() => navigate(`/interviews/${item.interview_id}/report`)}
                          >
                            <FileBarChart2 size={13} />
                            <span>{isReviewed ? "View Report" : "Review & Score"}</span>
                            <ArrowRight size={12} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </TeacherWorkspace>
  );
}

