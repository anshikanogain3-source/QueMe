import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Clock3,
  FileBarChart2,
  FilePlus2,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "../api.js";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

export function TeacherOverview({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    Promise.all([api("/interviews"), api("/teacher/analytics")])
      .then(([interviewRows, stats]) => {
        if (!active) return;
        setInterviews(interviewRows || []);
        setAnalytics(stats);
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

  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "Instructor";
  const recentInterviews = interviews.slice(0, 4);

  return (
    <TeacherWorkspace
      user={user}
      active="overview"
      pageTitle="Teacher Dashboard"
      pageSubtitle="Campus Assessment Overview"
    >
      <div className="teacher-overview-container">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* 1. Welcome Section */}
        <section className="student-overview-hero" aria-label="Welcome banner">
          <div className="overview-hero-content">
            <span className="eyebrow eyebrow-blue">FACULTY & PLACEMENT PORTAL</span>
            <h1>Welcome, {firstName}.</h1>
            <p className="overview-hero-text">
              Assign guided practice interviews, assess student responses against objective rubrics,
              and monitor interview readiness across your cohorts.
            </p>
            <div className="overview-hero-actions">
              <Link className="button button-primary" to="/teacher/interviews">
                <FilePlus2 size={15} aria-hidden="true" />
                <span>Assign New Interview</span>
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
              <Link className="button button-outline" to="/teacher/evaluations">
                <ClipboardCheck size={15} aria-hidden="true" />
                <span>Review Submissions ({analytics?.pending_reviews ?? 0})</span>
              </Link>
            </div>
          </div>
          <div className="overview-hero-badge">
            <div className="hero-badge-inner">
              <Sparkles size={24} className="hero-badge-icon" aria-hidden="true" />
              <strong>Campus Faculty</strong>
              <small>Interview Assessment</small>
            </div>
          </div>
        </section>

        {/* 2. Compact Statistics Cards */}
        <section className="student-metrics-row" aria-label="Essential statistics">
          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-blue">
              <Users size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Assigned Students</span>
              <strong className="metric-value">
                {analytics?.students_assigned ?? "—"}
              </strong>
              <span className="metric-caption">Active students enrolled</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-indigo">
              <BriefcaseBusiness size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Interviews Assigned</span>
              <strong className="metric-value">
                {analytics?.interview_count ?? "—"}
              </strong>
              <span className="metric-caption">
                {analytics?.active_interviews ?? 0} active / scheduled
              </span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-green">
              <CheckCircle2 size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Completed Sessions</span>
              <strong className="metric-value">
                {analytics?.completed_interviews ?? "—"}
              </strong>
              <span className="metric-caption">
                Avg score: {analytics?.average_score != null ? `${analytics.average_score}/10` : "—"}
              </span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-amber">
              <ClipboardCheck size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Pending Reviews</span>
              <strong className="metric-value">
                {analytics?.pending_reviews ?? 0}
              </strong>
              <span className="metric-caption">Requires faculty review</span>
            </div>
          </article>
        </section>

        {/* 3. Dashboard Split Layout: Recent Activity vs Quick Access */}
        <div className="student-overview-grid">
          {/* Left Column: Recent Student Activity */}
          <div className="overview-column-main">
            <article className="overview-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">MONITORING</span>
                  <h2>Recent Student Activity</h2>
                </div>
                <Link to="/teacher/interviews" className="panel-header-link">
                  View all sessions <ArrowRight size={13} />
                </Link>
              </div>

              {busy ? (
                <div className="loading-container">
                  <span className="spinner" />
                  <span>Loading recent sessions…</span>
                </div>
              ) : recentInterviews.length > 0 ? (
                <div className="recent-activity-list">
                  {recentInterviews.map((item) => {
                    const isDone = item.status === "COMPLETED";
                    const isRunning = item.status === "IN_PROGRESS";
                    const dateFormatted = item.scheduled_at
                      ? new Date(item.scheduled_at).toLocaleDateString([], {
                          month: "short",
                          day: "numeric",
                        })
                      : "Recently";

                    return (
                      <div key={item.interview_id} className="recent-activity-item">
                        <div
                          className={`activity-status-icon ${
                            isDone ? "is-done" : isRunning ? "is-running" : "is-pending"
                          }`}
                        >
                          {isDone ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}
                        </div>
                        <div className="activity-info">
                          <strong>{item.student_name || "Student"}</strong>
                          <span>
                            {item.template_title || "Mock Interview"} · {dateFormatted}
                          </span>
                        </div>
                        <div className="activity-action">
                          {isDone ? (
                            <button
                              type="button"
                              className="button button-outline button-small"
                              onClick={() => navigate(`/interviews/${item.interview_id}/report`)}
                            >
                              <span>{item.final_score != null ? `Score ${item.final_score}` : "Review"}</span>
                              <ArrowRight size={12} />
                            </button>
                          ) : (
                            <span className={`status-pill status-${item.status.toLowerCase()}`}>
                              {item.status.replaceAll("_", " ")}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="overview-empty-state">
                  <p>No student interviews assigned yet. Create an interview template to get started.</p>
                </div>
              )}
            </article>
          </div>

          {/* Right Column: Quick Access Modules & Faculty Tip */}
          <aside className="overview-column-side">
            <div className="overview-panel quick-access-panel">
              <span className="eyebrow">NAVIGATION</span>
              <h2>Quick Management</h2>
              <div className="quick-access-grid">
                <Link to="/teacher/students" className="quick-card">
                  <div className="quick-card-icon">
                    <Users size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>My Students</strong>
                    <span>Browse enrolled cohorts & student records</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/teacher/interviews" className="quick-card">
                  <div className="quick-card-icon">
                    <BriefcaseBusiness size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>Interview Management</strong>
                    <span>Create templates & assign practice rounds</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/teacher/evaluations" className="quick-card">
                  <div className="quick-card-icon">
                    <ClipboardCheck size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>Assessments & Reviews</strong>
                    <span>Score student answers & provide faculty remarks</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/teacher/question-bank" className="quick-card">
                  <div className="quick-card-icon">
                    <BookOpen size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>Question Bank</strong>
                    <span>Author questions & generate AI practice sets</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>
              </div>
            </div>

            {/* Assessment Tip Card */}
            <div className="overview-tip-card">
              <div className="tip-header">
                <Sparkles size={16} className="tip-icon" />
                <strong>Rubric Tip</strong>
              </div>
              <p>
                Pair technical questions with specific rubric criteria to generate consistent, automated AI evaluations for students before your final review.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </TeacherWorkspace>
  );
}

