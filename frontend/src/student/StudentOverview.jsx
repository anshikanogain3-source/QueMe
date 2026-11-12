import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Award,
  BarChart3,
  BriefcaseBusiness,
  CheckCircle2,
  Clock3,
  FileBarChart2,
  Sparkles,
  Zap,
} from "lucide-react";
import { api } from "../api.js";
import { StudentWorkspace } from "./StudentWorkspace.jsx";

export function StudentOverview({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [questions, setQuestions] = useState(null);
  const [progress, setProgress] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    Promise.all([
      api("/interviews"),
      api("/rapidfire/questions"),
      api("/students/me/progress"),
    ])
      .then(([interviewRows, rapidfireRows, progressData]) => {
        if (!active) return;
        setInterviews(interviewRows || []);
        setQuestions(rapidfireRows || []);
        setProgress(progressData);
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

  const completed = interviews.filter((row) => row.status === "COMPLETED");
  const upcoming = interviews.filter(
    (row) => row.status === "SCHEDULED" || row.status === "IN_PROGRESS"
  );
  const scores = completed
    .map((row) => Number(row.final_score))
    .filter(Number.isFinite);
  const average = scores.length
    ? `${(scores.reduce((sum, s) => sum + s, 0) / scores.length).toFixed(1)}/10`
    : "—";

  const next =
    upcoming.find((row) => row.status === "IN_PROGRESS") || upcoming[0];
  const firstName = user?.full_name ? user.full_name.split(" ")[0] : "Student";

  // Recent 3 activities: combination of completed and upcoming
  const recentActivities = interviews.slice(0, 3);

  return (
    <StudentWorkspace
      user={user}
      active="dashboard"
      pageTitle="Dashboard"
      pageSubtitle="Student Overview"
    >
      <div className="student-overview-container">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* 1. Welcome Hero Section */}
        <section className="student-overview-hero" aria-label="Welcome banner">
          <div className="overview-hero-content">
            <span className="eyebrow eyebrow-blue">CAMPUS INTERVIEW PREPARATION</span>
            <h1>Good to see you, {firstName}.</h1>
            <p className="overview-hero-text">
              Every interview is a chance to make your next answer clearer, more structured, and more confident.
            </p>
            <div className="overview-hero-actions">
              {next ? (
                <Link
                  className="button button-primary"
                  to={`/interviews/${next.interview_id}`}
                >
                  <span>
                    {next.status === "IN_PROGRESS" ? "Continue Interview" : "Start Next Interview"}
                  </span>
                  <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ) : (
                <Link className="button button-primary" to="/practice-interviews">
                  <span>Explore Practice Interviews</span>
                  <ArrowRight size={15} aria-hidden="true" />
                </Link>
              )}
              <Link className="button button-outline" to="/rapidfire">
                <Zap size={14} aria-hidden="true" />
                <span>Practice RapidFire</span>
              </Link>
            </div>
          </div>
          <div className="overview-hero-badge">
            <div className="hero-badge-inner">
              <Sparkles size={24} className="hero-badge-icon" aria-hidden="true" />
              <strong>Placement Ready</strong>
              <small>Campus Training Program</small>
            </div>
          </div>
        </section>

        {/* 2. Compact Statistics Section (4 cards) */}
        <section className="student-metrics-row" aria-label="Essential statistics">
          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-blue">
              <Clock3 size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Available Interviews</span>
              <strong className="metric-value">{upcoming.length}</strong>
              <span className="metric-caption">Ready to practice</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-green">
              <CheckCircle2 size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Completed Interviews</span>
              <strong className="metric-value">{completed.length}</strong>
              <span className="metric-caption">Finished sessions</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-indigo">
              <Award size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Average Score</span>
              <strong className="metric-value">{average}</strong>
              <span className="metric-caption">
                {scores.length ? `Across ${scores.length} scored sessions` : "No scores yet"}
              </span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-amber">
              <Activity size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">RapidFire Practice</span>
              <strong className="metric-value">
                {questions ? `${questions.length}` : "—"}
              </strong>
              <span className="metric-caption">Questions available</span>
            </div>
          </article>
        </section>

        {/* 3. Dashboard Split Layout: Recent Activity vs Quick Access */}
        <div className="student-overview-grid">
          {/* Left Column: Recent Activity & Next Interview */}
          <div className="overview-column-main">
            {/* Next Interview Highlight Card */}
            <article className="overview-panel next-interview-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">UPCOMING FOCUS</span>
                  <h2>{next ? next.template_title || "Assigned Practice" : "Interview Practice"}</h2>
                </div>
                {next && (
                  <span
                    className={`status-pill status-${next.status.toLowerCase()}`}
                  >
                    {next.status === "IN_PROGRESS" ? "In Progress" : "Scheduled"}
                  </span>
                )}
              </div>
              <p className="panel-desc">
                {next
                  ? `Assigned by ${next.teacher_name || "your instructor"} · Scheduled session ready for practice.`
                  : "You have no pending assigned interviews. Take a quick RapidFire practice round to stay sharp."}
              </p>
              <div className="panel-footer">
                {next ? (
                  <button
                    type="button"
                    className="button button-primary button-small"
                    onClick={() => navigate(`/interviews/${next.interview_id}`)}
                  >
                    <span>{next.status === "IN_PROGRESS" ? "Continue Practice" : "Start Interview"}</span>
                    <ArrowRight size={14} />
                  </button>
                ) : (
                  <Link to="/rapidfire" className="button button-outline button-small">
                    <span>Try RapidFire</span>
                    <ArrowRight size={14} />
                  </Link>
                )}
              </div>
            </article>

            {/* Recent Activity List */}
            <article className="overview-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">TRACK RECORD</span>
                  <h2>Recent Activity</h2>
                </div>
                <Link to="/practice-interviews" className="panel-header-link">
                  View all interviews <ArrowRight size={13} />
                </Link>
              </div>

              {recentActivities.length > 0 ? (
                <div className="recent-activity-list">
                  {recentActivities.map((row) => {
                    const isDone = row.status === "COMPLETED";
                    const isRunning = row.status === "IN_PROGRESS";
                    const dateFormatted = row.scheduled_at
                      ? new Date(row.scheduled_at).toLocaleDateString([], {
                          month: "short",
                          day: "numeric",
                        })
                      : "Recently";

                    return (
                      <div key={row.interview_id} className="recent-activity-item">
                        <div
                          className={`activity-status-icon ${
                            isDone ? "is-done" : isRunning ? "is-running" : "is-pending"
                          }`}
                        >
                          {isDone ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}
                        </div>
                        <div className="activity-info">
                          <strong>{row.template_title || "Practice Interview"}</strong>
                          <span>
                            {row.teacher_name ? `Assigned by ${row.teacher_name} · ` : ""}
                            {dateFormatted}
                          </span>
                        </div>
                        <div className="activity-action">
                          {isDone ? (
                            <Link
                              to={`/interviews/${row.interview_id}/report`}
                              className="button button-outline button-small"
                            >
                              <span>
                                {row.final_score != null ? `${row.final_score}/10` : "Report"}
                              </span>
                              <ArrowRight size={12} />
                            </Link>
                          ) : (
                            <Link
                              to={`/interviews/${row.interview_id}`}
                              className="button button-primary button-small"
                            >
                              <span>{isRunning ? "Continue" : "Start"}</span>
                              <ArrowRight size={12} />
                            </Link>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="overview-empty-state">
                  <p>No recent activity yet. When you begin practice, your progress will show up here.</p>
                </div>
              )}
            </article>
          </div>

          {/* Right Column: Quick Access Modules & Placement Tip */}
          <aside className="overview-column-side">
            <div className="overview-panel quick-access-panel">
              <span className="eyebrow">NAVIGATION</span>
              <h2>Quick Access</h2>
              <div className="quick-access-grid">
                <Link to="/practice-interviews" className="quick-card">
                  <div className="quick-card-icon">
                    <BriefcaseBusiness size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>Practice Interviews</strong>
                    <span>Browse assigned sessions & start rounds</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/rapidfire" className="quick-card">
                  <div className="quick-card-icon">
                    <Activity size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>RapidFire Practice</strong>
                    <span>Quick questions for spontaneous articulation</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/my-progress" className="quick-card">
                  <div className="quick-card-icon">
                    <BarChart3 size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>My Progress</strong>
                    <span>Score trends, speech rates & skill breakdown</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>

                <Link to="/feedback" className="quick-card">
                  <div className="quick-card-icon">
                    <FileBarChart2 size={18} />
                  </div>
                  <div className="quick-card-text">
                    <strong>Feedback & Reports</strong>
                    <span>Personalized plans and question evaluations</span>
                  </div>
                  <ArrowRight size={14} className="quick-card-arrow" />
                </Link>
              </div>
            </div>

            {/* Preparation Tip Card */}
            <div className="overview-tip-card">
              <div className="tip-header">
                <Sparkles size={16} className="tip-icon" />
                <strong>Interview Tip</strong>
              </div>
              <p>
                Structure behavioral questions with the <strong>STAR method</strong> (Situation, Task, Action, Result) to give clear, memorable responses.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </StudentWorkspace>
  );
}

