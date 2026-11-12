import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  Award,
  CheckCircle2,
  ChevronDown,
  Download,
  ExternalLink,
  FileBarChart2,
  FileText,
  Lightbulb,
  Mic,
  Target,
  UserCheck,
} from "lucide-react";
import { api } from "../api.js";
import { AuthenticatedAudio } from "./AuthenticatedAudio.jsx";
import { StudentWorkspace } from "./StudentWorkspace.jsx";

export function StudentFeedback({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [report, setReport] = useState(null);
  const [busyList, setBusyList] = useState(true);
  const [busyReport, setBusyReport] = useState(false);
  const [error, setError] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Load completed interviews list
  useEffect(() => {
    let active = true;
    setBusyList(true);
    api("/interviews")
      .then((data) => {
        if (!active) return;
        const completed = (data || []).filter((i) => i.status === "COMPLETED");
        setInterviews(completed);

        // Pre-select from URL param or default to latest completed
        const paramId = searchParams.get("id");
        if (paramId && completed.some((c) => String(c.interview_id) === String(paramId))) {
          setSelectedId(Number(paramId));
        } else if (completed.length > 0) {
          setSelectedId(completed[0].interview_id);
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusyList(false);
      });

    return () => {
      active = false;
    };
  }, []);

  // Fetch report when selectedId changes
  useEffect(() => {
    if (!selectedId) {
      setReport(null);
      return;
    }

    let active = true;
    setBusyReport(true);
    api(`/interviews/${selectedId}/report`)
      .then((data) => {
        if (active) setReport(data);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusyReport(false);
      });

    return () => {
      active = false;
    };
  }, [selectedId]);

  function handleSelectSession(id) {
    setSelectedId(id);
    setSearchParams({ id: String(id) });
  }

  const questions = report?.questions || [];
  const improvementPlan = report?.improvement_plan || [];

  return (
    <StudentWorkspace
      user={user}
      active="feedback"
      pageTitle="Feedback"
      pageSubtitle="Evaluations & Recommendations"
    >
      <div className="feedback-page-container">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {busyList ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Loading feedback records…</span>
          </div>
        ) : interviews.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <FileBarChart2 size={24} />
            </div>
            <h3>No Feedback Available Yet</h3>
            <p>
              Feedback, rubric criteria evaluations, and customized improvement recommendations
              appear after you complete an assigned interview.
            </p>
            <Link to="/practice-interviews" className="button button-primary button-small">
              <span>Go to Practice Interviews</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        ) : (
          <>
            {/* Session Selector Header */}
            <div className="feedback-selector-bar">
              <div className="selector-copy">
                <span className="selector-label">Select Completed Session:</span>
                <select
                  value={selectedId || ""}
                  onChange={(e) => handleSelectSession(Number(e.target.value))}
                  className="session-select-dropdown"
                  aria-label="Select completed interview session"
                >
                  {interviews.map((item) => (
                    <option key={item.interview_id} value={item.interview_id}>
                      {item.template_title || "Mock Interview"} —{" "}
                      {item.scheduled_at
                        ? new Date(item.scheduled_at).toLocaleDateString([], {
                            month: "short",
                            day: "numeric",
                          })
                        : "Completed"}{" "}
                      {item.final_score != null ? `(Score: ${item.final_score}/10)` : ""}
                    </option>
                  ))}
                </select>
              </div>

              {selectedId && (
                <div className="selector-actions">
                  <Link
                    to={`/interviews/${selectedId}/report`}
                    className="button button-outline button-small"
                  >
                    <span>Full Detailed Report</span>
                    <ExternalLink size={13} />
                  </Link>
                </div>
              )}
            </div>

            {busyReport ? (
              <div className="loading-container">
                <span className="spinner" />
                <span>Loading session assessment report…</span>
              </div>
            ) : report ? (
              <div className="feedback-content-stack">
                {/* 1. Overall Session Performance Card */}
                <section className="overview-panel feedback-summary-panel">
                  <div className="panel-header">
                    <div>
                      <span className="eyebrow">SESSION SUMMARY</span>
                      <h2>{report.template_title || "Interview Evaluation"}</h2>
                    </div>
                    <span className="card-score-badge large-badge">
                      Overall Score:{" "}
                      <strong>
                        {report.final_score != null
                          ? `${Number(report.final_score).toFixed(1)}/10`
                          : "Pending"}
                      </strong>
                    </span>
                  </div>

                  <div className="feedback-score-row">
                    <div className="score-box">
                      <span className="score-box-label">AI Evaluated Score</span>
                      <strong className="score-box-val">
                        {report.ai_final_score != null
                          ? `${Number(report.ai_final_score).toFixed(1)}/10`
                          : "—"}
                      </strong>
                      <span className="score-box-sub">Rubric + delivery analysis</span>
                    </div>

                    <div className="score-box">
                      <span className="score-box-label">Instructor Score</span>
                      <strong className="score-box-val">
                        {report.teacher_score != null
                          ? `${Number(report.teacher_score).toFixed(1)}/10`
                          : "Pending Review"}
                      </strong>
                      <span className="score-box-sub">
                        {report.teacher_name ? `By ${report.teacher_name}` : "Faculty assessment"}
                      </span>
                    </div>

                    <div className="score-box">
                      <span className="score-box-label">Questions Evaluated</span>
                      <strong className="score-box-val">{questions.length}</strong>
                      <span className="score-box-sub">Recorded & scored prompts</span>
                    </div>
                  </div>

                  {report.teacher_remark && (
                    <div className="instructor-remark-box">
                      <div className="remark-header">
                        <UserCheck size={16} className="remark-icon" />
                        <strong>Instructor Feedback Note</strong>
                      </div>
                      <p>{report.teacher_remark}</p>
                    </div>
                  )}
                </section>

                {/* 2. Personalized Practice & Improvement Plan */}
                <section className="overview-panel">
                  <div className="panel-header">
                    <div>
                      <span className="eyebrow">ACTIONABLE NEXT STEPS</span>
                      <h2>Personalized Improvement Recommendations</h2>
                    </div>
                    <span className="count-pill">
                      {improvementPlan.length} recommendation{improvementPlan.length === 1 ? "" : "s"}
                    </span>
                  </div>

                  {improvementPlan.length > 0 ? (
                    <div className="recommendations-grid">
                      {improvementPlan.map((item, index) => (
                        <div key={`${item.area}-${index}`} className="recommendation-card">
                          <div className="recommendation-top">
                            <span className="recommendation-area">
                              <Target size={14} />
                              {item.area}
                            </span>
                            {item.question_order && (
                              <small className="recommendation-q">
                                Question {item.question_order}
                              </small>
                            )}
                          </div>

                          <h3 className="recommendation-title">{item.interpretation}</h3>

                          {item.evidence && (
                            <blockquote className="recommendation-evidence">
                              “{item.evidence}”
                            </blockquote>
                          )}

                          <div className="recommendation-activity">
                            <Lightbulb size={15} className="activity-icon" />
                            <p><strong>Practice Activity:</strong> {item.practice_activity}</p>
                          </div>

                          <div className="recommendation-meta">
                            <span><strong>Target:</strong> {item.measurable_target}</span>
                            <span><strong>Timeframe:</strong> {item.review_timeframe}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="panel-empty-note">
                      <p>
                        No critical weaknesses identified for this session. Keep up the consistent
                        practice!
                      </p>
                    </div>
                  )}
                </section>

                {/* 3. Question-by-Question Assessment */}
                <section className="overview-panel">
                  <div className="panel-header">
                    <div>
                      <span className="eyebrow">QUESTION ASSESSMENTS</span>
                      <h2>Individual Question Breakdown</h2>
                    </div>
                  </div>

                  <div className="questions-feedback-list">
                    {questions.map((q) => {
                      const finalQScore =
                        q.teacher_score != null
                          ? q.teacher_score
                          : q.final_ai_score != null
                          ? q.final_ai_score
                          : q.final_score;

                      return (
                        <article key={q.interview_question_id} className="question-feedback-item">
                          <div className="q-feedback-header">
                            <span className="q-order-badge">Question {q.question_order}</span>
                            <div className="q-tags">
                              {q.topics && q.topics.length > 0 && (
                                <span className="status-pill status-in_progress">
                                  {q.topics.join(", ")}
                                </span>
                              )}
                              <span className="status-pill status-scheduled">
                                Score:{" "}
                                <strong>
                                  {finalQScore != null ? `${Number(finalQScore).toFixed(1)}/10` : "—"}
                                </strong>
                              </span>
                            </div>
                          </div>

                          <h3 className="q-text">{q.question_text}</h3>

                          {/* Audio Player if recorded */}
                          {q.audio_url && (
                            <div className="q-audio-wrap">
                              <span className="q-audio-label">
                                <Mic size={13} />
                                Recorded Audio:
                              </span>
                              <AuthenticatedAudio path={q.audio_url} />
                            </div>
                          )}

                          {/* Transcript */}
                          {q.transcript && (
                            <div className="q-transcript-box">
                              <span className="transcript-label">Transcribed Response:</span>
                              <p>“{q.transcript}”</p>
                            </div>
                          )}

                          {/* Evaluation Criteria Details */}
                          {q.evaluation?.criteria_scores && (
                            <div className="criteria-scores-list">
                              <span className="criteria-label">Rubric Criteria Scores:</span>
                              <div className="criteria-chips">
                                {Object.entries(q.evaluation.criteria_scores).map(
                                  ([name, scoreVal]) => (
                                    <span key={name} className="criterion-chip">
                                      {name.replaceAll("_", " ")}: <strong>{scoreVal}</strong>
                                    </span>
                                  )
                                )}
                              </div>
                            </div>
                          )}

                          {/* Teacher Remarks on specific question */}
                          {q.teacher_remark && (
                            <div className="q-teacher-remark">
                              <strong>Instructor Remark:</strong>
                              <p>{q.teacher_remark}</p>
                            </div>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </section>
              </div>
            ) : null}
          </>
        )}
      </div>
    </StudentWorkspace>
  );
}

