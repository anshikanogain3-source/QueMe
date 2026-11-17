import { useEffect, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Calendar,
  GraduationCap,
  Layers,
  Plus,
  Scale,
  Settings2,
  Sliders,
} from "lucide-react";
import { api } from "../api.js";
import { useFeedback } from "../feedback.jsx";
import { AdminWorkspace } from "./AdminWorkspace.jsx";

const SEMESTERS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];

export function AdminSettings({ user }) {
  const { notify } = useFeedback();
  const [weights, setWeights] = useState({ content_weight: 0.7, delivery_weight: 0.3 });
  const [courses, setCourses] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [cohortForm, setCohortForm] = useState({ course_id: "", semester: "", academic_year: "" });

  const [savingWeights, setSavingWeights] = useState(false);
  const [creatingCohort, setCreatingCohort] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
      const [scoreWeights, courseRows, cohortRows] = await Promise.all([
        api("/admin/settings").catch(() => ({ content_weight: 0.7, delivery_weight: 0.3 })),
        api("/admin/courses").catch(() => []),
        api("/admin/semesters").catch(() => []),
      ]);
      setWeights(scoreWeights);
      setCourses(Array.isArray(courseRows) ? courseRows : []);
      setCohorts(Array.isArray(cohortRows) ? cohortRows : []);
      if (courseRows.length > 0) {
        setCohortForm((prev) => ({
          ...prev,
          course_id: prev.course_id || String(courseRows[0].course_id),
        }));
      }
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleSaveWeights(e) {
    e.preventDefault();
    setSavingWeights(true);
    setError("");

    const cw = Number(weights.content_weight);
    const dw = Number(weights.delivery_weight);

    if (Math.abs(cw + dw - 1.0) > 0.001) {
      setError("Content weight and delivery weight must sum exactly to 1.00 (100%).");
      setSavingWeights(false);
      return;
    }

    try {
      const updated = await api("/admin/settings", {
        method: "PATCH",
        body: JSON.stringify({ content_weight: cw, delivery_weight: dw }),
      });
      setWeights(updated);
      flash("Institutional scoring weights saved successfully.");
    } catch (err) {
      fail(err);
    } finally {
      setSavingWeights(false);
    }
  }

  async function handleCreateCohort(e) {
    e.preventDefault();
    if (!cohortForm.course_id || !cohortForm.semester || !cohortForm.academic_year.trim()) {
      setError("Please complete all cohort fields.");
      return;
    }

    setCreatingCohort(true);
    setError("");

    try {
      await api("/admin/semesters", {
        method: "POST",
        body: JSON.stringify({
          course_id: Number(cohortForm.course_id),
          semester: cohortForm.semester,
          academic_year: cohortForm.academic_year.trim(),
        }),
      });
      flash("Class group (cohort) created successfully. Students can now enroll into it.");
      setCohortForm((prev) => ({ ...prev, semester: "", academic_year: "" }));
      const rows = await api("/admin/semesters");
      setCohorts(Array.isArray(rows) ? rows : []);
    } catch (err) {
      fail(err);
    } finally {
      setCreatingCohort(false);
    }
  }

  return (
    <AdminWorkspace
      user={user}
      active="settings"
      pageTitle="System Settings & Class Cohorts"
      pageSubtitle="Configure campus-wide scoring algorithms, content vs delivery weight distribution, and manage academic cohorts."
    >
      <div className="admin-section">
        {error && (
          <div className="qm-alert qm-alert-error" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="admin-settings-layout">
          {/* Section 1: Scoring Weights Form */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Institutional Scoring Weights</h3>
                <p>Define the relative weight of technical/conceptual accuracy versus speech and delivery quality.</p>
              </div>
            </div>

            <form onSubmit={handleSaveWeights} className="admin-form">
              <div className="form-grid-2">
                <div className="form-group">
                  <label htmlFor="content_weight">
                    Content &amp; Technical Accuracy Weight (0.00 – 1.00)
                  </label>
                  <input
                    id="content_weight"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    required
                    value={weights.content_weight}
                    onChange={(e) => {
                      const cw = parseFloat(e.target.value) || 0;
                      const dw = Math.max(0, parseFloat((1.0 - cw).toFixed(2)));
                      setWeights({ content_weight: e.target.value, delivery_weight: dw });
                    }}
                  />
                  <span className="field-hint">
                    Current: <strong>{Math.round(Number(weights.content_weight) * 100)}%</strong>
                  </span>
                </div>

                <div className="form-group">
                  <label htmlFor="delivery_weight">
                    Speech &amp; Delivery Quality Weight (0.00 – 1.00)
                  </label>
                  <input
                    id="delivery_weight"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    required
                    value={weights.delivery_weight}
                    onChange={(e) => {
                      const dw = parseFloat(e.target.value) || 0;
                      const cw = Math.max(0, parseFloat((1.0 - dw).toFixed(2)));
                      setWeights({ delivery_weight: e.target.value, content_weight: cw });
                    }}
                  />
                  <span className="field-hint">
                    Current: <strong>{Math.round(Number(weights.delivery_weight) * 100)}%</strong>
                  </span>
                </div>
              </div>

              <div className="weight-preview-bar">
                <div
                  className="weight-bar-segment content-seg"
                  style={{ width: `${Math.round(Number(weights.content_weight) * 100)}%` }}
                >
                  Content ({Math.round(Number(weights.content_weight) * 100)}%)
                </div>
                <div
                  className="weight-bar-segment delivery-seg"
                  style={{ width: `${Math.round(Number(weights.delivery_weight) * 100)}%` }}
                >
                  Delivery ({Math.round(Number(weights.delivery_weight) * 100)}%)
                </div>
              </div>

              <div className="form-footer">
                <span className="field-note">
                  Both weights must sum to exactly 1.00 (100%).
                </span>
                <button
                  type="submit"
                  className="admin-primary-btn"
                  disabled={savingWeights}
                >
                  {savingWeights ? "Saving..." : "Save Scoring Weights"}
                </button>
              </div>
            </form>
          </div>

          {/* Section 2: Create Class Group / Cohort Form */}
          <div className="admin-card">
            <div className="admin-card-head">
              <div>
                <h3>Add New Class Cohort</h3>
                <p>Register academic batches so students and faculty can enroll into organized groups.</p>
              </div>
            </div>

            <form onSubmit={handleCreateCohort} className="admin-form">
              <div className="form-grid-3">
                <div className="form-group">
                  <label htmlFor="course_id">Course / Degree Program *</label>
                  <select
                    id="course_id"
                    required
                    value={cohortForm.course_id}
                    onChange={(e) =>
                      setCohortForm((prev) => ({ ...prev, course_id: e.target.value }))
                    }
                  >
                    {courses.map((c) => (
                      <option key={c.course_id} value={c.course_id}>
                        {c.course_name} ({c.code})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="semester">Semester *</label>
                  <select
                    id="semester"
                    required
                    value={cohortForm.semester}
                    onChange={(e) =>
                      setCohortForm((prev) => ({ ...prev, semester: e.target.value }))
                    }
                  >
                    <option value="">Select Semester</option>
                    {SEMESTERS.map((s) => (
                      <option key={s} value={s}>
                        {s} Semester
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="academic_year">Academic Year *</label>
                  <input
                    id="academic_year"
                    type="text"
                    required
                    placeholder="e.g., 2026–27"
                    maxLength={20}
                    value={cohortForm.academic_year}
                    onChange={(e) =>
                      setCohortForm((prev) => ({ ...prev, academic_year: e.target.value }))
                    }
                  />
                </div>
              </div>

              <div className="form-footer">
                <span className="field-note">
                  Cohorts will immediately appear in student registration and teacher assignment filters.
                </span>
                <button
                  type="submit"
                  className="admin-primary-btn"
                  disabled={creatingCohort}
                >
                  <Plus size={15} />
                  <span>{creatingCohort ? "Creating..." : "Create Class Cohort"}</span>
                </button>
              </div>
            </form>
          </div>

          {/* Section 3: Registered Cohorts Table */}
          <div className="admin-card admin-table-card">
            <div className="admin-card-head">
              <div>
                <h3>Active Class Cohorts ({cohorts.length})</h3>
                <p>Currently configured academic batches across university departments.</p>
              </div>
            </div>

            {loading ? (
              <div className="admin-empty-state compact">
                <div className="admin-spinner" />
                <p>Loading cohorts...</p>
              </div>
            ) : cohorts.length === 0 ? (
              <div className="admin-empty-state compact">
                <GraduationCap size={36} className="admin-empty-icon" />
                <h4>No class cohorts configured</h4>
                <p>Use the form above to add your first academic cohort.</p>
              </div>
            ) : (
              <div className="admin-table-responsive">
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>Batch ID</th>
                      <th>Course Program</th>
                      <th>Semester</th>
                      <th>Academic Year</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cohorts.map((cohort) => {
                      const course =
                        cohort.course ||
                        courses.find((c) => c.course_id === cohort.course_id);
                      return (
                        <tr key={cohort.batch_id || cohort.semester_id}>
                          <td>
                            <span className="batch-id-badge">
                              #{cohort.batch_id || cohort.semester_id}
                            </span>
                          </td>
                          <td>
                            <strong>{course?.course_name || "Academic Program"}</strong>
                            <span className="course-code-sub">({course?.code || "—"})</span>
                          </td>
                          <td>
                            <span className="semester-pill">{cohort.semester} Semester</span>
                          </td>
                          <td>
                            <span>{cohort.academic_year}</span>
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
      </div>
    </AdminWorkspace>
  );
}

