import { useEffect, useState } from "react";
import {
  AlertCircle,
  ClipboardList,
  Eye,
  Edit2,
  Plus,
  Scale,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api.js";
import { useFeedback } from "../feedback.jsx";
import { useAuth } from "../auth.jsx";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

const RUBRIC_TYPES = ["technical", "hr", "behavioral", "communication", "other"];

const DEFAULT_CRITERIA_TEXT = `Conceptual correctness | 35
Relevance to the question | 25
Explanation quality | 20
Completeness | 15
Answer structure | 5`;

const EMPTY_RUBRIC_FORM = {
  rubric_name: "",
  rubric_type: "technical",
  maximum_score: 10,
  criteria: DEFAULT_CRITERIA_TEXT,
};

export function TeacherRubrics() {
  const { confirmAction, notify } = useFeedback();
  const { user } = useAuth();
  const [rubrics, setRubrics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [selectedRubric, setSelectedRubric] = useState(null);
  const [rubricForm, setRubricForm] = useState(EMPTY_RUBRIC_FORM);
  const [rubricEditId, setRubricEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [deletingRubricId, setDeletingRubricId] = useState(null);

  function flash(msg) {
    notify(msg, "success");
  }

  function fail(err) {
    setError(err?.message || "Operation failed.");
  }

  async function loadRubrics() {
    try {
      setLoading(true);
      const data = await api("/rubrics");
      setRubrics(Array.isArray(data) ? data : []);
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRubrics();
  }, []);

  function handleOpenCreate() {
    setRubricEditId(null);
    setRubricForm(EMPTY_RUBRIC_FORM);
    setIsEditorOpen(true);
    setError("");
  }

  function handleOpenEdit(r) {
    let criteriaLines = "";
    const list = r?.criteria_json?.criteria;
    if (Array.isArray(list)) {
      criteriaLines = list
        .map((c) => (typeof c === "object" ? `${c.name} | ${c.weight}` : String(c)))
        .join("\n");
    } else {
      criteriaLines = DEFAULT_CRITERIA_TEXT;
    }
    setRubricEditId(r.rubric_id);
    setRubricForm({
      rubric_name: r.rubric_name || "",
      rubric_type: r.rubric_type || "technical",
      maximum_score: r.maximum_score ?? 10,
      criteria: criteriaLines,
    });
    setIsEditorOpen(true);
    setError("");
  }

  async function handleSaveRubric(e) {
    e.preventDefault();
    if (!rubricForm.rubric_name.trim()) {
      setError("Please provide a rubric name.");
      return;
    }

    setSaving(true);
    setError("");

    const criteria = rubricForm.criteria
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const match = line.match(/^(.*?)\s*\|\s*(\d+(?:\.\d+)?)\s*$/);
        return match ? { name: match[1].trim(), weight: Number(match[2]) } : line;
      });

    const payload = {
      rubric_name: rubricForm.rubric_name.trim(),
      rubric_type: rubricForm.rubric_type,
      maximum_score: Number(rubricForm.maximum_score) || 10,
      criteria_json: { criteria },
    };

    try {
      const saved = await api(rubricEditId ? `/rubrics/${rubricEditId}` : "/rubrics", {
        method: rubricEditId ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });

      setRubrics((rows) =>
        rubricEditId
          ? rows.map((row) => (row.rubric_id === saved.rubric_id ? saved : row))
          : [saved, ...rows]
      );
      setIsEditorOpen(false);
      setRubricEditId(null);
      setRubricForm(EMPTY_RUBRIC_FORM);
      flash(rubricEditId ? "Rubric updated successfully." : "Reusable rubric created.");
    } catch (err) {
      fail(err);
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteRubric(r) {
    if (deletingRubricId) return;
    setError("");
    if (r.created_by !== user?.user_id) {
      setError("You can only delete rubrics you authored.");
      return;
    }
    const approved = await confirmAction({
      title: "Delete rubric?",
      description: `Delete “${r.rubric_name}”? Rubrics used by a template or interview cannot be deleted.`,
      confirmLabel: "Delete rubric",
      destructive: true,
    });
    if (!approved) return;
    setDeletingRubricId(r.rubric_id);
    try {
      await api(`/rubrics/${r.rubric_id}`, { method: "DELETE" });
      setRubrics((rows) => rows.filter((row) => row.rubric_id !== r.rubric_id));
      notify("Rubric deleted.", "success");
    } catch (err) {
      notify(err.message || "Could not delete the rubric.", "error");
    } finally {
      setDeletingRubricId(null);
    }
  }

  // Filter rubrics
  const filteredRubrics = rubrics.filter((r) => {
    if (typeFilter !== "all" && r.rubric_type !== typeFilter) return false;
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    const nameMatch = r.rubric_name?.toLowerCase().includes(q);
    const typeMatch = r.rubric_type?.toLowerCase().includes(q);
    const critMatch = JSON.stringify(r.criteria_json || {}).toLowerCase().includes(q);
    return nameMatch || typeMatch || critMatch;
  });

  return (
    <TeacherWorkspace
      user={user}
      active="rubrics"
      pageTitle="Rubrics & Scoring Criteria"
      pageSubtitle="Define and manage evaluation standards for interview assessments."
      searchPlaceholder="Search rubrics by name, skill or criteria..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
      actions={
        <button
          type="button"
          className="teacher-primary-btn"
          onClick={handleOpenCreate}
        >
          <Plus size={16} />
          <span>New Rubric</span>
        </button>
      }
    >
      <div className="teacher-section">
        {/* Alerts */}
        {error && (
          <div className="qm-alert qm-alert-error" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Filters and Header Bar */}
        <div className="teacher-card teacher-filter-toolbar">
          <div className="filter-pill-group">
            <button
              type="button"
              className={`filter-pill ${typeFilter === "all" ? "active" : ""}`}
              onClick={() => setTypeFilter("all")}
            >
              All Rubrics ({rubrics.length})
            </button>
            {RUBRIC_TYPES.map((t) => {
              const count = rubrics.filter((r) => r.rubric_type === t).length;
              return (
                <button
                  key={t}
                  type="button"
                  className={`filter-pill ${typeFilter === t ? "active" : ""}`}
                  onClick={() => setTypeFilter(t)}
                >
                  {t.toUpperCase()} ({count})
                </button>
              );
            })}
          </div>

          <div className="teacher-card-meta">
            Showing {filteredRubrics.length} of {rubrics.length} evaluation rubrics
          </div>
        </div>

        {/* Rubrics Grid */}
        {loading ? (
          <div className="teacher-card teacher-empty-state">
            <div className="teacher-spinner" />
            <p>Loading rubrics catalog...</p>
          </div>
        ) : filteredRubrics.length === 0 ? (
          <div className="teacher-card teacher-empty-state">
            <Scale size={42} className="teacher-empty-icon" />
            <h3>No evaluation rubrics found</h3>
            <p>
              {searchTerm || typeFilter !== "all"
                ? "Try adjusting your search query or filter pills."
                : "Create your first rubric to establish standard question-level scoring."}
            </p>
            <button
              type="button"
              className="teacher-primary-btn"
              onClick={handleOpenCreate}
              style={{ marginTop: "1rem" }}
            >
              <Plus size={16} />
              <span>Create Rubric</span>
            </button>
          </div>
        ) : (
          <div className="teacher-rubrics-grid">
            {filteredRubrics.map((r) => {
              const isMine = r.created_by === user?.user_id;
              const criteriaList = Array.isArray(r.criteria_json?.criteria)
                ? r.criteria_json.criteria
                : [];

              return (
                <div key={r.rubric_id} className="teacher-card teacher-rubric-card">
                  <div className="teacher-rubric-header">
                    <div className="rubric-header-left">
                      <span className={`teacher-type-pill pill-${r.rubric_type}`}>
                        {r.rubric_type}
                      </span>
                      <h3 className="rubric-title">{r.rubric_name}</h3>
                    </div>
                    <span className="rubric-max-badge">
                      <strong>{r.maximum_score}</strong>
                      <small>max points</small>
                    </span>
                  </div>

                  <div className="rubric-card-summary">
                    <span><ClipboardList size={14} /> {criteriaList.length} scoring criteria</span>
                  </div>

                  <div className="teacher-rubric-criteria-list">
                    <div className="criteria-list-label">Scoring breakdown</div>
                    {criteriaList.length > 0 ? (
                      criteriaList.slice(0, 3).map((crit, idx) => {
                        const name = typeof crit === "object" ? crit.name : crit;
                        const weight = typeof crit === "object" ? crit.weight : null;
                        return (
                          <div key={idx} className="rubric-criterion-row">
                            <span className="criterion-name">{name}</span>
                            {weight != null && <span className="criterion-weight">{weight}%</span>}
                          </div>
                        );
                      })
                    ) : (
                      <p className="rubric-no-criteria">Default comprehensive evaluation.</p>
                    )}
                    {criteriaList.length > 3 && (
                      <span className="rubric-more-criteria">+{criteriaList.length - 3} more criteria</span>
                    )}
                  </div>

                  <div className="teacher-rubric-footer">
                    <div className="rubric-meta-author">
                      {isMine ? (
                        <span className="author-badge mine">Authored by you</span>
                      ) : (
                        <span className="author-badge">Institutional standard</span>
                      )}
                    </div>
                    <div className="rubric-actions">
                      <button
                        type="button"
                        className="teacher-outline-btn rubric-sm-btn"
                        onClick={() => setSelectedRubric(r)}
                      >
                        <Eye size={13} />
                        <span>View details</span>
                      </button>
                      {isMine && (
                        <>
                          <button
                            type="button"
                            className="teacher-outline-btn rubric-sm-btn"
                            onClick={() => handleOpenEdit(r)}
                            title="Edit Rubric"
                          >
                            <Edit2 size={13} />
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            className="teacher-danger-btn rubric-sm-btn"
                            onClick={() => handleDeleteRubric(r)}
                            disabled={deletingRubricId !== null}
                            title="Delete Rubric"
                          >
                            <Trash2 size={13} />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {selectedRubric && (
        <div className="teacher-modal-backdrop" onClick={() => setSelectedRubric(null)}>
          <section
            className="teacher-modal teacher-rubric-modal rubric-details-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="rubric-details-title"
          >
            <div className="teacher-modal-header">
              <div className="modal-header-copy">
                <span className={`teacher-type-pill pill-${selectedRubric.rubric_type}`}>
                  {selectedRubric.rubric_type}
                </span>
                <h3 id="rubric-details-title">{selectedRubric.rubric_name}</h3>
                <p>{selectedRubric.created_by === user?.user_id ? "Authored by you" : "Institutional standard"}</p>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setSelectedRubric(null)}
                aria-label="Close rubric details"
              >
                <X size={18} />
              </button>
            </div>
            <div className="rubric-detail-score">
              <span>Maximum score</span>
              <strong>{selectedRubric.maximum_score} <small>points</small></strong>
            </div>
            <div className="rubric-detail-breakdown">
              <h4>Scoring criteria</h4>
              {Array.isArray(selectedRubric.criteria_json?.criteria) && selectedRubric.criteria_json.criteria.length ? (
                selectedRubric.criteria_json.criteria.map((criterion, index) => {
                  const name = typeof criterion === "object" ? criterion.name : criterion;
                  const weight = typeof criterion === "object" ? criterion.weight : null;
                  return (
                    <div className="rubric-detail-row" key={`${name}-${index}`}>
                      <span className="rubric-detail-index">{String(index + 1).padStart(2, "0")}</span>
                      <span className="rubric-detail-name">{name}</span>
                      {weight != null && <strong>{weight}%</strong>}
                    </div>
                  );
                })
              ) : (
                <p className="rubric-no-criteria">No individual criteria are defined for this rubric.</p>
              )}
            </div>
            <div className="teacher-modal-actions">
              {selectedRubric.created_by === user?.user_id && (
                <button
                  type="button"
                  className="teacher-primary-btn"
                  onClick={() => {
                    handleOpenEdit(selectedRubric);
                    setSelectedRubric(null);
                  }}
                >
                  <Edit2 size={14} /> Edit rubric
                </button>
              )}
              <button type="button" className="teacher-outline-btn" onClick={() => setSelectedRubric(null)}>
                Close
              </button>
            </div>
          </section>
        </div>
      )}

      {/* Slide-over or Modal Editor */}
      {isEditorOpen && (
        <div className="teacher-modal-backdrop" onClick={() => setIsEditorOpen(false)}>
          <div
            className="teacher-modal teacher-rubric-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="teacher-modal-header">
              <div className="modal-header-copy">
                <h3>{rubricEditId ? "Edit Rubric" : "Create Scoring Rubric"}</h3>
                <p>Standardize evaluation criteria and score weights across interviews.</p>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setIsEditorOpen(false)}
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveRubric} className="teacher-form">
              <div className="form-grid-2">
                <div className="form-group">
                  <label htmlFor="rubric_name">Rubric Title *</label>
                  <input
                    id="rubric_name"
                    type="text"
                    required
                    placeholder="e.g., Senior Full-Stack Technical Evaluation"
                    value={rubricForm.rubric_name}
                    onChange={(e) =>
                      setRubricForm((prev) => ({ ...prev, rubric_name: e.target.value }))
                    }
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="rubric_type">Evaluation Category</label>
                  <select
                    id="rubric_type"
                    value={rubricForm.rubric_type}
                    onChange={(e) =>
                      setRubricForm((prev) => ({ ...prev, rubric_type: e.target.value }))
                    }
                  >
                    {RUBRIC_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="maximum_score">Maximum Score (Scale Points)</label>
                <input
                  id="maximum_score"
                  type="number"
                  min="1"
                  max="100"
                  value={rubricForm.maximum_score}
                  onChange={(e) =>
                    setRubricForm((prev) => ({ ...prev, maximum_score: e.target.value }))
                  }
                />
              </div>

              <div className="form-group">
                <label htmlFor="criteria">
                  Criteria & Weight Distribution (One per line: <code>Criterion Name | Weight%</code>)
                </label>
                <textarea
                  id="criteria"
                  rows={6}
                  value={rubricForm.criteria}
                  onChange={(e) =>
                    setRubricForm((prev) => ({ ...prev, criteria: e.target.value }))
                  }
                  placeholder={`Conceptual correctness | 35\nRelevance to the question | 25\nExplanation quality | 20\nCompleteness | 15\nAnswer structure | 5`}
                />
                <span className="field-hint">
                  Tip: Total weights across all criteria should ideally sum to 100%.
                </span>
              </div>

              <div className="teacher-modal-actions">
                <button
                  type="button"
                  className="teacher-outline-btn"
                  onClick={() => setIsEditorOpen(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button type="submit" className="teacher-primary-btn" disabled={saving}>
                  {saving ? "Saving..." : rubricEditId ? "Update Rubric" : "Save Rubric"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </TeacherWorkspace>
  );
}

