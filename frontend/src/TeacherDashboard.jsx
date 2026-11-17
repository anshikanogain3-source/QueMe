import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BarChart3, BookOpen, CheckCircle2, ClipboardList, FileBarChart2, FilePlus2, LogOut, Menu, Search, Users } from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./auth.jsx";
import { Brand } from "./Brand.jsx";
import { useFeedback } from "./feedback.jsx";

const TYPES = ["technical", "hr", "behavioral", "communication", "other"];
const emptyQuestion = { question_text: "", question_type: "technical", difficulty: "medium", expected_key_points: "", reference_answer: "", topics: "" };
const emptyRubric = { rubric_name: "", rubric_type: "technical", maximum_score: 10, criteria: "Conceptual correctness | 35\nRelevance to the question | 25\nExplanation quality | 20\nCompleteness | 15\nAnswer structure | 5" };

function dateLabel(value) {
  return value ? new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Not scheduled";
}

function TeacherFrame({ user, activeItem, onNavigate, search, children }) {
  const { logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const items = [
    ["overview", "Dashboard", BarChart3],
    ["build", "Create interview", FilePlus2],
    ["questions", "Question bank", BookOpen],
    ["reports", "Reports", FileBarChart2],
    ["rubrics", "Rubrics", ClipboardList],
  ];

  function navigate(item) {
    onNavigate(item);
    setSidebarOpen(false);
  }

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const closeOnEscape = (event) => { if (event.key === "Escape") setSidebarOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [sidebarOpen]);

  return (
    <div className="teacher-app">
      {sidebarOpen && <button className="teacher-sidebar-backdrop" aria-label="Close teacher navigation" onClick={() => setSidebarOpen(false)} />}
      <aside className={`teacher-sidebar${sidebarOpen ? " is-open" : ""}`}>
        <Brand className="teacher-sidebar-brand" to="/dashboard" />
        <nav className="teacher-side-nav" aria-label="Teacher workspace">
          {items.map(([id, label, Icon]) => <button key={id} type="button" className={`teacher-side-link${activeItem === id ? " active" : ""}`} aria-current={activeItem === id ? "page" : undefined} onClick={() => navigate(id)}><Icon className="teacher-side-icon" size={17} aria-hidden="true" /><span>{label}</span></button>)}
        </nav>
        <div className="teacher-sidebar-note"><span className="teacher-sidebar-sprout" aria-hidden="true"><Users size={19} /></span><p>Support every student’s<br />next opportunity.</p><span className="teacher-note-line" /></div>
        <button className="teacher-signout" type="button" onClick={logout}><LogOut size={16} aria-hidden="true" />Sign out</button>
      </aside>
      <div className="teacher-content">
        <header className="teacher-topbar">
          <button className="teacher-menu-button" type="button" aria-label="Open teacher navigation" aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(true)}><Menu size={19} /></button>
          {search || <div className="teacher-topbar-spacer" />}
          <details className="teacher-profile-menu">
            <summary><span className="teacher-avatar">{user.full_name?.[0]?.toUpperCase() || "T"}</span><span className="teacher-profile-copy"><strong>{user.full_name}</strong><small>Teacher</small></span><span className="teacher-profile-chevron" aria-hidden="true">⌄</span></summary>
            <div className="teacher-profile-dropdown"><span>{user.email}</span><button type="button" onClick={logout}><LogOut size={15} />Sign out</button></div>
          </details>
        </header>
        <main className="teacher-main">{children}</main>
      </div>
    </div>
  );
}

function TeacherDashboard({ user }) {
  const { confirmAction } = useFeedback();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");
  const [activeItem, setActiveItem] = useState("overview");
  const [interviews, setInterviews] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [questions, setQuestions] = useState([]);
  const [rubrics, setRubrics] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [students, setStudents] = useState([]);
  const [questionForm, setQuestionForm] = useState(emptyQuestion);
  const [questionEditId, setQuestionEditId] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [selectedDrafts, setSelectedDrafts] = useState([]);
  const [draftMessage, setDraftMessage] = useState("");
  const [draftAttempted, setDraftAttempted] = useState(false);
  const [draftBusy, setDraftBusy] = useState(false);
  const [draftPrompt, setDraftPrompt] = useState({ topic: "", question_type: "technical", difficulty: "medium" });
  const [rubricForm, setRubricForm] = useState(emptyRubric);
  const [rubricEditId, setRubricEditId] = useState(null);
  const [templateForm, setTemplateForm] = useState({ title: "", description: "", duration_minutes: "" });
  const [selectedQuestions, setSelectedQuestions] = useState([]);
  const [questionRubrics, setQuestionRubrics] = useState({});
  const [templateEditId, setTemplateEditId] = useState(null);
  const [assignment, setAssignment] = useState({ template_id: "", batch_id: "", student_id: "", scheduled_at: "", target: "group" });
  const [busy, setBusy] = useState(true);
  const [workspaceLoaded, setWorkspaceLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function goToTab(nextTab) {
    setTab(nextTab);
    setActiveItem(nextTab);
  }

  function navigateWorkspace(item) {
    setActiveItem(item);
    if (item === "reports") {
      setTab("overview");
      window.setTimeout(() => document.getElementById("teacher-sessions")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
      return;
    }
    setTab(item);
  }

  const searchResults = useMemo(() => {
    const query = searchTerm.trim().toLocaleLowerCase();
    if (!query) return [];
    const sessions = interviews.map((row) => ({ kind: "session", id: row.interview_id, title: row.student_name || row.template_title || "Interview session", detail: `${row.template_title || "Interview"} · ${row.status.replaceAll("_", " ").toLowerCase()}`, value: `${row.student_name || ""} ${row.template_title || ""} ${row.status}` }));
    const savedTemplates = templates.map((row) => ({ kind: "template", id: row.template_id, title: row.title, detail: `Template · ${row.questions?.length || 0} questions`, value: row.title }));
    const bankQuestions = questions.map((row) => ({ kind: "question", id: row.question_id, title: row.question_text, detail: `Question · ${row.question_type} · ${row.difficulty}`, value: `${row.question_text} ${row.question_type} ${row.difficulty}` }));
    return [...sessions, ...savedTemplates, ...bankQuestions].filter((row) => row.value.toLocaleLowerCase().includes(query)).slice(0, 7);
  }, [searchTerm, interviews, templates, questions]);

  function openSearchResult(result) {
    setSearchTerm("");
    if (result.kind === "session") {
      const session = interviews.find((row) => row.interview_id === result.id);
      if (session?.status === "COMPLETED") navigate(`/interviews/${result.id}/report`);
      else { navigateWorkspace("reports"); window.setTimeout(() => document.getElementById(`teacher-interview-${result.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 40); }
    } else if (result.kind === "template") {
      navigateWorkspace("overview"); window.setTimeout(() => document.getElementById(`teacher-template-${result.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 40);
    } else {
      navigateWorkspace("questions"); window.setTimeout(() => document.getElementById(`teacher-question-${result.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 40);
    }
  }

  async function retryRefresh() {
    setBusy(true); setError("");
    try {
      await refresh();
      if (assignment.batch_id) setStudents(await api(`/teacher/students?batch_id=${assignment.batch_id}`));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function refresh() {
    const [interviewRows, stats, questionRows, rubricRows, templateRows, cohortRows] = await Promise.all([
      api("/interviews"), api("/teacher/analytics"), api("/questions?is_active=all"), api("/rubrics"), api("/templates"), api("/admin/semesters"),
    ]);
    setInterviews(interviewRows); setAnalytics(stats); setQuestions(questionRows); setRubrics(rubricRows);
    setTemplates(templateRows); setCohorts(cohortRows.filter((row) => row.academic_year));
    setWorkspaceLoaded(true);
  }

  useEffect(() => { refresh().catch((err) => setError(err.message)).finally(() => setBusy(false)); }, []);

  useEffect(() => {
    if (!assignment.batch_id) { setStudents([]); return; }
    api(`/teacher/students?batch_id=${assignment.batch_id}`).then(setStudents).catch((err) => setError(err.message));
  }, [assignment.batch_id]);

  const selectedQuestionRows = useMemo(() => selectedQuestions.map((id) => questions.find((row) => row.question_id === id)).filter(Boolean), [selectedQuestions, questions]);
  const completedStudents = useMemo(() => new Set(interviews.filter((row) => row.status === "COMPLETED" && row.student_id != null).map((row) => row.student_id)).size, [interviews]);

  function flash(message) { setNotice(message); setError(""); }
  function fail(err) { setError(err.message); setNotice(""); }
  function toggleQuestion(id) {
    setSelectedQuestions((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }
  function moveQuestion(index, delta) {
    const target = index + delta;
    if (target < 0 || target >= selectedQuestions.length) return;
    setSelectedQuestions((current) => { const next = [...current]; [next[index], next[target]] = [next[target], next[index]]; return next; });
  }

  async function saveQuestion(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const saved = await api(questionEditId ? `/questions/${questionEditId}` : "/questions", {
        method: questionEditId ? "PATCH" : "POST", body: JSON.stringify(questionForm),
      });
      setQuestions((rows) => questionEditId ? rows.map((row) => row.question_id === saved.question_id ? saved : row) : [saved, ...rows]);
      setQuestionForm(emptyQuestion); setQuestionEditId(null); flash("Question saved to your question bank.");
    } catch (err) { fail(err); }
    finally { setSaving(false); }
  }

  async function generateDrafts(event) {
    event?.preventDefault(); setDraftAttempted(true); setDraftBusy(true); setDraftMessage(""); setDrafts([]); setSelectedDrafts([]); setError("");
    try {
      const result = await api("/questions/generate", { method: "POST", body: JSON.stringify(draftPrompt) });
      setDrafts((result.questions || []).map((row) => ({ ...row, reference_answer: "" }))); setDraftMessage(result.message || "Review each draft, select the questions you want, then add them to this interview.");
    } catch (err) { fail(err); }
    finally { setDraftBusy(false); }
  }

  async function addDraftsToInterview() {
    const selected = drafts.filter((_, index) => selectedDrafts.includes(index));
    if (!selected.length) { setError("Select at least one reviewed draft question first."); return; }
    if (selected.some((draft) => !draft.question_text.trim())) { setError("Selected draft questions cannot be empty. Review and edit them before adding."); return; }
    if (selectedQuestions.length + selected.length > 50) { setError("An interview can contain at most 50 questions. Remove some questions before adding these drafts."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await api("/questions/commit-drafts", { method: "POST", body: JSON.stringify({ questions: selected }) });
      const savedRows = result.questions || [];
      setQuestions((rows) => [...savedRows.filter((saved) => !rows.some((row) => row.question_id === saved.question_id)), ...rows]);
      const addedIds = [...new Set(result.question_ids || [])];
      setSelectedQuestions((current) => [...current, ...addedIds.filter((id) => !current.includes(id))]);
      setQuestionRubrics((current) => ({ ...current, ...Object.fromEntries(addedIds.map((id) => [id, current[id] || ""])) }));
      setDrafts((current) => current.filter((_, index) => !selectedDrafts.includes(index)));
      setSelectedDrafts([]);
      flash(`${addedIds.length} selected question${addedIds.length === 1 ? "" : "s"} added to this interview and saved to your reusable question library (${result.created_count} new, ${result.reused_count} reused).`);
      goToTab("build");
    } catch (err) { fail(err); }
    finally { setSaving(false); }
  }

  async function removeQuestion(question) {
    if (question.created_by !== user.user_id) { setError("Shared default questions cannot be deleted."); return; }
    if (!await confirmAction({ title: "Delete question?", description: "This permanently removes the question. Questions used by a template or interview cannot be deleted; deactivate them instead.", confirmLabel: "Delete question", destructive: true })) return;
    try { await api(`/questions/${question.question_id}`, { method: "DELETE" }); setQuestions((rows) => rows.filter((row) => row.question_id !== question.question_id)); flash("Question deleted."); }
    catch (err) { fail(err); }
  }

  async function deactivateQuestion(question) {
    try {
      const saved = await api(`/questions/${question.question_id}`, { method: "PATCH", body: JSON.stringify({ is_active: false }) });
      setQuestions((rows) => rows.map((row) => row.question_id === saved.question_id ? saved : row)); flash("Question deactivated.");
    } catch (err) { fail(err); }
  }

  async function saveRubric(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    const criteria = rubricForm.criteria.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
      const match = line.match(/^(.*?)\s*\|\s*(\d+(?:\.\d+)?)\s*$/);
      return match ? { name: match[1].trim(), weight: Number(match[2]) } : line;
    });
    const payload = { rubric_name: rubricForm.rubric_name, rubric_type: rubricForm.rubric_type, maximum_score: Number(rubricForm.maximum_score), criteria_json: { criteria } };
    try {
      const saved = await api(rubricEditId ? `/rubrics/${rubricEditId}` : "/rubrics", { method: rubricEditId ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setRubrics((rows) => rubricEditId ? rows.map((row) => row.rubric_id === saved.rubric_id ? saved : row) : [...rows, saved]);
      setRubricForm(emptyRubric); setRubricEditId(null); flash("Reusable rubric saved.");
    } catch (err) { fail(err); }
    finally { setSaving(false); }
  }

  async function deleteRubric(rubric) {
    if (rubric.created_by !== user.user_id) return;
    if (!await confirmAction({ title: "Delete rubric?", description: "Rubrics used by a template or interview cannot be deleted.", confirmLabel: "Delete rubric", destructive: true })) return;
    try { await api(`/rubrics/${rubric.rubric_id}`, { method: "DELETE" }); setRubrics((rows) => rows.filter((row) => row.rubric_id !== rubric.rubric_id)); flash("Rubric deleted."); }
    catch (err) { fail(err); }
  }

  async function saveTemplate(event) {
    event?.preventDefault(); setError(""); setNotice("");
    if (!templateForm.title.trim()) { setError("Enter an interview title."); return; }
    if (selectedQuestions.length < 1 || selectedQuestions.length > 50) { setError("Select between 1 and 50 questions for this interview."); return; }
    setSaving(true);
    const payload = {
      ...templateForm,
      duration_minutes: templateForm.duration_minutes ? Number(templateForm.duration_minutes) : null,
      questions: selectedQuestionRows.map((row) => ({ question_id: row.question_id, rubric_id: questionRubrics[row.question_id] ? Number(questionRubrics[row.question_id]) : null })),
    };
    try {
      const saved = await api(templateEditId ? `/templates/${templateEditId}` : "/templates", { method: templateEditId ? "PATCH" : "POST", body: JSON.stringify(payload) });
      setTemplates((rows) => templateEditId ? rows.map((row) => row.template_id === saved.template_id ? saved : row) : [saved, ...rows]);
      setTemplateForm({ title: "", description: "", duration_minutes: "" }); setSelectedQuestions([]); setQuestionRubrics({}); setTemplateEditId(null);
      flash("Interview template saved. Assign it to a student or class group when ready.");
    } catch (err) { fail(err); }
    finally { setSaving(false); }
  }

  function editTemplate(template) {
    setTemplateEditId(template.template_id); setTemplateForm({ title: template.title, description: template.description || "", duration_minutes: template.duration_minutes || "" });
    setSelectedQuestions((template.questions || []).map((item) => item.question_id));
    setQuestionRubrics(Object.fromEntries((template.questions || []).map((item) => [item.question_id, item.rubric_id || ""])));
    goToTab("build"); window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function deleteTemplate(template) {
    if (!await confirmAction({ title: "Delete interview template?", description: "Templates with assigned interviews cannot be deleted.", confirmLabel: "Delete template", destructive: true })) return;
    try { await api(`/templates/${template.template_id}`, { method: "DELETE" }); setTemplates((rows) => rows.filter((row) => row.template_id !== template.template_id)); flash("Template deleted."); }
    catch (err) { fail(err); }
  }

  async function assignInterview(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    const payload = { template_id: Number(assignment.template_id), scheduled_at: assignment.scheduled_at || null };
    if (assignment.target === "group") payload.batch_id = Number(assignment.batch_id);
    else payload.student_id = Number(assignment.student_id);
    try {
      const result = await api("/interviews", { method: "POST", body: JSON.stringify(payload) });
      setAssignment((current) => ({ ...current, student_id: "", scheduled_at: "" }));
      flash(`Interview assigned to ${result.assigned_count} student${result.assigned_count === 1 ? "" : "s"}.`);
      await refresh(); goToTab("overview");
    } catch (err) { fail(err); }
    finally { setSaving(false); }
  }

  async function cancelInterview(interview) {
    if (!await confirmAction({ title: "Cancel scheduled interview?", description: `The scheduled interview for ${interview.student_name || "this student"} will be cancelled.`, confirmLabel: "Cancel interview", destructive: true })) return;
    try {
      await api(`/interviews/${interview.interview_id}/cancel`, { method: "POST" });
      flash("Scheduled interview cancelled."); await refresh();
    } catch (err) { fail(err); }
  }

  const searchControl = <div className="teacher-search"><label className="sr-only" htmlFor="teacher-workspace-search">Search students, interviews, or questions</label><Search className="teacher-search-icon" size={17} aria-hidden="true" /><input id="teacher-workspace-search" type="search" role="combobox" aria-autocomplete="list" aria-expanded={Boolean(searchTerm.trim())} aria-controls={searchTerm.trim() ? "teacher-search-results" : undefined} placeholder="Search students, interviews, or questions..." value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") setSearchTerm(""); }} />{searchTerm.trim() && <div className="teacher-search-results" id="teacher-search-results" role="listbox" aria-label="Workspace search results">{searchResults.length ? searchResults.map((result) => <button key={`${result.kind}-${result.id}`} type="button" role="option" aria-selected="false" onClick={() => openSearchResult(result)}><span className="teacher-search-result-icon">{result.kind === "session" ? <FileBarChart2 size={16} /> : result.kind === "template" ? <ClipboardList size={16} /> : <BookOpen size={16} />}</span><span><strong>{result.title}</strong><small>{result.detail}</small></span></button>) : <p>No matching interviews, templates, or questions.</p>}</div>}</div>;

  if (busy) return <TeacherFrame user={user} activeItem={activeItem} onNavigate={navigateWorkspace}><div className="teacher-loading-panel"><span className="spinner" />Loading teacher workspace</div></TeacherFrame>;
  if (!workspaceLoaded && error) return <TeacherFrame user={user} activeItem={activeItem} onNavigate={navigateWorkspace}><section className="teacher-load-error" role="alert"><span className="teacher-load-error-icon" aria-hidden="true">!</span><h1>We couldn’t load your workspace</h1><p>Check your connection and try again to load your interviews, analytics, and question resources.</p><button className="button teacher-button-primary" onClick={retryRefresh}>Try again</button></section></TeacherFrame>;

  return <TeacherFrame user={user} activeItem={activeItem} onNavigate={navigateWorkspace} search={searchControl}>
    {tab === "overview" ? <section className="teacher-hero"><div className="teacher-hero-copy"><div className="eyebrow">TEACHER WORKSPACE</div><h1>Welcome, {user.full_name.split(" ")[0]}.</h1><p>Create interview sets, assign practice, and review student results — all in one place.</p><div className="teacher-hero-actions"><button className="button teacher-button-primary" onClick={() => goToTab("build")}><FilePlus2 size={16} aria-hidden="true" />Create interview<ArrowRight size={15} aria-hidden="true" /></button><button className="button teacher-button-outline" onClick={() => goToTab("questions")}><BookOpen size={16} aria-hidden="true" />Question bank</button></div></div><div className="teacher-hero-metrics" aria-label="Teacher activity summary"><div><span><Users size={16} /></span><small>Students assigned</small><strong>{analytics?.students_assigned ?? "—"}</strong></div><div><span><CheckCircle2 size={16} /></span><small>Completed interviews</small><strong>{analytics?.completed_interviews ?? "—"}</strong></div><div><span><FileBarChart2 size={16} /></span><small>Reports to review</small><strong>{analytics?.pending_reviews ?? "—"}</strong></div></div></section> : <section className="teacher-page-heading"><div className="eyebrow">TEACHER WORKSPACE</div><h1>{tab === "build" ? (templateEditId ? "Edit interview template" : "Create an interview") : tab === "questions" ? "Question bank" : "Rubrics"}</h1><p>{tab === "build" ? "Choose questions, add scoring rubrics, and assign practice." : tab === "questions" ? "Manage the questions available to your interview templates." : "Build reusable scoring criteria for your interview questions."}</p></section>}
    {error && <div className="alert alert-error teacher-alert" role="alert"><span>{error}</span><button className="button button-outline button-small" onClick={retryRefresh}>Retry</button></div>}{notice && <div className="alert alert-info teacher-alert" role="status">{notice}</div>}

    {tab === "overview" && <>
      <section className="teacher-stats-grid" aria-label="Teacher interview statistics"><article className="teacher-metric-card teacher-metric-primary"><span className="teacher-metric-icon">♧</span><span className="teacher-metric-label">Total interviews</span><strong>{analytics?.interview_count ?? "—"}</strong><small>Created and assigned by you</small></article><article className="teacher-metric-card"><span className="teacher-metric-icon mint">▦</span><span className="teacher-metric-label">Active assignments</span><strong>{analytics?.active_interviews ?? "—"}</strong><small>Scheduled or in progress</small></article><article className="teacher-metric-card"><span className="teacher-metric-icon blue">⌂</span><span className="teacher-metric-label">Completed students</span><strong>{analytics ? completedStudents : "—"}<span className="teacher-metric-total"> / {analytics?.students_assigned ?? "—"} assigned</span></strong><small>Average score {analytics?.average_score != null ? `${analytics.average_score}/10` : "—"}</small></article><article className="teacher-metric-card"><span className="teacher-metric-icon violet">▤</span><span className="teacher-metric-label">Pending teacher review</span><strong>{analytics?.pending_reviews ?? "—"}</strong><small>Reports awaiting review</small></article></section>
      <section id="teacher-sessions" className="list-section teacher-surface teacher-session-section"><div className="section-heading"><div><div className="eyebrow">INTERVIEW MANAGEMENT</div><h2>Assigned student sessions</h2></div><div className="teacher-action-row"><span className="count-pill">{interviews.length} total</span><button className="button teacher-button-primary button-small" onClick={() => goToTab("build")}>＋ Create Interview</button></div></div>
        {interviews.length ? <div className="interview-list">{interviews.map((row) => <article className="interview-card teacher-session-card" id={`teacher-interview-${row.interview_id}`} key={row.interview_id}><div className="interview-symbol">{row.status === "COMPLETED" ? "✓" : "Q"}</div><div className="interview-card-copy"><h3>{row.template_title || "Interview practice"}</h3><p>{row.student_name || "Student"}<span className="dot-separator">·</span>{dateLabel(row.scheduled_at)}{row.final_score != null ? <><span className="dot-separator">·</span>Score {row.final_score}</> : null}</p></div><span className={`status-pill status-${row.status.toLowerCase()}`}>{row.status.replaceAll("_", " ").toLowerCase()}</span>{row.status === "COMPLETED" && <button className="button button-outline button-small" onClick={() => navigate(`/interviews/${row.interview_id}/report`)}>Results & review →</button>}{row.status === "SCHEDULED" && <button className="button button-quiet button-small" onClick={() => cancelInterview(row)}>Cancel</button>}</article>)}</div> : <div className="empty-state teacher-empty-state"><div className="teacher-empty-illustration" aria-hidden="true"><span>▤</span><b>＋</b></div><h3>No interview assignments yet</h3><p>Create a question set and template, then assign it to a student or configured class group.</p><button className="button teacher-button-primary button-small" onClick={() => goToTab("build")}>Start an interview <span aria-hidden="true">→</span></button></div>}
      </section>
      <section className="list-section teacher-surface teacher-template-section"><div className="section-heading"><div><div className="eyebrow">SAVED INTERVIEW SETS</div><h2>Your templates</h2></div><span className="count-pill">{templates.length} templates</span></div>{templates.length ? <div className="teacher-template-grid">{templates.map((template, index) => <article className="teacher-template-card" id={`teacher-template-${template.template_id}`} key={template.template_id}><div className={`teacher-template-icon tone-${index % 4}`} aria-hidden="true">{(template.questions?.[0]?.question_type || "Q").slice(0, 1).toUpperCase()}</div><div className="teacher-template-copy"><button className="teacher-template-title" onClick={() => editTemplate(template)}>{template.title}</button><span>{template.questions?.[0]?.question_type || "Interview"}<i />{template.questions?.length || 0} questions</span></div><div className="teacher-template-actions"><button className="teacher-template-open" aria-label={`Assign ${template.title}`} title="Assign" onClick={() => { setAssignment((current) => ({ ...current, template_id: String(template.template_id) })); goToTab("build"); }}>＋</button><button className="teacher-template-open" aria-label={`Edit ${template.title}`} title="Edit" onClick={() => editTemplate(template)}>↗</button><button className="teacher-template-delete" aria-label={`Delete ${template.title}`} title="Delete" onClick={() => deleteTemplate(template)}>×</button></div></article>)}</div> : <div className="empty-state compact-empty teacher-template-empty"><h3>No templates saved</h3><p>Build a template from your question bank to create an assignable interview.</p></div>}</section>
    </>}

    {tab === "build" && <div className="teacher-work-grid">
      <section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">STEP 1 · INTERVIEW CONFIGURATION</div><h2>{templateEditId ? "Edit template" : "Build an interview template"}</h2></div></div><div className="form-stack"><label className="field"><span>Interview title</span><input required maxLength="150" value={templateForm.title} onChange={(e) => setTemplateForm((x) => ({ ...x, title: e.target.value }))} placeholder="e.g. Technical and HR practice" /></label><label className="field"><span>Description or instructions <em>Optional</em></span><textarea rows="3" maxLength="5000" value={templateForm.description} onChange={(e) => setTemplateForm((x) => ({ ...x, description: e.target.value }))} /></label><label className="field"><span>Time limit in minutes <em>Optional</em></span><input type="number" min="1" max="600" value={templateForm.duration_minutes} onChange={(e) => setTemplateForm((x) => ({ ...x, duration_minutes: e.target.value }))} /></label>
        <div className="field"><span>Select questions and rubrics ({selectedQuestions.length} selected)</span>{questions.filter((q) => q.is_active).length ? <div className="teacher-question-picker">{questions.filter((q) => q.is_active).map((question) => <div className="teacher-picker-row" key={question.question_id}><label><input type="checkbox" checked={selectedQuestions.includes(question.question_id)} onChange={() => toggleQuestion(question.question_id)} /><span><strong>{question.question_text}</strong><small>{question.question_type} · {question.difficulty}</small></span></label>{selectedQuestions.includes(question.question_id) && <select aria-label={`Rubric for ${question.question_text}`} value={questionRubrics[question.question_id] || ""} onChange={(e) => setQuestionRubrics((x) => ({ ...x, [question.question_id]: e.target.value }))}><option value="">No rubric</option>{rubrics.map((rubric) => <option key={rubric.rubric_id} value={rubric.rubric_id}>{rubric.rubric_name}</option>)}</select>}</div>)}</div> : <p className="muted small-copy">Add questions in Question bank before building a template.</p>}</div>
        <div className="teacher-divider" /><h3>Generate interview questions</h3><p className="muted small-copy">Drafts stay out of the interview until you review, select, and add them. Selected drafts are saved to your reusable question library automatically.</p>
        <div className="form-stack"><label className="field"><span>Topic</span><input required maxLength="200" value={draftPrompt.topic} onChange={(e) => setDraftPrompt((x) => ({ ...x, topic: e.target.value }))} placeholder="e.g. Database normalization" /></label><div className="field-row"><label className="field"><span>Question type</span><select value={draftPrompt.question_type} onChange={(e) => setDraftPrompt((x) => ({ ...x, question_type: e.target.value }))}>{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><label className="field"><span>Difficulty</span><select value={draftPrompt.difficulty} onChange={(e) => setDraftPrompt((x) => ({ ...x, difficulty: e.target.value }))}>{["easy", "medium", "hard"].map((level) => <option key={level}>{level}</option>)}</select></label></div><button type="button" className="button button-outline" disabled={draftBusy || !draftPrompt.topic.trim()} onClick={() => generateDrafts()}>{draftBusy ? "Generating draft questions…" : "Generate draft questions"}</button></div>
        {draftBusy && <div className="loading-screen" aria-live="polite"><span className="spinner" />Generating question drafts…</div>}
        {draftMessage && <p className="muted small-copy" role="status">{draftMessage}</p>}
        {drafts.length > 0 ? <><div className="teacher-draft-list">{drafts.map((draft, index) => <article className="teacher-draft" key={`${draft.question_text}-${index}`}><label className="teacher-draft-select"><input type="checkbox" checked={selectedDrafts.includes(index)} onChange={(e) => setSelectedDrafts((current) => e.target.checked ? [...current, index] : current.filter((item) => item !== index))} /><span>Select for this interview</span></label><label className="field"><span>Review or edit question {index + 1}</span><textarea rows="3" maxLength="5000" value={draft.question_text} onChange={(e) => setDrafts((rows) => rows.map((item, i) => i === index ? { ...item, question_text: e.target.value } : item))} /></label>{draft.expected_key_points && <small>Expected concepts: {draft.expected_key_points}</small>}<button className="button button-quiet button-small" type="button" onClick={() => { setDrafts((rows) => rows.filter((_, i) => i !== index)); setSelectedDrafts((rows) => rows.filter((i) => i !== index).map((i) => i > index ? i - 1 : i)); }}>Remove draft</button></article>)}</div><button className="button button-primary" type="button" disabled={saving || selectedDrafts.length === 0} onClick={addDraftsToInterview}>{saving ? "Adding selected questions…" : `Add ${selectedDrafts.length || "selected"} draft${selectedDrafts.length === 1 ? "" : "s"} to interview`}</button></> : !draftBusy && draftAttempted && <div className="empty-state compact-empty"><h3>No draft questions to select</h3></div>}
        {selectedQuestionRows.length > 0 && <div className="selected-question-order"><strong>Interview questions · select to remove, use arrows to reorder</strong>{selectedQuestionRows.map((question, index) => <div key={question.question_id}><label className="selected-template-question"><input type="checkbox" checked={selectedQuestions.includes(question.question_id)} onChange={() => toggleQuestion(question.question_id)} /><span>{index + 1}. {question.question_text}</span></label><button type="button" className="text-button" onClick={() => moveQuestion(index, -1)} aria-label="Move up">↑</button><button type="button" className="text-button" onClick={() => moveQuestion(index, 1)} aria-label="Move down">↓</button></div>)}</div>}
        <button type="button" className="button button-primary" disabled={saving || selectedQuestions.length === 0} onClick={() => saveTemplate()}>{saving ? "Saving…" : templateEditId ? "Update template" : "Save interview template"}</button>{templateEditId && <button type="button" className="button button-quiet" onClick={() => { setTemplateEditId(null); setTemplateForm({ title: "", description: "", duration_minutes: "" }); setSelectedQuestions([]); setQuestionRubrics({}); }}>Cancel editing</button>}
      </div></section>
      <section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">STEP 2 · ASSIGN PRACTICE</div><h2>Assign a saved template</h2></div></div>{templates.length ? <form className="form-stack" onSubmit={assignInterview}><label className="field"><span>Interview template</span><select required value={assignment.template_id} onChange={(e) => setAssignment((x) => ({ ...x, template_id: e.target.value }))}><option value="">Choose template</option>{templates.map((template) => <option key={template.template_id} value={template.template_id}>{template.title}</option>)}</select></label><label className="field"><span>Assign to</span><select value={assignment.target} onChange={(e) => setAssignment((x) => ({ ...x, target: e.target.value, student_id: "" }))}><option value="group">All students in a class group</option><option value="student">One student</option></select></label><label className="field"><span>Course · semester · year</span><select required value={assignment.batch_id} onChange={(e) => setAssignment((x) => ({ ...x, batch_id: e.target.value, student_id: "" }))}><option value="">Choose class group</option>{cohorts.map((cohort) => <option key={cohort.batch_id} value={cohort.batch_id}>{cohort.course_name || cohort.course_id} · {cohort.semester} · {cohort.academic_year}</option>)}</select></label>{assignment.target === "student" && <label className="field"><span>Active student</span><select required value={assignment.student_id} onChange={(e) => setAssignment((x) => ({ ...x, student_id: e.target.value }))}><option value="">Choose student</option>{students.map((student) => <option key={student.user_id} value={student.user_id}>{student.full_name}{student.roll_number ? ` · ${student.roll_number}` : ""} · {student.email} · {student.teacher_interview_count} assigned</option>)}</select></label>}<label className="field"><span>Scheduled date and time <em>Optional</em></span><input type="datetime-local" value={assignment.scheduled_at} onChange={(e) => setAssignment((x) => ({ ...x, scheduled_at: e.target.value }))} /></label>{assignment.target === "group" && assignment.batch_id && <p className="muted small-copy">The selected group has {students.length} active students. One interview session will be created for each.</p>}<button className="button button-primary" disabled={saving || !assignment.template_id || !assignment.batch_id || (assignment.target === "student" && !assignment.student_id)}>{saving ? "Assigning…" : "Assign interview"}</button></form> : <div className="empty-state compact-empty"><h3>Save a template first</h3><p>Select questions and rubrics above, then assign the template here.</p></div>}</section>
    </div>}

    {tab === "questions" && <div className="teacher-work-grid"><section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">QUESTION AUTHORING</div><h2>{questionEditId ? "Edit question" : "Add a question"}</h2></div></div><form className="form-stack" onSubmit={saveQuestion}><label className="field"><span>Question text</span><textarea required rows="4" maxLength="5000" value={questionForm.question_text} onChange={(e) => setQuestionForm((x) => ({ ...x, question_text: e.target.value }))} /></label><div className="field-row"><label className="field"><span>Question type</span><select value={questionForm.question_type} onChange={(e) => setQuestionForm((x) => ({ ...x, question_type: e.target.value }))}>{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><label className="field"><span>Difficulty</span><select value={questionForm.difficulty} onChange={(e) => setQuestionForm((x) => ({ ...x, difficulty: e.target.value }))}>{["easy", "medium", "hard"].map((level) => <option key={level}>{level}</option>)}</select></label></div><label className="field"><span>Topics <em>Optional · comma separated</em></span><input maxLength="1000" value={questionForm.topics} onChange={(e) => setQuestionForm((x) => ({ ...x, topics: e.target.value }))} /></label><label className="field"><span>Expected key points <em>Optional</em></span><textarea rows="3" maxLength="5000" value={questionForm.expected_key_points} onChange={(e) => setQuestionForm((x) => ({ ...x, expected_key_points: e.target.value }))} /></label><label className="field"><span>Reference answer <em>Optional</em></span><textarea rows="3" maxLength="10000" value={questionForm.reference_answer} onChange={(e) => setQuestionForm((x) => ({ ...x, reference_answer: e.target.value }))} /></label><button className="button button-primary" disabled={saving}>{questionEditId ? "Save question" : "Add to question bank"}</button>{questionEditId && <button type="button" className="button button-quiet" onClick={() => { setQuestionEditId(null); setQuestionForm(emptyQuestion); }}>Cancel editing</button>}</form>
      <div className="teacher-divider" /><p className="muted small-copy">Use Create interview to generate reviewed draft questions as selectable options for a template.</p></section>
      <section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">REUSABLE LIBRARY</div><h2>Available questions</h2></div><span className="count-pill">{questions.length}</span></div>{questions.length ? <div className="interview-list">{questions.map((question) => <article className="teacher-library-row" id={`teacher-question-${question.question_id}`} key={question.question_id}><div className="teacher-library-copy"><strong>{question.question_text}</strong><small>{question.question_type} · {question.difficulty}{question.topics?.length ? ` · ${question.topics.join(", ")}` : ""}{!question.is_active ? " · inactive" : question.created_by === user.user_id ? " · yours" : " · shared"}</small></div>{question.created_by === user.user_id && <><button className="button button-outline button-small" onClick={() => { setQuestionEditId(question.question_id); setQuestionForm({ ...question, topics: (question.topics || []).join(", "), expected_key_points: question.expected_key_points || "", reference_answer: question.reference_answer || "" }); }}>Edit</button>{question.is_active ? <button className="button button-quiet button-small" onClick={() => deactivateQuestion(question)}>Deactivate</button> : <button className="button button-quiet button-small" onClick={async () => { try { const row = await api(`/questions/${question.question_id}`, { method: "PATCH", body: JSON.stringify({ is_active: true }) }); setQuestions((rows) => rows.map((item) => item.question_id === row.question_id ? row : item)); } catch (err) { fail(err); } }}>Reactivate</button>}<button className="button button-quiet button-small" onClick={() => removeQuestion(question)}>Delete</button></>}</article>)}</div> : <div className="empty-state compact-empty"><h3>Your question bank is empty</h3><p>Create a question manually or generate local AI drafts.</p></div>}</section></div>}

    {tab === "rubrics" && <div className="teacher-work-grid"><section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">SCORING CRITERIA</div><h2>{rubricEditId ? "Edit reusable rubric" : "Create a reusable rubric"}</h2></div></div><form className="form-stack" onSubmit={saveRubric}><label className="field"><span>Rubric name</span><input required maxLength="100" value={rubricForm.rubric_name} onChange={(e) => setRubricForm((x) => ({ ...x, rubric_name: e.target.value }))} /></label><div className="field-row"><label className="field"><span>Rubric type</span><select value={rubricForm.rubric_type} onChange={(e) => setRubricForm((x) => ({ ...x, rubric_type: e.target.value }))}>{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label><label className="field"><span>Maximum score</span><input type="number" min="1" max="100" required value={rubricForm.maximum_score} onChange={(e) => setRubricForm((x) => ({ ...x, maximum_score: e.target.value }))} /></label></div><label className="field"><span>Criteria <em>One per line</em></span><textarea required rows="6" value={rubricForm.criteria} onChange={(e) => setRubricForm((x) => ({ ...x, criteria: e.target.value }))} /></label><button className="button button-primary" disabled={saving}>{rubricEditId ? "Save rubric" : "Create rubric"}</button>{rubricEditId && <button type="button" className="button button-quiet" onClick={() => { setRubricEditId(null); setRubricForm(emptyRubric); }}>Cancel editing</button>}</form></section>
      <section className="teacher-panel"><div className="section-heading"><div><div className="eyebrow">RUBRIC LIBRARY</div><h2>Rubrics you can reuse</h2></div><span className="count-pill">{rubrics.length}</span></div>{rubrics.length ? <div className="interview-list">{rubrics.map((rubric) => <article className="teacher-library-row" key={rubric.rubric_id}><div className="teacher-library-copy"><strong>{rubric.rubric_name}</strong><small>{rubric.rubric_type} · maximum {rubric.maximum_score}<br />{(rubric.criteria_json?.criteria || []).map((item) => typeof item === "string" ? item : `${item.name}${item.weight == null ? "" : ` (${item.weight}%)`}`).join(" · ")}</small></div>{rubric.created_by === user.user_id && <><button className="button button-outline button-small" onClick={() => { setRubricEditId(rubric.rubric_id); setRubricForm({ rubric_name: rubric.rubric_name, rubric_type: rubric.rubric_type, maximum_score: rubric.maximum_score, criteria: (rubric.criteria_json?.criteria || []).map((item) => typeof item === "string" ? item : `${item.name}${item.weight == null ? "" : ` | ${item.weight}`}`).join("\n") }); }}>Edit</button><button className="button button-quiet button-small" onClick={() => deleteRubric(rubric)}>Delete</button></>}</article>)}</div> : <div className="empty-state compact-empty"><h3>No rubrics available</h3><p>Create a rubric to evaluate answers consistently.</p></div>}</section></div>}
    <footer className="page-footer"><span>QueMe · Teacher workspace</span><span>AI feedback supports learning; it does not make placement decisions.</span></footer>
  </TeacherFrame>;
}

export default TeacherDashboard;
