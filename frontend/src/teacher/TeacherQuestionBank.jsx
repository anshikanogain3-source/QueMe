import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  Edit2,
  Filter,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api.js";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

const TYPES = ["technical", "hr", "behavioral", "communication", "other"];
const emptyQuestion = {
  question_text: "",
  question_type: "technical",
  difficulty: "medium",
  expected_key_points: "",
  reference_answer: "",
  topics: "",
};

export function TeacherQuestionBank({ user }) {
  const [questions, setQuestions] = useState([]);
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [questionForm, setQuestionForm] = useState(emptyQuestion);
  const [questionEditId, setQuestionEditId] = useState(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");

  async function loadQuestions() {
    try {
      const rows = await api("/questions?is_active=all");
      setQuestions(rows || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    let active = true;
    setBusy(true);
    loadQuestions().finally(() => {
      if (active) setBusy(false);
    });
    return () => {
      active = false;
    };
  }, []);

  async function saveQuestion(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await api(
        questionEditId ? `/questions/${questionEditId}` : "/questions",
        {
          method: questionEditId ? "PATCH" : "POST",
          body: JSON.stringify(questionForm),
        }
      );
      setQuestions((rows) =>
        questionEditId
          ? rows.map((r) => (r.question_id === saved.question_id ? saved : r))
          : [saved, ...rows]
      );
      setQuestionForm(emptyQuestion);
      setQuestionEditId(null);
      setNotice("Question saved to question bank.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeQuestion(question) {
    if (question.created_by !== user.user_id) {
      setError("Shared default questions cannot be deleted.");
      return;
    }
    if (!window.confirm("Delete this question? Questions used by templates cannot be deleted."))
      return;
    try {
      await api(`/questions/${question.question_id}`, { method: "DELETE" });
      setQuestions((rows) => rows.filter((r) => r.question_id !== question.question_id));
      setNotice("Question deleted.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleActive(question) {
    try {
      const saved = await api(`/questions/${question.question_id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !question.is_active }),
      });
      setQuestions((rows) =>
        rows.map((r) => (r.question_id === saved.question_id ? saved : r))
      );
      setNotice(`Question ${saved.is_active ? "reactivated" : "deactivated"}.`);
    } catch (err) {
      setError(err.message);
    }
  }

  const filteredQuestions = useMemo(() => {
    let list = questions;
    if (typeFilter !== "all") {
      list = list.filter((q) => q.question_type?.toLowerCase() === typeFilter.toLowerCase());
    }
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(
        (item) =>
          (item.question_text && item.question_text.toLowerCase().includes(q)) ||
          (item.topics && item.topics.some((t) => t.toLowerCase().includes(q)))
      );
    }
    return list;
  }, [questions, typeFilter, searchTerm]);

  return (
    <TeacherWorkspace
      user={user}
      active="questions"
      pageTitle="Question Bank"
      pageSubtitle="Reusable Interview Prompts"
      searchPlaceholder="Search questions by text or topic..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="teacher-question-bank-page">
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

        <div className="student-overview-grid">
          {/* Question List Section */}
          <section className="overview-column-main">
            <div className="practice-toolbar">
              <div className="filter-group">
                <button
                  type="button"
                  className={`filter-pill-btn${typeFilter === "all" ? " active" : ""}`}
                  onClick={() => setTypeFilter("all")}
                >
                  All Types ({questions.length})
                </button>
                {TYPES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={`filter-pill-btn${typeFilter === t ? " active" : ""}`}
                    onClick={() => setTypeFilter(t)}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>

              <div className="toolbar-status">
                <span>{filteredQuestions.length} questions available</span>
              </div>
            </div>

            {busy ? (
              <div className="loading-container">
                <span className="spinner" />
                <span>Loading question bank…</span>
              </div>
            ) : filteredQuestions.length === 0 ? (
              <div className="empty-state">
                <div className="empty-mark">
                  <BookOpen size={24} />
                </div>
                <h3>No questions found</h3>
                <p>Add a question using the authoring form on the right.</p>
              </div>
            ) : (
              <div className="questions-card-list">
                {filteredQuestions.map((q) => {
                  const isMine = q.created_by === user.user_id;

                  return (
                    <article key={q.question_id} className="teacher-question-card">
                      <div className="q-topline">
                        <div className="q-badges">
                          <span className="status-pill status-in_progress">{q.question_type}</span>
                          <span className="status-pill status-scheduled">{q.difficulty}</span>
                          {!q.is_active && (
                            <span className="status-pill status-cancelled">Inactive</span>
                          )}
                          <span className="q-ownership">
                            {isMine ? "Created by you" : "Shared bank"}
                          </span>
                        </div>

                        {isMine && (
                          <div className="q-action-btns">
                            <button
                              type="button"
                              className="button button-outline button-small"
                              onClick={() => {
                                setQuestionEditId(q.question_id);
                                setQuestionForm({
                                  ...q,
                                  topics: (q.topics || []).join(", "),
                                  expected_key_points: q.expected_key_points || "",
                                  reference_answer: q.reference_answer || "",
                                });
                                window.scrollTo({ top: 0, behavior: "smooth" });
                              }}
                            >
                              <Edit2 size={13} />
                              <span>Edit</span>
                            </button>
                            <button
                              type="button"
                              className="button button-quiet button-small"
                              onClick={() => toggleActive(q)}
                            >
                              <span>{q.is_active ? "Deactivate" : "Reactivate"}</span>
                            </button>
                            <button
                              type="button"
                              className="button button-quiet button-small"
                              onClick={() => removeQuestion(q)}
                              aria-label="Delete question"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        )}
                      </div>

                      <h3 className="q-card-text">{q.question_text}</h3>

                      {q.expected_key_points && (
                        <p className="q-card-hint">
                          <strong>Key Concepts:</strong> {q.expected_key_points}
                        </p>
                      )}

                      {q.topics && q.topics.length > 0 && (
                        <div className="q-card-topics">
                          {q.topics.map((t) => (
                            <span key={t} className="criterion-chip">
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          {/* Authoring Form */}
          <aside className="overview-column-side">
            <section className="overview-panel">
              <span className="eyebrow">
                {questionEditId ? "EDIT QUESTION" : "NEW QUESTION"}
              </span>
              <h2>{questionEditId ? "Edit Question" : "Author Question"}</h2>

              <form className="form-stack" onSubmit={saveQuestion}>
                <label className="field">
                  <span>Question Text</span>
                  <textarea
                    required
                    rows={4}
                    maxLength={5000}
                    value={questionForm.question_text}
                    onChange={(e) =>
                      setQuestionForm((prev) => ({
                        ...prev,
                        question_text: e.target.value,
                      }))
                    }
                    placeholder="Enter question prompt clearly..."
                  />
                </label>

                <div className="field-row">
                  <label className="field">
                    <span>Type</span>
                    <select
                      value={questionForm.question_type}
                      onChange={(e) =>
                        setQuestionForm((prev) => ({
                          ...prev,
                          question_type: e.target.value,
                        }))
                      }
                    >
                      {TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t.charAt(0).toUpperCase() + t.slice(1)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field">
                    <span>Difficulty</span>
                    <select
                      value={questionForm.difficulty}
                      onChange={(e) =>
                        setQuestionForm((prev) => ({
                          ...prev,
                          difficulty: e.target.value,
                        }))
                      }
                    >
                      {["easy", "medium", "hard"].map((l) => (
                        <option key={l} value={l}>
                          {l.charAt(0).toUpperCase() + l.slice(1)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="field">
                  <span>Topics (comma separated)</span>
                  <input
                    maxLength={1000}
                    value={questionForm.topics}
                    onChange={(e) =>
                      setQuestionForm((prev) => ({ ...prev, topics: e.target.value }))
                    }
                    placeholder="e.g. Algorithms, Data Structures, OOP"
                  />
                </label>

                <label className="field">
                  <span>Expected Key Points (Optional)</span>
                  <textarea
                    rows={3}
                    maxLength={5000}
                    value={questionForm.expected_key_points}
                    onChange={(e) =>
                      setQuestionForm((prev) => ({
                        ...prev,
                        expected_key_points: e.target.value,
                      }))
                    }
                    placeholder="Concepts students should mention..."
                  />
                </label>

                <label className="field">
                  <span>Reference Answer (Optional)</span>
                  <textarea
                    rows={3}
                    maxLength={10000}
                    value={questionForm.reference_answer}
                    onChange={(e) =>
                      setQuestionForm((prev) => ({
                        ...prev,
                        reference_answer: e.target.value,
                      }))
                    }
                    placeholder="Ideal benchmark response..."
                  />
                </label>

                <button type="submit" className="button button-primary" disabled={saving}>
                  <span>{saving ? "Saving…" : questionEditId ? "Save Question" : "Add to Library"}</span>
                </button>

                {questionEditId && (
                  <button
                    type="button"
                    className="button button-outline"
                    onClick={() => {
                      setQuestionEditId(null);
                      setQuestionForm(emptyQuestion);
                    }}
                  >
                    Cancel Editing
                  </button>
                )}
              </form>
            </section>
          </aside>
        </div>
      </div>
    </TeacherWorkspace>
  );
}

