import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  BriefcaseBusiness,
  Calendar,
  CheckCircle2,
  Clock3,
  FileBarChart2,
  FilePlus2,
  Layers,
  Play,
  RotateCcw,
  Sparkles,
  Trash2,
  User,
  X,
} from "lucide-react";
import { api } from "../api.js";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

const TYPES = ["technical", "hr", "behavioral", "communication", "other"];

export function TeacherInterviews({ user }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "sessions"; // 'sessions' | 'templates' | 'create' | 'assign'
  const [activeTab, setActiveTab] = useState(initialTab);

  const [interviews, setInterviews] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [rubrics, setRubrics] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [students, setStudents] = useState([]);

  // Template Form State
  const [templateForm, setTemplateForm] = useState({
    title: "",
    description: "",
    duration_minutes: "",
  });
  const [templateEditId, setTemplateEditId] = useState(null);
  const [selectedQuestions, setSelectedQuestions] = useState([]);
  const [questionRubrics, setQuestionRubrics] = useState({});
  const [draggedQuestionId, setDraggedQuestionId] = useState(null);

  // AI Draft Generator State
  const [draftPrompt, setDraftPrompt] = useState({
    topic: "",
    question_type: "technical",
    difficulty: "medium",
  });
  const [drafts, setDrafts] = useState([]);
  const [selectedDrafts, setSelectedDrafts] = useState([]);
  const [draftBusy, setDraftBusy] = useState(false);
  const [draftMessage, setDraftMessage] = useState("");

  // Assignment Form State
  const [assignment, setAssignment] = useState({
    template_id: "",
    batch_id: "",
    student_id: searchParams.get("student_id") || "",
    scheduled_at: "",
    target: searchParams.get("student_id") ? "student" : "group",
  });

  const [sessionFilter, setSessionFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const navigate = useNavigate();

  async function refresh() {
    const [interviewRows, templateRows, questionRows, rubricRows, cohortRows] =
      await Promise.all([
        api("/interviews"),
        api("/templates"),
        api("/questions?is_active=all"),
        api("/rubrics"),
        api("/admin/semesters"),
      ]);
    setInterviews(interviewRows || []);
    setTemplates(templateRows || []);
    setQuestions(questionRows || []);
    setRubrics(rubricRows || []);
    const validCohorts = (cohortRows || []).filter((c) => c.academic_year);
    setCohorts(validCohorts);
    if (!assignment.batch_id && validCohorts.length > 0) {
      setAssignment((prev) => ({ ...prev, batch_id: String(validCohorts[0].batch_id) }));
    }
  }

  useEffect(() => {
    let active = true;
    setBusy(true);
    refresh()
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

  // Fetch students when assignment.batch_id changes
  useEffect(() => {
    if (!assignment.batch_id) {
      setStudents([]);
      return;
    }
    api(`/teacher/students?batch_id=${assignment.batch_id}`)
      .then((data) => setStudents(data || []))
      .catch((err) => setError(err.message));
  }, [assignment.batch_id]);

  function switchTab(tab) {
    setActiveTab(tab);
    setSearchParams({ tab });
  }

  function toggleQuestion(id) {
    setSelectedQuestions((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  }

  function toggleAllLibraryQuestions() {
    const activeQuestionIds = questions
      .filter((question) => question.is_active)
      .map((question) => question.question_id);
    const allSelected = activeQuestionIds.every((id) => selectedQuestions.includes(id));
    setSelectedQuestions((prev) =>
      allSelected
        ? prev.filter((id) => !activeQuestionIds.includes(id))
        : [...prev, ...activeQuestionIds.filter((id) => !prev.includes(id))]
    );
  }

  function toggleAllDrafts() {
    const allSelected = drafts.every((_, index) => selectedDrafts.includes(index));
    setSelectedDrafts(allSelected ? [] : drafts.map((_, index) => index));
  }

  function moveQuestion(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= selectedQuestions.length) return;
    reorderQuestion(index, target);
  }

  function reorderQuestion(sourceIndex, targetIndex) {
    setSelectedQuestions((prev) => {
      if (
        sourceIndex < 0 || sourceIndex >= prev.length ||
        targetIndex < 0 || targetIndex >= prev.length || sourceIndex === targetIndex
      ) return prev;
      const next = [...prev];
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
  }

  function dropQuestion(targetQuestionId) {
    const sourceIndex = selectedQuestions.indexOf(draggedQuestionId);
    const targetIndex = selectedQuestions.indexOf(targetQuestionId);
    if (sourceIndex !== -1 && targetIndex !== -1) {
      reorderQuestion(sourceIndex, targetIndex);
    }
    setDraggedQuestionId(null);
  }

  async function generateDrafts() {
    setDraftBusy(true);
    setDraftMessage("");
    setDrafts([]);
    setSelectedDrafts([]);
    setError("");
    try {
      const result = await api("/questions/generate", {
        method: "POST",
        body: JSON.stringify(draftPrompt),
      });
      setDrafts((result.questions || []).map((row) => ({ ...row, reference_answer: "" })));
      setDraftMessage(
        result.message ||
          "Review each draft, select the questions you want, then add them to this interview."
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setDraftBusy(false);
    }
  }

  async function addDraftsToInterview() {
    const selected = drafts.filter((_, index) => selectedDrafts.includes(index));
    if (!selected.length) {
      setError("Select at least one reviewed draft question first.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await api("/questions/commit-drafts", {
        method: "POST",
        body: JSON.stringify({ questions: selected }),
      });
      const savedRows = result.questions || [];
      setQuestions((rows) => [
        ...savedRows.filter((saved) => !rows.some((r) => r.question_id === saved.question_id)),
        ...rows,
      ]);
      const addedIds = [...new Set(result.question_ids || [])];
      setSelectedQuestions((prev) => [...prev, ...addedIds.filter((id) => !prev.includes(id))]);
      setDrafts((prev) => prev.filter((_, index) => !selectedDrafts.includes(index)));
      setSelectedDrafts([]);
      setNotice(
        `${addedIds.length} question(s) added to this interview and saved to your library.`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function saveTemplate() {
    setError("");
    setNotice("");
    if (!templateForm.title.trim()) {
      setError("Enter an interview title.");
      return;
    }
    if (selectedQuestions.length < 1 || selectedQuestions.length > 50) {
      setError("Select between 1 and 50 questions for this interview.");
      return;
    }
    setSaving(true);
    const payload = {
      ...templateForm,
      duration_minutes: templateForm.duration_minutes
        ? Number(templateForm.duration_minutes)
        : null,
      questions: selectedQuestions.map((id) => ({
        question_id: id,
        rubric_id: questionRubrics[id] ? Number(questionRubrics[id]) : null,
      })),
    };

    try {
      const saved = await api(
        templateEditId ? `/templates/${templateEditId}` : "/templates",
        {
          method: templateEditId ? "PATCH" : "POST",
          body: JSON.stringify(payload),
        }
      );
      setTemplates((rows) =>
        templateEditId
          ? rows.map((r) => (r.template_id === saved.template_id ? saved : r))
          : [saved, ...rows]
      );
      setTemplateForm({ title: "", description: "", duration_minutes: "" });
      setSelectedQuestions([]);
      setQuestionRubrics({});
      setTemplateEditId(null);
      setNotice("Interview template saved successfully.");
      switchTab("templates");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  function editTemplate(template) {
    setTemplateEditId(template.template_id);
    setTemplateForm({
      title: template.title,
      description: template.description || "",
      duration_minutes: template.duration_minutes || "",
    });
    setSelectedQuestions((template.questions || []).map((item) => item.question_id));
    setQuestionRubrics(
      Object.fromEntries(
        (template.questions || []).map((item) => [item.question_id, item.rubric_id || ""])
      )
    );
    switchTab("create");
  }

  async function deleteTemplate(template) {
    if (!window.confirm("Delete this template? Assigned interviews prevent deletion.")) return;
    try {
      await api(`/templates/${template.template_id}`, { method: "DELETE" });
      setTemplates((rows) => rows.filter((r) => r.template_id !== template.template_id));
      setNotice("Template deleted.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function assignInterview(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    const payload = {
      template_id: Number(assignment.template_id),
      scheduled_at: assignment.scheduled_at || null,
    };
    if (assignment.target === "group") payload.batch_id = Number(assignment.batch_id);
    else payload.student_id = Number(assignment.student_id);

    try {
      const result = await api("/interviews", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setNotice(`Interview assigned to ${result.assigned_count} student(s).`);
      await refresh();
      switchTab("sessions");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function cancelInterview(interview) {
    if (
      !window.confirm(
        `Cancel scheduled interview for ${interview.student_name || "this student"}?`
      )
    )
      return;
    try {
      await api(`/interviews/${interview.interview_id}/cancel`, { method: "POST" });
      setNotice("Scheduled interview cancelled.");
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  // Filtered Sessions
  const filteredSessions = useMemo(() => {
    let list = interviews;
    if (sessionFilter === "ready") {
      list = list.filter((i) => i.status === "SCHEDULED" || i.status === "IN_PROGRESS");
    } else if (sessionFilter === "completed") {
      list = list.filter((i) => i.status === "COMPLETED");
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(
        (i) =>
          (i.template_title && i.template_title.toLowerCase().includes(q)) ||
          (i.student_name && i.student_name.toLowerCase().includes(q))
      );
    }
    return list;
  }, [interviews, sessionFilter, searchTerm]);

  const selectedQuestionRows = useMemo(
    () => selectedQuestions.map((id) => questions.find((q) => q.question_id === id)).filter(Boolean),
    [selectedQuestions, questions]
  );
  const activeQuestionIds = questions
    .filter((question) => question.is_active)
    .map((question) => question.question_id);
  const allLibraryQuestionsSelected = activeQuestionIds.length > 0 &&
    activeQuestionIds.every((id) => selectedQuestions.includes(id));

  return (
    <TeacherWorkspace
      user={user}
      active="interviews"
      pageTitle="Interview Management"
      pageSubtitle="Sessions, Templates & Assignments"
    >
      <div className="teacher-interviews-page">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="alert alert-info" role="status">
            {notice}
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="practice-toolbar">
          <div className="filter-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "sessions"}
              className={`filter-tab${activeTab === "sessions" ? " active" : ""}`}
              onClick={() => switchTab("sessions")}
            >
              Assigned Sessions <span className="tab-count">{interviews.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "templates"}
              className={`filter-tab${activeTab === "templates" ? " active" : ""}`}
              onClick={() => switchTab("templates")}
            >
              Templates <span className="tab-count">{templates.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "create"}
              className={`filter-tab${activeTab === "create" ? " active" : ""}`}
              onClick={() => switchTab("create")}
            >
              {templateEditId ? "Edit Template" : "＋ Create Template"}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "assign"}
              className={`filter-tab${activeTab === "assign" ? " active" : ""}`}
              onClick={() => switchTab("assign")}
            >
              Assign Interview
            </button>
          </div>
        </div>

        {/* TAB 1: Assigned Sessions */}
        {activeTab === "sessions" && (
          <div className="tab-content-stack">
            <div className="sessions-filter-row">
              <div className="filter-group">
                <button
                  type="button"
                  className={`filter-pill-btn${sessionFilter === "all" ? " active" : ""}`}
                  onClick={() => setSessionFilter("all")}
                >
                  All ({interviews.length})
                </button>
                <button
                  type="button"
                  className={`filter-pill-btn${sessionFilter === "ready" ? " active" : ""}`}
                  onClick={() => setSessionFilter("ready")}
                >
                  Active / Scheduled (
                  {interviews.filter((i) => i.status === "SCHEDULED" || i.status === "IN_PROGRESS").length}
                  )
                </button>
                <button
                  type="button"
                  className={`filter-pill-btn${sessionFilter === "completed" ? " active" : ""}`}
                  onClick={() => setSessionFilter("completed")}
                >
                  Completed ({interviews.filter((i) => i.status === "COMPLETED").length})
                </button>
              </div>

              <div className="teacher-topbar-search" style={{ width: "280px" }}>
                <input
                  type="text"
                  placeholder="Search student or title..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>

            {filteredSessions.length === 0 ? (
              <div className="empty-state">
                <div className="empty-mark">
                  <BriefcaseBusiness size={24} />
                </div>
                <h3>No interview sessions found</h3>
                <p>Assign a saved template to a class group or student to begin.</p>
                <button
                  type="button"
                  className="button button-primary button-small"
                  onClick={() => switchTab("assign")}
                >
                  Assign Interview
                </button>
              </div>
            ) : (
              <div className="interviews-grid">
                {filteredSessions.map((item) => {
                  const isDone = item.status === "COMPLETED";
                  const dateStr = item.scheduled_at
                    ? new Date(item.scheduled_at).toLocaleString([], {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })
                    : "No schedule";

                  return (
                    <article key={item.interview_id} className="interview-saas-card">
                      <div className="card-topline">
                        <span className={`status-pill status-${item.status.toLowerCase()}`}>
                          {item.status.replaceAll("_", " ")}
                        </span>
                        {isDone && item.final_score != null && (
                          <span className="card-score-badge">Score: {item.final_score}/10</span>
                        )}
                      </div>

                      <div className="card-body">
                        <h3 className="card-title">
                          {item.template_title || "Mock Interview"}
                        </h3>
                        <div className="card-meta">
                          <div className="meta-row">
                            <User size={13} />
                            <span>
                              Candidate: <strong>{item.student_name || "Student"}</strong>
                            </span>
                          </div>
                          <div className="meta-row">
                            <Calendar size={13} />
                            <span>{dateStr}</span>
                          </div>
                        </div>
                      </div>

                      <div className="card-actions">
                        {isDone ? (
                          <button
                            type="button"
                            className="button button-outline button-wide"
                            onClick={() => navigate(`/interviews/${item.interview_id}/report`)}
                          >
                            <FileBarChart2 size={14} />
                            <span>Results & Review</span>
                            <ArrowRight size={13} />
                          </button>
                        ) : item.status === "SCHEDULED" ? (
                          <button
                            type="button"
                            className="button button-quiet button-wide"
                            onClick={() => cancelInterview(item)}
                          >
                            <X size={14} />
                            <span>Cancel Session</span>
                          </button>
                        ) : (
                          <span className="status-pill status-in_progress">Student In Progress</span>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: Saved Templates */}
        {activeTab === "templates" && (
          <div className="tab-content-stack">
            {templates.length === 0 ? (
              <div className="empty-state">
                <div className="empty-mark">
                  <FilePlus2 size={24} />
                </div>
                <h3>No Interview Templates Saved</h3>
                <p>Build your first interview set with custom questions and rubrics.</p>
                <button
                  type="button"
                  className="button button-primary button-small"
                  onClick={() => switchTab("create")}
                >
                  Create Template
                </button>
              </div>
            ) : (
              <div className="interviews-grid">
                {templates.map((tpl) => (
                  <article key={tpl.template_id} className="interview-saas-card">
                    <div className="card-topline">
                      <span className="status-pill status-scheduled">
                        {tpl.questions?.length || 0} Questions
                      </span>
                      {tpl.duration_minutes && (
                        <span className="card-score-badge">{tpl.duration_minutes} min</span>
                      )}
                    </div>

                    <div className="card-body">
                      <h3 className="card-title">{tpl.title}</h3>
                      <p className="panel-desc">
                        {tpl.description || "No description provided."}
                      </p>
                    </div>

                    <div className="card-actions" style={{ display: "flex", gap: "8px" }}>
                      <button
                        type="button"
                        className="button button-primary button-small"
                        style={{ flex: 1 }}
                        onClick={() => {
                          setAssignment((prev) => ({
                            ...prev,
                            template_id: String(tpl.template_id),
                          }));
                          switchTab("assign");
                        }}
                      >
                        Assign
                      </button>
                      <button
                        type="button"
                        className="button button-outline button-small"
                        onClick={() => editTemplate(tpl)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="button button-quiet button-small"
                        onClick={() => deleteTemplate(tpl)}
                        aria-label="Delete template"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Create / Edit Template */}
        {activeTab === "create" && (
          <div className="student-overview-grid">
            <section className="overview-panel">
              <span className="eyebrow">STEP 1 · CONFIGURATION</span>
              <h2>{templateEditId ? "Edit Interview Template" : "Build Interview Template"}</h2>

              <div className="form-stack">
                <label className="field">
                  <span>Interview Title</span>
                  <input
                    required
                    maxLength={150}
                    value={templateForm.title}
                    onChange={(e) =>
                      setTemplateForm((prev) => ({ ...prev, title: e.target.value }))
                    }
                    placeholder="e.g. Full Stack Technical & Behavioral Practice"
                  />
                </label>

                <label className="field">
                  <span>Instructions / Description (Optional)</span>
                  <textarea
                    rows={3}
                    maxLength={5000}
                    value={templateForm.description}
                    onChange={(e) =>
                      setTemplateForm((prev) => ({ ...prev, description: e.target.value }))
                    }
                    placeholder="Provide guidance or topics covered in this practice..."
                  />
                </label>

                <label className="field">
                  <span>Time Limit in Minutes (Optional)</span>
                  <input
                    type="number"
                    min={1}
                    max={600}
                    value={templateForm.duration_minutes}
                    onChange={(e) =>
                      setTemplateForm((prev) => ({
                        ...prev,
                        duration_minutes: e.target.value,
                      }))
                    }
                    placeholder="e.g. 45"
                  />
                </label>

                <div className="field">
                  <div className="question-select-toolbar">
                    <span>Select Questions from Library ({selectedQuestions.length} selected)</span>
                    <button
                      type="button"
                      className="button button-outline button-small"
                      disabled={activeQuestionIds.length === 0}
                      onClick={toggleAllLibraryQuestions}
                    >
                      {allLibraryQuestionsSelected ? "Deselect all" : "Select all"}
                    </button>
                  </div>
                  <div className="teacher-question-picker">
                    {questions
                      .filter((q) => q.is_active)
                      .map((q) => (
                        <div className="teacher-picker-row" key={q.question_id}>
                          <label>
                            <input
                              type="checkbox"
                              checked={selectedQuestions.includes(q.question_id)}
                              onChange={() => toggleQuestion(q.question_id)}
                            />
                            <span>
                              <strong>{q.question_text}</strong>
                              <small>
                                {q.question_type} · {q.difficulty}
                              </small>
                            </span>
                          </label>
                          {selectedQuestions.includes(q.question_id) && (
                            <select
                              aria-label={`Rubric for ${q.question_text}`}
                              value={questionRubrics[q.question_id] || ""}
                              onChange={(e) =>
                                setQuestionRubrics((prev) => ({
                                  ...prev,
                                  [q.question_id]: e.target.value,
                                }))
                              }
                            >
                              <option value="">No rubric</option>
                              {rubrics.map((r) => (
                                <option key={r.rubric_id} value={r.rubric_id}>
                                  {r.rubric_name}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      ))}
                  </div>
                </div>

                {selectedQuestionRows.length > 0 && (
                  <div className="selected-question-order">
                    <strong>Question Order (drag to reorder or use arrows):</strong>
                    {selectedQuestionRows.map((q, index) => (
                      <div
                        key={q.question_id}
                        className={`selected-row-item${draggedQuestionId === q.question_id ? " is-dragging" : ""}`}
                        draggable
                        onDragStart={(event) => {
                          setDraggedQuestionId(q.question_id);
                          event.dataTransfer.effectAllowed = "move";
                          event.dataTransfer.setData("text/plain", String(q.question_id));
                        }}
                        onDragOver={(event) => {
                          event.preventDefault();
                          event.dataTransfer.dropEffect = "move";
                        }}
                        onDrop={(event) => {
                          event.preventDefault();
                          dropQuestion(q.question_id);
                        }}
                        onDragEnd={() => setDraggedQuestionId(null)}
                      >
                        <span>
                          {index + 1}. {q.question_text}
                        </span>
                        <div className="order-actions">
                          <button
                            type="button"
                            className="text-button"
                            aria-label={`Move question ${index + 1} up`}
                            disabled={index === 0}
                            onClick={() => moveQuestion(index, -1)}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            className="text-button"
                            aria-label={`Move question ${index + 1} down`}
                            disabled={index === selectedQuestionRows.length - 1}
                            onClick={() => moveQuestion(index, 1)}
                          >
                            ↓
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="form-actions-row">
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={saving || selectedQuestions.length === 0}
                    onClick={saveTemplate}
                  >
                    <span>
                      {saving
                        ? "Saving…"
                        : templateEditId
                        ? "Update Template"
                        : "Save Interview Template"}
                    </span>
                  </button>
                  {templateEditId && (
                    <button
                      type="button"
                      className="button button-outline"
                      onClick={() => {
                        setTemplateEditId(null);
                        setTemplateForm({ title: "", description: "", duration_minutes: "" });
                        setSelectedQuestions([]);
                      }}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            </section>

            {/* AI Generator Panel */}
            <aside className="overview-column-side">
              <section className="overview-panel">
                <div className="tip-header">
                  <Sparkles size={16} />
                  <strong>AI Question Generator</strong>
                </div>
                <p className="panel-desc">
                  Generate draft questions on any topic. Reviewed drafts are automatically added to
                  your reusable question library.
                </p>

                <div className="form-stack">
                  <label className="field">
                    <span>Topic</span>
                    <input
                      required
                      value={draftPrompt.topic}
                      onChange={(e) =>
                        setDraftPrompt((prev) => ({ ...prev, topic: e.target.value }))
                      }
                      placeholder="e.g. Database Indexing & ACID"
                    />
                  </label>

                  <div className="field-row">
                    <label className="field">
                      <span>Type</span>
                      <select
                        value={draftPrompt.question_type}
                        onChange={(e) =>
                          setDraftPrompt((prev) => ({
                            ...prev,
                            question_type: e.target.value,
                          }))
                        }
                      >
                        {TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="field">
                      <span>Difficulty</span>
                      <select
                        value={draftPrompt.difficulty}
                        onChange={(e) =>
                          setDraftPrompt((prev) => ({
                            ...prev,
                            difficulty: e.target.value,
                          }))
                        }
                      >
                        {["easy", "medium", "hard"].map((l) => (
                          <option key={l} value={l}>
                            {l}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <button
                    type="button"
                    className="button button-outline"
                    disabled={draftBusy || !draftPrompt.topic.trim()}
                    onClick={generateDrafts}
                  >
                    {draftBusy ? "Generating drafts…" : "Generate Drafts"}
                  </button>

                  {draftMessage && <p className="muted small-copy">{draftMessage}</p>}

                  {drafts.length > 0 && (
                    <div className="teacher-draft-list">
                      <button
                        type="button"
                        className="button button-outline button-small"
                        onClick={toggleAllDrafts}
                      >
                        {drafts.every((_, index) => selectedDrafts.includes(index))
                          ? "Deselect all drafts"
                          : "Select all drafts"}
                      </button>
                      {drafts.map((draft, idx) => (
                        <div key={idx} className="teacher-draft">
                          <label>
                            <input
                              type="checkbox"
                              checked={selectedDrafts.includes(idx)}
                              onChange={(e) =>
                                setSelectedDrafts((prev) =>
                                  e.target.checked
                                    ? [...prev, idx]
                                    : prev.filter((i) => i !== idx)
                                )
                              }
                            />
                            <span>Select draft {idx + 1}</span>
                          </label>
                          <textarea
                            rows={2}
                            value={draft.question_text}
                            onChange={(e) =>
                              setDrafts((prev) =>
                                prev.map((item, i) =>
                                  i === idx ? { ...item, question_text: e.target.value } : item
                                )
                              )
                            }
                          />
                        </div>
                      ))}
                      <button
                        type="button"
                        className="button button-primary button-small"
                        disabled={saving || selectedDrafts.length === 0}
                        onClick={addDraftsToInterview}
                      >
                        Add {selectedDrafts.length} Selected to Interview
                      </button>
                    </div>
                  )}
                </div>
              </section>
            </aside>
          </div>
        )}

        {/* TAB 4: Assign Interview */}
        {activeTab === "assign" && (
          <section className="overview-panel" style={{ maxWidth: "720px", margin: "0 auto" }}>
            <span className="eyebrow">STEP 2 · DISPATCH</span>
            <h2>Assign Interview Practice</h2>
            <p className="panel-desc">
              Dispatch an interview template to an entire class group or an individual student.
            </p>

            <form className="form-stack" onSubmit={assignInterview}>
              <label className="field">
                <span>Select Interview Template</span>
                <select
                  required
                  value={assignment.template_id}
                  onChange={(e) =>
                    setAssignment((prev) => ({ ...prev, template_id: e.target.value }))
                  }
                >
                  <option value="">Choose template</option>
                  {templates.map((tpl) => (
                    <option key={tpl.template_id} value={tpl.template_id}>
                      {tpl.title} ({tpl.questions?.length || 0} questions)
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>Assignment Target</span>
                <select
                  value={assignment.target}
                  onChange={(e) =>
                    setAssignment((prev) => ({
                      ...prev,
                      target: e.target.value,
                      student_id: "",
                    }))
                  }
                >
                  <option value="group">All students in a class group</option>
                  <option value="student">One individual student</option>
                </select>
              </label>

              <label className="field">
                <span>Course · Semester · Academic Year</span>
                <select
                  required
                  value={assignment.batch_id}
                  onChange={(e) =>
                    setAssignment((prev) => ({
                      ...prev,
                      batch_id: e.target.value,
                      student_id: "",
                    }))
                  }
                >
                  <option value="">Choose class group</option>
                  {cohorts.map((cohort) => (
                    <option key={cohort.batch_id} value={cohort.batch_id}>
                      {cohort.course_name || cohort.course_id} · {cohort.semester} ·{" "}
                      {cohort.academic_year}
                    </option>
                  ))}
                </select>
              </label>

              {assignment.target === "student" && (
                <label className="field">
                  <span>Student</span>
                  <select
                    required
                    value={assignment.student_id}
                    onChange={(e) =>
                      setAssignment((prev) => ({ ...prev, student_id: e.target.value }))
                    }
                  >
                    <option value="">Choose student</option>
                    {students.map((s) => (
                      <option key={s.user_id} value={s.user_id}>
                        {s.full_name} ({s.roll_number || s.email})
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className="field">
                <span>Scheduled Date and Time (Optional)</span>
                <input
                  type="datetime-local"
                  value={assignment.scheduled_at}
                  onChange={(e) =>
                    setAssignment((prev) => ({ ...prev, scheduled_at: e.target.value }))
                  }
                />
              </label>

              <button
                type="submit"
                className="button button-primary"
                disabled={
                  saving ||
                  !assignment.template_id ||
                  !assignment.batch_id ||
                  (assignment.target === "student" && !assignment.student_id)
                }
              >
                <span>{saving ? "Assigning…" : "Confirm & Assign Interview"}</span>
                <ArrowRight size={14} />
              </button>
            </form>
          </section>
        )}
      </div>
    </TeacherWorkspace>
  );
}
