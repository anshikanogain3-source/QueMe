import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Award,
  BarChart3,
  CheckCircle2,
  Clock,
  Layers,
  MessageSquare,
  Mic,
  TrendingUp,
} from "lucide-react";
import { api } from "../api.js";
import { StudentWorkspace } from "./StudentWorkspace.jsx";

export function MyProgress({ user }) {
  const [progressData, setProgressData] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    api("/students/me/progress")
      .then((data) => {
        if (active) setProgressData(data);
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

  const history = progressData?.interviews || [];
  const completedCount = history.length;

  // Aggregate metrics
  const validOverall = history
    .map((h) => Number(h.overall_score))
    .filter(Number.isFinite);
  const avgOverall = validOverall.length
    ? (validOverall.reduce((sum, s) => sum + s, 0) / validOverall.length).toFixed(1)
    : "—";

  const validContent = history
    .map((h) => Number(h.content_score))
    .filter(Number.isFinite);
  const avgContent = validContent.length
    ? (validContent.reduce((sum, s) => sum + s, 0) / validContent.length).toFixed(1)
    : "—";

  const validDelivery = history
    .map((h) => Number(h.delivery_score))
    .filter(Number.isFinite);
  const avgDelivery = validDelivery.length
    ? (validDelivery.reduce((sum, s) => sum + s, 0) / validDelivery.length).toFixed(1)
    : "—";

  // Aggregate audio metrics from latest or across history
  const latestAudio = history[history.length - 1]?.audio_summary || {};
  const speakingRate = latestAudio.words_per_minute != null
    ? `${Number(latestAudio.words_per_minute).toFixed(0)} WPM`
    : "—";
  const pauseCount = latestAudio.pause_count != null
    ? Number(latestAudio.pause_count).toFixed(1)
    : "—";
  const pauseDuration = latestAudio.total_pause_duration_seconds != null
    ? `${Number(latestAudio.total_pause_duration_seconds).toFixed(1)}s`
    : "—";
  const fillers = latestAudio.fillers_per_100_words != null
    ? Number(latestAudio.fillers_per_100_words).toFixed(1)
    : "—";

  // Aggregate topic analysis
  const topicsMap = {};
  history.forEach((h) => {
    (h.topic_analysis || []).forEach((t) => {
      if (!topicsMap[t.topic]) {
        topicsMap[t.topic] = {
          topic: t.topic,
          scores: [],
          questionsTotal: 0,
          classification: t.classification,
        };
      }
      if (t.average_content_score != null) {
        topicsMap[t.topic].scores.push(Number(t.average_content_score));
      }
      topicsMap[t.topic].questionsTotal += t.questions_scored || 1;
    });
  });
  const topicsList = Object.values(topicsMap).map((t) => ({
    ...t,
    avg: t.scores.length
      ? (t.scores.reduce((a, b) => a + b, 0) / t.scores.length).toFixed(1)
      : null,
  }));

  return (
    <StudentWorkspace
      user={user}
      active="progress"
      pageTitle="My Progress"
      pageSubtitle="Performance & Analytics"
    >
      <div className="progress-page-container">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* 1. Top KPI Summary Grid (4 Cards) */}
        <section className="student-metrics-row" aria-label="Score benchmarks">
          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-blue">
              <Award size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Overall Average</span>
              <strong className="metric-value">{avgOverall}{avgOverall !== "—" ? "/10" : ""}</strong>
              <span className="metric-caption">Combined rubric score</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-indigo">
              <BarChart3 size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Content & Accuracy</span>
              <strong className="metric-value">{avgContent}{avgContent !== "—" ? "/10" : ""}</strong>
              <span className="metric-caption">Conceptual correctness</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-amber">
              <Mic size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Delivery & Pacing</span>
              <strong className="metric-value">{avgDelivery}{avgDelivery !== "—" ? "/10" : ""}</strong>
              <span className="metric-caption">Clarity and rhythm</span>
            </div>
          </article>

          <article className="student-metric-card">
            <div className="metric-icon-wrap icon-green">
              <CheckCircle2 size={18} aria-hidden="true" />
            </div>
            <div className="metric-data">
              <span className="metric-label">Completed Sessions</span>
              <strong className="metric-value">{completedCount}</strong>
              <span className="metric-caption">Full interviews assessed</span>
            </div>
          </article>
        </section>

        {busy ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Loading performance analytics…</span>
          </div>
        ) : completedCount === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <BarChart3 size={24} />
            </div>
            <h3>No Completed Practice Sessions Yet</h3>
            <p>
              Once you complete an assigned interview, your score progression, communication
              speed, pause metrics, and skill breakdowns will appear here.
            </p>
            <Link to="/practice-interviews" className="button button-primary button-small">
              <span>View Assigned Interviews</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        ) : (
          <>
            {/* 2. Score Progression Chart Card */}
            <section className="overview-panel score-chart-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">CHRONOLOGICAL TRAJECTORY</span>
                  <h2>Score Trend Over Time</h2>
                </div>
                <span className="count-pill">{completedCount} session{completedCount === 1 ? "" : "s"}</span>
              </div>
              <p className="panel-desc">
                Tracks overall score trajectory on a scale of 0 to 10 across your completed sessions.
              </p>

              {history.length > 1 ? (
                <div className="chart-wrapper">
                  <svg
                    className="saas-progress-chart"
                    viewBox="0 0 700 160"
                    role="img"
                    aria-label="Interview score history chart"
                  >
                    {/* Horizontal gridlines */}
                    <line x1="40" y1="20" x2="680" y2="20" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="40" y1="70" x2="680" y2="70" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="40" y1="120" x2="680" y2="120" stroke="#f1f5f9" strokeDasharray="3 3" />
                    <line x1="40" y1="135" x2="680" y2="135" stroke="#e2e8f0" strokeWidth="1.5" />

                    {/* Y-axis labels */}
                    <text x="12" y="24" fontSize="10" fill="#94a3b8">10</text>
                    <text x="16" y="74" fontSize="10" fill="#94a3b8">5</text>
                    <text x="16" y="124" fontSize="10" fill="#94a3b8">0</text>

                    {/* Connected score line & points */}
                    {history.map((item, index) => {
                      const total = history.length;
                      const x = total === 1 ? 360 : 60 + (index * 600) / (total - 1);
                      const rawScore = item.overall_score == null ? 0 : Number(item.overall_score);
                      const y = 135 - Math.max(0, Math.min(10, rawScore)) * 11;

                      const prev = history[index - 1];
                      let prevLine = null;
                      if (prev) {
                        const prevRaw = prev.overall_score == null ? 0 : Number(prev.overall_score);
                        const prevX = 60 + ((index - 1) * 600) / (total - 1);
                        const prevY = 135 - Math.max(0, Math.min(10, prevRaw)) * 11;
                        prevLine = (
                          <line
                            x1={prevX}
                            y1={prevY}
                            x2={x}
                            y2={y}
                            stroke="#2563eb"
                            strokeWidth="2.5"
                            strokeLinecap="round"
                          />
                        );
                      }

                      return (
                        <g key={item.interview_id}>
                          {prevLine}
                          <circle cx={x} cy={y} r="5" fill="#2563eb" stroke="#fff" strokeWidth="2" />
                          <text
                            x={x}
                            y={y - 9}
                            fontSize="10"
                            fontWeight="600"
                            fill="#1e293b"
                            textAnchor="middle"
                          >
                            {rawScore.toFixed(1)}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              ) : (
                <div className="single-session-note">
                  <p>
                    Completed 1 interview with overall score of <strong>{avgOverall}/10</strong>.
                    Complete additional interviews to visualize trend trajectories.
                  </p>
                </div>
              )}
            </section>

            {/* 3. Communication & Speech Analytics Grid */}
            <section className="overview-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">SPEECH & PACING</span>
                  <h2>Communication Delivery Metrics</h2>
                </div>
                <span className="card-score-badge">Based on latest answers</span>
              </div>
              <div className="speech-metrics-grid">
                <div className="speech-metric-box">
                  <span className="speech-metric-label">Speaking Rate</span>
                  <strong className="speech-metric-val">{speakingRate}</strong>
                  <span className="speech-metric-sub">Target: 130–160 WPM</span>
                </div>
                <div className="speech-metric-box">
                  <span className="speech-metric-label">Avg Pauses Per Answer</span>
                  <strong className="speech-metric-val">{pauseCount}</strong>
                  <span className="speech-metric-sub">Natural thinking pauses</span>
                </div>
                <div className="speech-metric-box">
                  <span className="speech-metric-label">Total Pause Time</span>
                  <strong className="speech-metric-val">{pauseDuration}</strong>
                  <span className="speech-metric-sub">Per recorded response</span>
                </div>
                <div className="speech-metric-box">
                  <span className="speech-metric-label">Filler Words</span>
                  <strong className="speech-metric-val">{fillers}</strong>
                  <span className="speech-metric-sub">Per 100 spoken words</span>
                </div>
              </div>
            </section>

            {/* 4. Topic Analysis & Skill Breakdown */}
            {topicsList.length > 0 && (
              <section className="overview-panel">
                <div className="panel-header">
                  <div>
                    <span className="eyebrow">DOMAIN COMPETENCIES</span>
                    <h2>Topic Performance Breakdown</h2>
                  </div>
                </div>
                <div className="topics-cards-grid">
                  {topicsList.map((t) => (
                    <div key={t.topic} className="topic-card">
                      <div className="topic-card-header">
                        <strong>{t.topic}</strong>
                        {t.avg && <span className="topic-score">{t.avg}/10</span>}
                      </div>
                      <div className="topic-card-bar">
                        <span
                          style={{
                            width: t.avg ? `${(Number(t.avg) / 10) * 100}%` : "0%",
                          }}
                        />
                      </div>
                      <small className="topic-card-meta">
                        {t.classification ? t.classification.replaceAll("_", " ") : "Evaluated"} · {t.questionsTotal} questions scored
                      </small>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 5. Complete Interview History Table */}
            <section className="overview-panel">
              <div className="panel-header">
                <div>
                  <span className="eyebrow">SESSION LOG</span>
                  <h2>Completed Interview History</h2>
                </div>
              </div>
              <div className="history-table-wrapper">
                <table className="saas-table">
                  <thead>
                    <tr>
                      <th>Interview Title</th>
                      <th>Date</th>
                      <th>Overall Score</th>
                      <th>Content</th>
                      <th>Delivery</th>
                      <th>Progress Comparison</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => {
                      const dateStr = item.interview_date
                        ? new Date(item.interview_date).toLocaleDateString([], {
                            dateStyle: "medium",
                          })
                        : "—";
                      const comparison =
                        item.comparison_to_previous?.reasons?.join(" ") || "—";

                      return (
                        <tr key={item.interview_id}>
                          <td>
                            <strong>{item.template_title || "Mock Interview"}</strong>
                          </td>
                          <td>{dateStr}</td>
                          <td>
                            <span className="table-score-badge">
                              {item.overall_score != null
                                ? `${Number(item.overall_score).toFixed(1)}/10`
                                : "—"}
                            </span>
                          </td>
                          <td>
                            {item.content_score != null
                              ? `${Number(item.content_score).toFixed(1)}/10`
                              : "—"}
                          </td>
                          <td>
                            {item.delivery_score != null
                              ? `${Number(item.delivery_score).toFixed(1)}/10`
                              : "—"}
                          </td>
                          <td className="table-comparison-col">
                            <span title={comparison}>{comparison}</span>
                          </td>
                          <td>
                            <Link
                              to={`/interviews/${item.interview_id}/report`}
                              className="button button-outline button-small"
                            >
                              <span>Report</span>
                              <ArrowRight size={12} />
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </StudentWorkspace>
  );
}

