import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  BarChart2,
  Download,
  FileCheck2,
  FileSpreadsheet,
  GraduationCap,
  Layers,
  Scale,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { api } from "../api.js";
import { useFeedback } from "../feedback.jsx";
import { AdminWorkspace } from "./AdminWorkspace.jsx";

export function AdminAnalytics({ user }) {
  const { notify } = useFeedback();
  const [analytics, setAnalytics] = useState(null);
  const [validationData, setValidationData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exportingValidation, setExportingValidation] = useState(false);

  function flash(msg) {
    notify(msg, "success");
  }

  function fail(err) {
    setError(err?.message || "Operation failed.");
    window.setTimeout(() => setError(""), 5000);
  }

  async function loadData() {
    try {
      setLoading(true);
      const [stats, valData] = await Promise.all([
        api("/admin/analytics").catch(() => null),
        api("/admin/validation").catch(() => []),
      ]);
      setAnalytics(stats);
      setValidationData(Array.isArray(valData) ? valData : []);
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleExportValidation() {
    try {
      setExportingValidation(true);
      const blob = await api("/admin/validation.xlsx");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `queme-rubric-validation-dataset-${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      flash("Exported rubric evaluation dataset (.xlsx).");
    } catch (err) {
      fail(err);
    } finally {
      setExportingValidation(false);
    }
  }

  return (
    <AdminWorkspace
      user={user}
      active="analytics"
      pageTitle="Platform & Evaluation Analytics"
      pageSubtitle="Institutional score metrics, AI-teacher agreement validation dataset, and candidate readiness."
      actions={
        <button
          type="button"
          className="admin-primary-btn"
          onClick={handleExportValidation}
          disabled={exportingValidation}
        >
          <Download size={15} />
          <span>{exportingValidation ? "Exporting..." : "Export Validation Dataset (.xlsx)"}</span>
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

        {/* 4 Metric Cards */}
        <div className="admin-kpi-grid">
          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap primary">
              <TrendingUp size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Campus Average Score</span>
              <strong className="kpi-value">
                {analytics?.average_score != null ? `${Number(analytics.average_score).toFixed(1)}/10` : "—"}
              </strong>
              <small className="kpi-sub">Across completed interviews</small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap success">
              <FileCheck2 size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Completed Sessions</span>
              <strong className="kpi-value">{analytics?.completed_interviews ?? 0}</strong>
              <small className="kpi-sub">
                Out of {analytics?.interview_count ?? 0} total scheduled
              </small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap info">
              <Users size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Campus Cohort Size</span>
              <strong className="kpi-value">
                {(analytics?.active_students ?? 0) + (analytics?.active_teachers ?? 0)}
              </strong>
              <small className="kpi-sub">
                {analytics?.active_students ?? 0} students &middot; {analytics?.active_teachers ?? 0}{" "}
                faculty
              </small>
            </div>
          </div>

          <div className="admin-kpi-card">
            <div className="kpi-icon-wrap warning">
              <Scale size={20} />
            </div>
            <div className="kpi-body">
              <span className="kpi-label">Scored Answers</span>
              <strong className="kpi-value">{validationData.length}</strong>
              <small className="kpi-sub">Validation dataset entries</small>
            </div>
          </div>
        </div>

        {/* 2-Column Analytical Insight Cards */}
        <div className="admin-overview-grid">
          {/* Rubric Evaluation Dataset Summary */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Rubric Validation Dataset</h3>
                <p>
                  Exportable dataset tracking AI automated scores against faculty overrides for institutional accreditation and research.
                </p>
              </div>
            </div>

            <div className="validation-dataset-summary">
              <div className="validation-feature-list">
                <div className="validation-feature-item">
                  <span className="feature-bullet" />
                  <div>
                    <strong>Dual-Scoring Auditability</strong>
                    <p>Captures AI content/delivery sub-scores and instructor modified grades.</p>
                  </div>
                </div>
                <div className="validation-feature-item">
                  <span className="feature-bullet" />
                  <div>
                    <strong>Question-Level Granularity</strong>
                    <p>Includes question text, difficulty, rubric criteria weights, and candidate responses.</p>
                  </div>
                </div>
                <div className="validation-feature-item">
                  <span className="feature-bullet" />
                  <div>
                    <strong>Accreditation Compliance</strong>
                    <p>Ready for export into statistical software (SPSS, R, Excel) for AI reliability studies.</p>
                  </div>
                </div>
              </div>

              <div className="validation-action-box">
                <button
                  type="button"
                  className="admin-primary-btn"
                  onClick={handleExportValidation}
                  disabled={exportingValidation}
                >
                  <FileSpreadsheet size={15} />
                  <span>Download Validation Dataset (.xlsx)</span>
                </button>
              </div>
            </div>
          </div>

          {/* Platform Health & Quality Metrics */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Evaluation Quality Assurance</h3>
                <p>Status of scoring pipeline and faculty review velocity.</p>
              </div>
            </div>

            <div className="admin-qa-metrics">
              <div className="qa-metric-row">
                <span className="qa-label">Faculty Verification Queue</span>
                <strong className="qa-value warning">
                  {analytics?.reports_needing_review ?? 0} Pending
                </strong>
              </div>
              <div className="qa-metric-row">
                <span className="qa-label">Account Verification Queue</span>
                <strong className="qa-value info">
                  {analytics?.pending_accounts ?? 0} Awaiting Action
                </strong>
              </div>
              <div className="qa-metric-row">
                <span className="qa-label">Completion Velocity</span>
                <strong className="qa-value success">
                  {analytics?.interview_count
                    ? `${Math.round(((analytics?.completed_interviews ?? 0) / analytics.interview_count) * 100)}%`
                    : "0%"}
                </strong>
              </div>
            </div>

            <div className="admin-qa-guidance">
              <p>
                <strong>Tip:</strong> Encourage faculty to review pending evaluations so students receive finalized reports and comprehensive interview insights prior to campus placement drives.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AdminWorkspace>
  );
}

