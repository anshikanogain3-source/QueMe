import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, ArrowRight, AudioLines, BarChart3, BookOpen, BriefcaseBusiness, Check, ChevronDown, ClipboardCheck, Clock3, Eye, EyeOff, FileBarChart2, FileText, Headphones, House, LogOut, Menu, Play, Settings2, ShieldCheck, Users, Video, VideoOff, X } from "lucide-react";
import { api } from "./api.js";
import { useAuth } from "./auth.jsx";
import TeacherDashboard from "./TeacherDashboard.jsx";
import { Brand, BrandMark } from "./Brand.jsx";
import { StudentWorkspace } from "./student/StudentWorkspace.jsx";
import { StudentOverview } from "./student/StudentOverview.jsx";
import { PracticeInterviews } from "./student/PracticeInterviews.jsx";
import { RapidFirePractice } from "./student/RapidFirePractice.jsx";
import { MyProgress } from "./student/MyProgress.jsx";
import { StudentFeedback } from "./student/StudentFeedback.jsx";
import { AuthenticatedAudio } from "./student/AuthenticatedAudio.jsx";

// Modular Teacher Pages
import { TeacherOverview } from "./teacher/TeacherOverview.jsx";
import { TeacherStudents } from "./teacher/TeacherStudents.jsx";
import { TeacherInterviews } from "./teacher/TeacherInterviews.jsx";
import { TeacherEvaluations } from "./teacher/TeacherEvaluations.jsx";
import { TeacherQuestionBank } from "./teacher/TeacherQuestionBank.jsx";
import { TeacherRubrics } from "./teacher/TeacherRubrics.jsx";
import { TeacherReports } from "./teacher/TeacherReports.jsx";

// Modular Admin Pages
import { AdminOverview } from "./admin/AdminOverview.jsx";
import { AdminUsers } from "./admin/AdminUsers.jsx";
import { AdminReports } from "./admin/AdminReports.jsx";
import { AdminAnalytics } from "./admin/AdminAnalytics.jsx";
import { AdminSettings } from "./admin/AdminSettings.jsx";

function TopBar({ user }) {
  const { logout } = useAuth();
  return (
    <header className="topbar">
      <Brand />
      <div className="topbar-right">
        <span className="topbar-user"><span className="avatar">{user?.full_name?.[0]?.toUpperCase() || "Q"}</span><span className="topbar-user-name">{user?.full_name}</span></span>
        <button className="button button-quiet button-small" onClick={logout}><LogOut size={16} aria-hidden="true" /><span>Sign out</span></button>
      </div>
    </header>
  );
}

function ReportWorkspace({ user, children }) {
  const { logout } = useAuth();
  if (user.role === "student") {
    return (
      <StudentWorkspace user={user} active="feedback" pageTitle="Interview Report" pageSubtitle="Assessment Feedback">
        {children}
      </StudentWorkspace>
    );
  }
  return (
    <div className="admin-app report-app-shell">
      <aside className="admin-sidebar">
        <Brand to="/dashboard" className="admin-brand" />
        <nav className="admin-side-nav" aria-label="Report navigation">
          <Link to="/dashboard" className="admin-side-link"><House size={17} />Dashboard</Link>
          <span className="admin-side-link active" aria-current="page"><FileBarChart2 size={17} />Interview report</span>
        </nav>
        <button className="admin-signout" type="button" onClick={logout}><LogOut size={16} />Sign out</button>
      </aside>
      <div className="admin-content">
        <header className="admin-topbar"><div><span className="admin-topbar-label">ASSESSMENT</span><h2>Interview report</h2></div><span className="admin-profile"><span className="avatar">{user.full_name?.[0]?.toUpperCase() || "Q"}</span><span><strong>{user.full_name}</strong><small>{user.role === "admin" ? "Administrator" : "Teacher"}</small></span></span></header>
        <main className="report-role-main">{children}</main>
      </div>
    </div>
  );
}

function Loading({ label = "Loading QueMe" }) {
  return <div className="loading-screen"><span className="spinner" />{label}</div>;
}

function Protected({ children, roles }) {
  const { ready, user } = useAuth();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

function AuthLayout({ eyebrow, title, description, children, footer }) {
  return (
    <main className="auth-page">
      <aside className="auth-aside">
        <Brand />
        <div className="auth-aside-copy">
          <div className="eyebrow eyebrow-light">CAMPUS PLACEMENT PRACTICE</div>
          <h1>Show up ready<br />for what’s next.</h1>
          <p>A quiet place to practise, find your rhythm, and build confidence one answer at a time.</p>
        </div>
        <div className="auth-orbit orbit-one" /><div className="auth-orbit orbit-two" />
        <div className="auth-aside-note">Practice is progress. Keep going.</div>
      </aside>
      <section className="auth-main">
        <div className="auth-mobile-brand"><Brand /></div>
        <div className="auth-form-wrap">
          <div className="eyebrow">{eyebrow}</div>
          <h2>{title}</h2>
          <p className="auth-description">{description}</p>
          {children}
          <div className="auth-footer">{footer}</div>
        </div>
        <span className="auth-version">QueMe · Campus Training</span>
      </section>
    </main>
  );
}

function HomePage() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <main className="home-page">
      <header className="home-nav">
        <Brand />
        <button className="home-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="home-navigation" onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? "Close" : "Menu"}{menuOpen ? <X size={17} aria-hidden="true" /> : <Menu size={17} aria-hidden="true" />}</button>
        <nav id="home-navigation" className={`home-nav-links${menuOpen ? " is-open" : ""}`} aria-label="Main navigation">
          <Link to="/" onClick={() => setMenuOpen(false)}>Home</Link>
          <a href="#how-it-works" onClick={() => setMenuOpen(false)}>How It Works</a>
          <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
          <a href="#about" onClick={() => setMenuOpen(false)}>About</a>
          <Link className="home-signin" to="/login" onClick={() => setMenuOpen(false)}>Login</Link><Link className="button button-primary button-small" to="/register" onClick={() => setMenuOpen(false)}>Get Started <span aria-hidden="true">→</span></Link>
        </nav>
      </header>
      <section className="home-hero">
        <div className="home-copy">
          <div className="eyebrow">CAMPUS INTERVIEW PRACTICE & ASSESSMENT</div>
          <h1>Build interview readiness, one answer at a time.</h1>
          <p className="home-lede">A connected practice and assessment workspace for students, teachers, and placement teams.</p>
          <p>Students practise assigned interviews and review feedback. Teachers build question sets, assess answers, and follow student progress.</p>
          <div className="home-actions">
            <Link className="button button-primary" to="/register">Start Practicing <span aria-hidden="true">→</span></Link>
            <a className="button button-outline" href="#how-it-works">Explore How It Works <span aria-hidden="true">↓</span></a>
          </div>
          <div className="home-reassurance"><span aria-hidden="true">✳</span> Practice at your pace. Progress on your terms.</div>
        </div>
        <div className="home-visual" role="img" aria-label="QueMe interview preview with an interview question and response controls">
          <div className="home-orbit home-orbit-one" /><div className="home-orbit home-orbit-two" />
          <div className="home-practice-card home-interview-preview"><div className="home-card-top"><span className="home-card-dot" /><span>INTERVIEW PREVIEW</span><span className="home-card-menu">···</span></div><div className="home-progress-meta"><span>Practice session</span><span>Question in progress</span></div><div className="home-progress-track"><i /></div><div className="home-interviewer"><span className="home-interviewer-avatar"><BrandMark /></span><span><b>AI voice interviewer</b><small>Take your time</small></span><span className="home-audio-indicator" aria-hidden="true"><i /><i /><i /><i /></span></div><div className="home-card-label">YOUR QUESTION</div><div className="home-card-question">Tell me about a challenge you’re proud of overcoming.</div><div className="home-recording"><span className="home-record-dot" /> Answer controls <span className="home-mic-icon" aria-hidden="true"><Headphones size={14} /></span></div><div className="home-card-footer"><span>Recorded answers can be reviewed later</span><ArrowRight size={16} className="home-card-arrow" aria-hidden="true" /></div></div>
          <div className="home-note home-note-top">A little practice<br />goes a long way <span>✳</span></div>
          <div className="home-note home-note-bottom"><span>✓</span> Practice at your own pace</div>
        </div>
      </section>
      <section id="how-it-works" className="home-section home-how"><div className="home-section-heading"><div className="eyebrow">A SIMPLE WAY TO GET STARTED</div><h2>Practice, one question at a time.</h2><p>QueMe guides you through your assigned interview and gives you a place to reflect on each answer.</p></div>
        <div className="home-pillars"><article><span>01</span><div><h3>Open your interview</h3><p>Choose from the practice interviews your teacher has assigned to you.</p></div></article><article><span>02</span><div><h3>Record your answers</h3><p>Listen to each question and respond in your own words in a low-pressure space.</p></div></article><article><span>03</span><div><h3>Review and reflect</h3><p>Read your report, available transcript, and feedback. Some answers may be marked for teacher review.</p></div></article></div>
      </section>
      <section id="features" className="home-section home-features"><div className="home-section-heading"><div className="eyebrow">TOOLS FOR YOUR NEXT STEP</div><h2>Everything you need to practice with purpose.</h2></div>
        <div className="home-feature-grid"><article><span><BriefcaseBusiness size={18} /></span><h3>Guided interview sessions</h3><p>Work through questions assigned to your interview, with controls to repeat, skip, or finish.</p></article><article><span><Headphones size={18} /></span><h3>Recorded answers</h3><p>Save audio responses and revisit your recordings from a completed interview.</p></article><article><span><FileText size={18} /></span><h3>Transcripts when available</h3><p>Speech transcription adds a written record when the transcription service is available.</p></article><article><span><ClipboardCheck size={18} /></span><h3>Rubric-based feedback</h3><p>Review content and delivery scoring. Automated evaluation depends on service availability; teacher review remains part of the process.</p></article><article><span><BarChart3 size={18} /></span><h3>Reports you can revisit</h3><p>See completed sessions, answer details, feedback, and any teacher remarks in one place.</p></article><article><span><BookOpen size={18} /></span><h3>Questions built for practice</h3><p>Teachers can prepare reusable questions by topic, question type, and difficulty for assigned interviews.</p></article></div>
      </section>
      <section id="about" className="home-section home-about"><div className="home-about-copy"><div className="eyebrow eyebrow-light">A SHARED WORKSPACE FOR CAMPUS PLACEMENT</div><h2>Practice for students. Insight for teachers.</h2><p>Students build confidence through recorded practice and review. Teachers create consistent assessments, follow assigned interview outcomes, and add guidance where automated evaluation needs review.</p><Link className="button home-about-button" to="/register">Get started<ArrowRight size={15} /></Link></div>
        <div className="home-report-preview" role="img" aria-label="Illustrative QueMe report preview showing content and delivery feedback"><div className="home-report-top"><span>REPORT PREVIEW</span><span className="home-report-status">SAMPLE</span></div><h3>Your practice, reflected.</h3><p>Review notes from your interview session.</p><div className="home-report-row"><span>Answer content</span><b>Rubric feedback</b></div><div className="home-report-row"><span>Speaking delivery</span><b>Audio analysis</b></div><div className="home-report-foot"><span>Feedback supports learning</span><span>QueMe <BrandMark /></span></div></div>
      </section>
      <section className="home-final-cta"><div><div className="eyebrow">YOUR NEXT ANSWER STARTS HERE</div><h2>Ready to feel more prepared?</h2><p>Start with the practice interviews assigned to you.</p></div><Link className="button button-primary" to="/register">Start Practicing<span aria-hidden="true">→</span></Link></section>
      <footer className="home-footer"><Link to="/" className="home-footer-brand"><BrandMark />QueMe</Link><nav aria-label="Footer navigation"><a href="#how-it-works">How It Works</a><a href="#features">Features</a><a href="#about">About</a><Link to="/login">Login</Link></nav><span>AI feedback supports learning; it does not make placement decisions.</span><span>© {new Date().getFullYear()} QueMe</span></footer>
    </main>
  );
}

function LoginPage() {
  const { login, user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/dashboard" replace />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      if (err.code === "account_not_active") {
        navigate(`/pending?status=${encodeURIComponent(err.payload?.account_status || "PENDING")}`, { replace: true });
      } else setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="WELCOME BACK"
      title="Sign in to QueMe"
      description="Pick up where you left off and keep your practice moving."
      footer={<>New to QueMe? <Link to="/register">Create an account <span aria-hidden="true">↗</span></Link></>}
    >
      <form className="form-stack" onSubmit={submit}>
        {location.state?.notice && <div className="alert alert-info" role="status">{location.state.notice}</div>}
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label className="field"><span>Email address</span><input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@campus.edu" /></label>
        <label className="field"><span>Password</span><span className="password-field"><input type={showPassword ? "text" : "password"} autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" /><button type="button" className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>
        <div className="auth-inline-link"><Link to={`/forgot-password${email ? `?email=${encodeURIComponent(email)}` : ""}`}>Forgot password?</Link></div>
        <button className="button button-primary button-wide" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<span aria-hidden="true">→</span></button>
      </form>
      <div className="secure-note"><span>◇</span> Your practice space is private and secure.</div>
    </AuthLayout>
  );
}

function ForgotPasswordPage() {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState(searchParams.get("email") || "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
      setMessage(result.message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return <AuthLayout eyebrow="ACCOUNT RECOVERY" title="Reset your password" description="Enter your account email and we’ll send you a secure reset link." footer={<>Remembered it? <Link to="/login">Return to sign in <span aria-hidden="true">↗</span></Link></>}>
    <form className="form-stack" onSubmit={submit}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}
      <label className="field"><span>Email address</span><input type="email" autoComplete="email" required maxLength="150" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@campus.edu" /></label>
      <button className="button button-primary button-wide" disabled={busy}>{busy ? "Sending…" : "Send reset link"}<span aria-hidden="true">→</span></button>
    </form>
  </AuthLayout>;
}

function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }) });
      navigate("/login", { replace: true, state: { notice: "Your password has been reset. You can now sign in." } });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return <AuthLayout eyebrow="ACCOUNT RECOVERY" title="Choose a new password" description="Use at least 12 characters for your new password." footer={<>Need a new link? <Link to="/forgot-password">Request another reset link <span aria-hidden="true">↗</span></Link></>}>
    <form className="form-stack" onSubmit={submit}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {!token && <div className="alert alert-error" role="alert">This reset link is missing its token. Request a new link to continue.</div>}
      <label className="field"><span>New password</span><span className="password-field"><input type={showPassword ? "text" : "password"} autoComplete="new-password" required minLength="12" maxLength="72" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 12 characters" /><button type="button" className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span></label>
      <button className="button button-primary button-wide" disabled={busy || !token}>{busy ? "Updating…" : "Update password"}<span aria-hidden="true">→</span></button>
    </form>
  </AuthLayout>;
}

function RegisterPage() {
  const { register, user } = useAuth();
  const navigate = useNavigate();
  const [departments, setDepartments] = useState([]);
  const [batches, setBatches] = useState([]);
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "student", department_id: "", semester: "", academic_year: "", roll_number: "", employee_id: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([api("/admin/courses"), api("/admin/semesters")])
      .then(([departmentRows, batchRows]) => { setDepartments(departmentRows); setBatches(batchRows); })
      .catch((err) => setError(err.message));
  }, []);
  if (user) return <Navigate to="/dashboard" replace />;
  const matchingCohorts = batches.filter((row) => String(row.department_id) === form.department_id && row.semester === form.semester);
  const availableYears = [...new Set(matchingCohorts.map((row) => row.academic_year).filter(Boolean))].sort();

  function change(key, value) {
    setForm((current) => ({ ...current, [key]: value, ...(["department_id", "semester"].includes(key) ? { academic_year: "" } : {}) }));
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const payload = {
      full_name: form.full_name,
      email: form.email,
      password: form.password,
      role: form.role,
      course_id: Number(form.department_id),
      semester: form.semester,
      academic_year: form.academic_year,
      ...(form.role === "student" && form.roll_number ? { roll_number: form.roll_number } : {}),
      ...(form.role === "teacher" && form.employee_id ? { employee_id: form.employee_id } : {}),
    };
    try {
      await register(payload);
      navigate("/pending?status=PENDING", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      eyebrow="GET STARTED"
      title="Create your account"
      description="Join your campus practice space. An administrator will review your request."
      footer={<>Already have an account? <Link to="/login">Sign in <span aria-hidden="true">↗</span></Link></>}
    >
      <form className="form-stack form-scroll" onSubmit={submit}>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label className="field"><span>Full name</span><input autoComplete="name" maxLength="100" required value={form.full_name} onChange={(e) => change("full_name", e.target.value)} placeholder="Your name" /></label>
        <label className="field"><span>Email address</span><input type="email" autoComplete="email" required value={form.email} onChange={(e) => change("email", e.target.value)} placeholder="you@campus.edu" /></label>
        <label className="field"><span>I am registering as</span><select value={form.role} onChange={(e) => change("role", e.target.value)}><option value="student">Student</option><option value="teacher">Teacher</option></select></label>
        <div className="field-row">
          <label className="field"><span>Course</span><select required value={form.department_id} onChange={(e) => change("department_id", e.target.value)}><option value="">Select course</option>{departments.map((row) => <option key={row.course_id} value={row.course_id}>{row.course_name}</option>)}</select></label>
          <label className="field"><span>Semester</span><select required value={form.semester} onChange={(e) => change("semester", e.target.value)}><option value="">Select semester</option>{["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"].map((semester) => <option key={semester}>{semester}</option>)}</select></label>
        </div>
        <label className="field"><span>Academic year</span><select required disabled={!availableYears.length} value={form.academic_year} onChange={(e) => change("academic_year", e.target.value)}><option value="">{availableYears.length ? "Select academic year" : "No class group available; contact your administrator"}</option>{availableYears.map((year) => <option key={year}>{year}</option>)}</select></label>
        {form.role === "student" ? (
          <label className="field"><span>Roll number <em>Optional</em></span><input maxLength="30" value={form.roll_number} onChange={(e) => change("roll_number", e.target.value)} placeholder="Your campus roll number" /></label>
        ) : (
          <label className="field"><span>Employee ID <em>Optional</em></span><input maxLength="30" value={form.employee_id} onChange={(e) => change("employee_id", e.target.value)} placeholder="Your employee ID" /></label>
        )}
        <label className="field"><span>Password</span><span className="password-field"><input type={showPassword ? "text" : "password"} autoComplete="new-password" minLength="12" maxLength="72" required value={form.password} onChange={(e) => change("password", e.target.value)} placeholder="At least 12 characters" /><button type="button" className="password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></span><small>Use 12 or more characters.</small></label>
        <button className="button button-primary button-wide" disabled={busy}>{busy ? "Sending request…" : "Request an account"}<span aria-hidden="true">→</span></button>
      </form>
    </AuthLayout>
  );
}

function PendingPage() {
  const [search] = useSearchParams();
  const status = (search.get("status") || "PENDING").toUpperCase();
  const rejected = status === "REJECTED";
  return (
    <AuthLayout
      eyebrow="ACCOUNT STATUS"
      title={rejected ? "Please contact your campus admin" : "Your request is in review"}
      description={rejected ? "Your account request was not approved. Your campus administrator can explain the next steps." : "You’re all set for now. An administrator needs to activate your account before you can sign in."}
      footer={<>Already approved? <Link to="/login">Return to sign in <span aria-hidden="true">↗</span></Link></>}
    >
      <div className={`status-illustration ${rejected ? "status-rejected" : ""}`}><span>{rejected ? "!" : "✓"}</span></div>
      <Link className="button button-primary button-wide" to="/login">Back to sign in <span aria-hidden="true">→</span></Link>
      <p className="muted center-text small-copy">Approval is managed by your campus administrator.</p>
    </AuthLayout>
  );
}

function DashboardPage() {
  const { user } = useAuth();
  const location = useLocation();
  if (user.role === "student") {
    if (location.hash === "#interviews") return <Navigate to="/practice-interviews" replace />;
    if (location.hash === "#progress") return <Navigate to="/my-progress" replace />;
    if (location.hash === "#feedback") return <Navigate to="/feedback" replace />;
    return <StudentOverview user={user} />;
  }
  if (user.role === "teacher") {
    if (location.hash === "#build" || location.hash === "#sessions") return <Navigate to="/teacher/interviews" replace />;
    if (location.hash === "#questions") return <Navigate to="/teacher/question-bank" replace />;
    if (location.hash === "#rubrics") return <Navigate to="/teacher/rubrics" replace />;
    if (location.hash === "#reports") return <Navigate to="/teacher/reports" replace />;
    return <TeacherOverview user={user} />;
  }
  if (user.role === "admin") {
    if (location.hash === "#admin-users") return <Navigate to="/admin/users" replace />;
    if (location.hash === "#admin-reports") return <Navigate to="/admin/reports" replace />;
    if (location.hash === "#admin-settings") return <Navigate to="/admin/settings" replace />;
    return <AdminOverview user={user} />;
  }
  return <><TopBar user={user} /><UserDashboard user={user} /></>;
}

function UserDashboard({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  useEffect(() => {
    api("/interviews").then(setInterviews).catch((err) => setError(err.message)).finally(() => setBusy(false));
  }, []);
  const completed = interviews.filter((row) => row.status === "COMPLETED");
  const upcoming = interviews.filter((row) => row.status === "SCHEDULED" || row.status === "IN_PROGRESS");
  const isStudent = user.role === "student";

  return (
    <main className="app-shell">
      <section className="welcome-row">
        <div><div className="eyebrow">{isStudent ? "YOUR PRACTICE SPACE" : "TEACHER OVERVIEW"}</div><h1>{isStudent ? <>Good to see you, {user.full_name.split(" ")[0]}.</> : <>Welcome, {user.full_name.split(" ")[0]}.</>}</h1><p>{isStudent ? "Every interview is a chance to make the next answer clearer." : "Here’s a look at the interviews you’ve assigned."}</p></div>
        <div className="welcome-decoration"><div className="deco-ring" /><div className="deco-core">{isStudent ? "Q" : "↗"}</div></div>
      </section>
      <section className="stats-grid" aria-label="Interview summary">
        <div className="stat-card stat-highlight"><span className="stat-icon">◷</span><span className="stat-label">{isStudent ? "Ready to practise" : "Active assignments"}</span><strong>{upcoming.length.toString().padStart(2, "0")}</strong><span className="stat-caption">Scheduled or in progress</span></div>
        <div className="stat-card"><span className="stat-icon stat-icon-soft">✓</span><span className="stat-label">Completed</span><strong>{completed.length.toString().padStart(2, "0")}</strong><span className="stat-caption">Practice sessions finished</span></div>
        <div className="stat-card stat-note"><span className="stat-note-label">A small reminder</span><p>Take a breath. Give yourself a moment to think before you answer.</p><span className="note-flower">✳</span></div>
      </section>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      <section className="list-section">
        <div className="section-heading"><div><div className="eyebrow">{isStudent ? "YOUR SCHEDULE" : "ASSIGNED INTERVIEWS"}</div><h2>{isStudent ? "Interview practice" : "Student sessions"}</h2></div><span className="count-pill">{interviews.length} total</span></div>
        {busy ? <Loading label="Loading your interviews" /> : interviews.length === 0 ? (
          <div className="empty-state"><div className="empty-mark">Q</div><h3>{isStudent ? "Nothing scheduled yet" : "No interviews assigned yet"}</h3><p>{isStudent ? "Your teacher will add an interview here when one is ready." : "Interviews you assign to students will appear here."}</p></div>
        ) : (
          <div className="interview-list">
            {interviews.map((row) => <InterviewCard key={row.interview_id} interview={row} role={user.role} onOpen={() => navigate(`/interviews/${row.interview_id}`)} onReport={() => navigate(`/interviews/${row.interview_id}/report`)} />)}
          </div>
        )}
      </section>
      <footer className="page-footer"><span>QueMe · Practice at your pace</span><span>AI feedback supports learning; it does not make placement decisions.</span></footer>
    </main>
  );
}

function InterviewCard({ interview, role, onOpen, onReport }) {
  const status = interview.status.toLowerCase().replaceAll("_", " ");
  const date = interview.scheduled_at ? new Date(interview.scheduled_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Schedule not set";
  return (
    <article className="interview-card">
      <div className="interview-symbol">{interview.status === "COMPLETED" ? <Check size={18} /> : <BriefcaseBusiness size={18} />}</div>
      <div className="interview-card-copy"><h3>{interview.template_title || "Interview practice"}</h3><p>{role === "student" ? `Assigned by ${interview.teacher_name || "your teacher"}` : `For ${interview.student_name || "student"}`}<span className="dot-separator">·</span>{date}</p></div>
      <span className={`status-pill status-${interview.status.toLowerCase()}`}>{status}</span>
      {role === "student" && interview.status !== "CANCELLED" && <button className="button button-outline button-small" onClick={interview.status === "COMPLETED" ? onReport : onOpen}>{interview.status === "IN_PROGRESS" ? "Continue" : interview.status === "COMPLETED" ? "View report" : "View interview"}<span aria-hidden="true">→</span></button>}
      {role === "teacher" && interview.status === "COMPLETED" && <button className="button button-outline button-small" onClick={onReport}>Review report<span aria-hidden="true">→</span></button>}
    </article>
  );
}

function AdminDashboard({ user }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [users, setUsers] = useState([]);
  const [reports, setReports] = useState([]);
  const [courses, setCourses] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [cohortForm, setCohortForm] = useState({ course_id: "", semester: "", academic_year: "" });
  const [weights, setWeights] = useState({ content_weight: 0.7, delivery_weight: 0.3 });
  const [roleFilter, setRoleFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(true);
  const [savingWeights, setSavingWeights] = useState(false);
  async function refresh() {
    const [stats, accountRows, reportRows, scoreWeights, courseRows, cohortRows] = await Promise.all([
      api("/admin/analytics"), api("/admin/users"), api("/admin/reports"), api("/admin/settings"), api("/admin/courses"), api("/admin/semesters"),
    ]);
    setAnalytics(stats);
    setUsers(accountRows);
    setReports(reportRows);
    setWeights(scoreWeights);
    setCourses(courseRows);
    setCohorts(cohortRows);
    if (!cohortForm.course_id && courseRows.length) setCohortForm((current) => ({ ...current, course_id: String(courseRows[0].course_id) }));
  }
  useEffect(() => { refresh().catch((err) => setError(err.message)).finally(() => setBusy(false)); }, []);
  async function approve(userId, account_status) {
    try {
      await api(`/admin/users/${userId}/status`, { method: "POST", body: JSON.stringify({ account_status }) });
      setNotice(`Account ${account_status === "ACTIVE" ? "approved" : "rejected"}.`);
      await refresh();
    } catch (err) { setError(err.message); }
  }
  async function saveWeights(event) {
    event.preventDefault(); setSavingWeights(true); setError(""); setNotice("");
    try {
      const updated = await api("/admin/settings", { method: "PATCH", body: JSON.stringify({
        content_weight: Number(weights.content_weight), delivery_weight: Number(weights.delivery_weight),
      }) });
      setWeights(updated); setNotice("Scoring weights saved.");
    } catch (err) { setError(err.message); }
    finally { setSavingWeights(false); }
  }
  async function createCohort(event) {
    event.preventDefault(); setError(""); setNotice("");
    try {
      await api("/admin/semesters", { method: "POST", body: JSON.stringify(cohortForm) });
      setNotice("Class group created. Students and teachers can now register into it.");
      setCohortForm((current) => ({ ...current, semester: "", academic_year: "" }));
      const rows = await api("/admin/semesters"); setCohorts(rows);
    } catch (err) { setError(err.message); }
  }
  async function download(path, filename) {
    try {
      const blob = await api(path);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = objectUrl; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) { setError(err.message); }
  }
  const pending = users.filter((person) => person.account_status === "PENDING");
  const visibleUsers = users.filter((person) => (roleFilter === "all" || person.role === roleFilter)
    && (statusFilter === "all" || person.account_status === statusFilter));
  return (
    <div className="admin-app">
      <aside className="admin-sidebar">
        <Brand to="/dashboard" className="admin-brand" />
        <nav className="admin-side-nav" aria-label="Administration">
          <a href="#admin-overview" className="admin-side-link active"><House size={17} />Overview</a>
          <a href="#admin-users" className="admin-side-link"><Users size={17} />Accounts</a>
          <a href="#admin-reports" className="admin-side-link"><FileBarChart2 size={17} />Reports</a>
          <a href="#admin-settings" className="admin-side-link"><Settings2 size={17} />Settings</a>
        </nav>
        <button className="admin-signout" type="button" onClick={logout}><LogOut size={16} />Sign out</button>
      </aside>
      <div className="admin-content">
        <header className="admin-topbar"><div><span className="admin-topbar-label">ADMINISTRATION</span><h2>Campus overview</h2></div><span className="admin-profile"><span className="avatar">{user.full_name?.[0]?.toUpperCase() || "A"}</span><span><strong>{user.full_name}</strong><small>Administrator</small></span></span></header>
        <main className="app-shell">
      <section className="welcome-row" id="admin-overview"><div><div className="eyebrow">PLATFORM OVERVIEW</div><h1>Welcome, {user.full_name.split(" ")[0]}.</h1><p>Manage campus access, monitor interview activity, and review reports.</p></div><div className="report-actions"><button className="button button-primary button-small" onClick={() => download("/admin/reports.xlsx", "queme-reports.xlsx")}><FileText size={15} />Export all reports</button></div></section>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {notice && <div className="alert alert-info" role="status">{notice}</div>}
      {busy ? <Loading label="Loading campus activity" /> : <>
        <section className="admin-stats stats-grid">
          <div className="stat-card"><span className="stat-label">Interviews</span><strong>{analytics?.interview_count ?? 0}</strong><span className="stat-caption">{analytics?.completed_interviews ?? 0} completed</span></div>
          <div className="stat-card"><span className="stat-label">Average score</span><strong>{analytics?.average_score ?? "—"}</strong><span className="stat-caption">Across scored interviews</span></div>
          <div className="stat-card"><span className="stat-label">Active students</span><strong>{analytics?.active_students ?? 0}</strong><span className="stat-caption">{analytics?.active_teachers ?? 0} active teachers</span></div>
          <div className="stat-card"><span className="stat-label">Pending / review</span><strong>{analytics?.pending_accounts ?? 0}</strong><span className="stat-caption">Pending accounts · {analytics?.reports_needing_review ?? 0} reports need review</span></div>
        </section>
        <section className="list-section admin-section" id="admin-users"><div className="section-heading"><div><div className="eyebrow">ACCESS REQUESTS</div><h2>Pending accounts</h2></div><span className="count-pill">{pending.length} to review</span></div>
          {pending.length ? <div className="interview-list">{pending.map((person) => <article className="interview-card" key={person.user_id}><div className="avatar avatar-large">{person.full_name[0]?.toUpperCase()}</div><div className="interview-card-copy"><h3>{person.full_name}</h3><p>{person.email}<span className="dot-separator">·</span>{person.role}</p></div><button className="button button-outline button-small" onClick={() => approve(person.user_id, "REJECTED")}>Reject</button><button className="button button-primary button-small" onClick={() => approve(person.user_id, "ACTIVE")}>Approve</button></article>)}</div> : <div className="empty-state compact-empty"><h3>All caught up</h3><p>New student and teacher requests will show here.</p></div>}
        </section>
        <section className="list-section admin-section">
          <div className="section-heading"><div><div className="eyebrow">ACCOUNT MANAGEMENT</div><h2>Campus accounts</h2></div><span className="count-pill">{users.length} accounts</span></div>
          <div className="admin-filters"><label className="field"><span>Role</span><select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}><option value="all">All roles</option><option value="student">Students</option><option value="teacher">Teachers</option><option value="admin">Admins</option></select></label><label className="field"><span>Status</span><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="all">All statuses</option><option value="PENDING">Pending</option><option value="ACTIVE">Active</option><option value="REJECTED">Rejected</option></select></label></div>
          <div className="interview-list">{visibleUsers.map((person) => <article className="interview-card" key={person.user_id}><div className="avatar avatar-large">{person.full_name[0]?.toUpperCase()}</div><div className="interview-card-copy"><h3>{person.full_name}</h3><p>{person.email}<span className="dot-separator">·</span>{person.role}{person.course ? <><span className="dot-separator">·</span>{person.course} {person.semester}{person.academic_year ? ` · ${person.academic_year}` : ""}</> : null}</p></div><span className={`status-pill status-${person.account_status.toLowerCase()}`}>{person.account_status.toLowerCase()}</span>{person.role !== "admin" && person.account_status !== "ACTIVE" && <button className="button button-primary button-small" onClick={() => approve(person.user_id, "ACTIVE")}>Activate</button>}{person.role !== "admin" && person.account_status !== "REJECTED" && <button className="button button-outline button-small" onClick={() => approve(person.user_id, "REJECTED")}>Reject</button>}</article>)}{visibleUsers.length === 0 && <div className="empty-state compact-empty"><h3>No matching accounts</h3></div>}</div>
        </section>
        <section className="list-section admin-section" id="admin-reports"><div className="section-heading"><div><div className="eyebrow">REPORTS & EXPORTS</div><h2>Recent interview reports</h2></div><span className="count-pill">Latest {reports.length}</span></div>
          {reports.length ? <div className="interview-list">{reports.map((report) => <article className="interview-card" key={report.report_id}><div className="interview-symbol"><FileBarChart2 size={18} /></div><div className="interview-card-copy"><h3>{report.template_title || `Interview ${report.interview_id}`}</h3><p>{report.student_name || "Student"}<span className="dot-separator">·</span>Score {report.final_score ?? "Pending review"}<span className="dot-separator">·</span>{report.report_status?.replaceAll("_", " ")}</p></div><button className="button button-outline button-small" onClick={() => navigate(`/interviews/${report.interview_id}/report`)}>View</button><button className="button button-outline button-small" onClick={() => download(`/interviews/${report.interview_id}/report.pdf`, `queme-interview-${report.interview_id}.pdf`)}>PDF</button><button className="button button-outline button-small" onClick={() => download(`/interviews/${report.interview_id}/report.xlsx`, `queme-interview-${report.interview_id}.xlsx`)}>Excel</button></article>)}</div> : <div className="empty-state compact-empty"><h3>No reports yet</h3><p>Reports are created as interviews are completed.</p></div>}
        </section>
        <section className="list-section admin-section" id="admin-settings"><div className="section-heading"><div><div className="eyebrow">SCORING</div><h2>Score weights</h2></div></div><form className="admin-weights" onSubmit={saveWeights}><label className="field"><span>Content weight</span><input type="number" min="0" max="1" step="0.01" value={weights.content_weight} onChange={(e) => setWeights((current) => ({ ...current, content_weight: e.target.value }))} /></label><label className="field"><span>Delivery weight</span><input type="number" min="0" max="1" step="0.01" value={weights.delivery_weight} onChange={(e) => setWeights((current) => ({ ...current, delivery_weight: e.target.value }))} /></label><button className="button button-primary button-small" disabled={savingWeights}>{savingWeights ? "Saving…" : "Save weights"}</button><span className="muted small-copy">Weights must total 1.00.</span></form></section>
        <section className="list-section admin-section"><div className="section-heading"><div><div className="eyebrow">COURSE SETUP</div><h2>Class groups</h2><p>Create course, semester, and year groups for student and teacher accounts.</p></div></div><form className="admin-weights" onSubmit={createCohort}><label className="field"><span>Course</span><select required value={cohortForm.course_id} onChange={(e) => setCohortForm((current) => ({ ...current, course_id: e.target.value }))}>{courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.course_name}</option>)}</select></label><label className="field"><span>Semester</span><select required value={cohortForm.semester} onChange={(e) => setCohortForm((current) => ({ ...current, semester: e.target.value }))}><option value="">Choose semester</option>{["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"].map((semester) => <option key={semester}>{semester}</option>)}</select></label><label className="field"><span>Academic year</span><input required maxLength="20" placeholder="2026–27" value={cohortForm.academic_year} onChange={(e) => setCohortForm((current) => ({ ...current, academic_year: e.target.value }))} /></label><button className="button button-primary button-small">Create class group</button></form><div className="interview-list">{cohorts.map((cohort) => <article className="interview-card" key={cohort.batch_id}><div className="interview-card-copy"><h3>{courses.find((course) => course.course_id === cohort.course_id)?.course_name || "Course"} · {cohort.semester}</h3><p>Academic year {cohort.academic_year}</p></div></article>)}</div></section>
      </>}
        </main>
      </div>
    </div>
  );
}

function cancelSpeech() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
}

function speak(text, onState = () => {}) {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return false;
  cancelSpeech();
  try {
    const synthesis = window.speechSynthesis;
    const line = new SpeechSynthesisUtterance(text);
    const voices = synthesis.getVoices();
    const english = voices.filter((voice) => /^en(-|_)/i.test(voice.lang));
    const feminineVoice = (voice) => /female|woman|samantha|victoria|karen|zira|susan|aria|jenny|sara|google uk english female/i.test(voice.name);
    const indianFeminine = english.find((voice) => /en[-_]in/i.test(voice.lang) && feminineVoice(voice));
    const feminine = english.find(feminineVoice);
    const indian = english.find((voice) => /en[-_]in/i.test(voice.lang));
    line.voice = indianFeminine || feminine || indian || english[0] || null;
    line.lang = line.voice?.lang || "en-IN";
    line.rate = 0.96;
    line.pitch = 1;
    line.onstart = () => onState("speaking");
    line.onend = () => onState("ready");
    line.onerror = (event) => {
      if (event.error === "canceled" || event.error === "interrupted") return;
      onState("error");
    };
    synthesis.speak(line);
  } catch {
    return false;
  }
  return true;
}


function InterviewAnalyticsSections({ report }) {
  const coverage = report.analysis_coverage;
  const audio = report.audio_summary || {};
  const average = (key) => {
    const value = audio[key];
    const count = audio.metric_sample_counts?.[key] || 0;
    return value == null ? "Not available" : Number(value).toFixed(1) + " · " + count + " answer" + (count === 1 ? "" : "s");
  };
  return <>
    <section className="report-summary-grid" aria-label="Interview communication averages">
      <div className="report-summary-item"><span>Speaking rate</span><strong>{average("words_per_minute")}<small> WPM</small></strong></div>
      <div className="report-summary-item"><span>Pauses per answer</span><strong>{average("pause_count")}</strong></div>
      <div className="report-summary-item"><span>Total pause time per answer</span><strong>{average("total_pause_duration_seconds")}<small> sec</small></strong></div>
      <div className="report-summary-item"><span>Longest pause per answer</span><strong>{average("longest_pause_seconds")}<small> sec</small></strong></div>
      <div className="report-summary-item"><span>Fillers per 100 words</span><strong>{audio.fillers_per_100_words == null ? "Not available" : Number(audio.fillers_per_100_words).toFixed(1) + " · " + (audio.metric_sample_counts?.fillers_per_100_words || 0) + " answers"}<small>{audio.filler_word_denominator ? " / " + audio.filler_word_denominator + " words" : ""}</small></strong></div>
      <div className="report-summary-item"><span>Delivery score</span><strong>{average("delivery_score")}<small> / 10</small></strong></div>
    </section>
    {coverage && <section className="report-insights-grid" aria-label="Analysis coverage">
      <article className="report-panel"><span className="eyebrow">ANALYSIS COVERAGE · {coverage.status.replaceAll("_", " ")}</span>
        <p>{coverage.questions_answered} recordings · {coverage.usable_recordings} usable · {coverage.transcribed_answers} transcribed · {coverage.content_evaluations} content evaluations · {coverage.communication_analyses} communication analyses</p>
        <div className="report-coverage-list">{Object.entries(coverage.coverage).map(([name, value]) => <span key={name}>{name.replaceAll("_", " ")}: {value.percentage == null ? "Not available" : value.percentage + "% (" + value.count + "/" + value.denominator + ")"}</span>)}</div>
        <small>{coverage.total_questions} total questions · {coverage.attempted_questions} attempted · {coverage.failed_or_unavailable_analyses} incomplete or unavailable analyses</small>
      </article>
      <article className="report-panel"><span className="eyebrow">TOPIC PERFORMANCE</span>
        {report.topic_analysis?.length ? <div className="report-coverage-list">{report.topic_analysis.map((topic) => <span key={topic.topic}>{topic.topic}: {topic.average_content_score == null ? "Not available" : Number(topic.average_content_score).toFixed(1) + "/10"} · {topic.questions_scored}/{topic.questions_total} scored · {topic.classification.replaceAll("_", " ").toLowerCase()}{topic.sample_note ? " · " + topic.sample_note : ""} · Q{topic.question_orders.join(", Q")}</span>)}</div> : <p>No question topics are tagged, so topic analysis is unavailable.</p>}
      </article>
    </section>}
    <section className="report-panel"><span className="eyebrow">PERSONALIZED PRACTICE PLAN</span>
      {report.improvement_plan?.length ? <ol className="report-plan-list">{report.improvement_plan.map((item, index) => <li key={item.area + "-" + index}><strong>{item.area}</strong>{item.question_order ? <small> · Question {item.question_order}</small> : null}<p>{item.interpretation}</p>{item.evidence && <blockquote>Evidence: “{item.evidence}”</blockquote>}<p>{item.practice_activity}</p><small>Target: {item.measurable_target} · {item.review_timeframe}</small></li>)}</ol> : <p>There is not enough evaluated evidence to suggest priorities yet.</p>}
    </section>
  </>;
}

function ReportPage() {
  const { interviewId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [teacherScore, setTeacherScore] = useState("");
  const [teacherRemark, setTeacherRemark] = useState("");
  const [questionEdits, setQuestionEdits] = useState({});
  const [busy, setBusy] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [expandedQuestions, setExpandedQuestions] = useState(() => new Set());
  const [openTranscripts, setOpenTranscripts] = useState(() => new Set());
  const [exporting, setExporting] = useState("");
  const canReview = user?.role === "teacher" || user?.role === "admin";

  useEffect(() => {
    let active = true;
    api(`/interviews/${interviewId}/report`)
      .then((data) => {
        if (!active) return;
        setReport(data);
        setTeacherScore(data.teacher_score ?? "");
        setTeacherRemark(data.teacher_remark || "");
        setQuestionEdits(Object.fromEntries((data.questions || []).map((q) => [q.interview_question_id, {
          teacher_score: q.teacher_score ?? "",
          teacher_remark: q.teacher_remark || "",
          teacher_criteria_scores: q.teacher_review?.teacher_criteria_scores || Object.fromEntries(
            Object.keys(q.evaluation?.criteria_scores || {}).map((criterion) => [criterion, ""]),
          ),
        }])));
      })
      .catch((err) => { if (active) setError(err.message); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [interviewId]);

  function updateQuestion(id, key, value) {
    setQuestionEdits((current) => ({ ...current, [id]: { ...current[id], [key]: value } }));
  }

  async function saveReview(event) {
    event.preventDefault();
    setSaving(true); setError(""); setNotice("");
    try {
      const updated = await api(`/interviews/${interviewId}/report`, {
        method: "PATCH",
        body: JSON.stringify({
          teacher_score: teacherScore === "" ? null : Number(teacherScore),
          teacher_remark: teacherRemark,
          question_reviews: report.questions.map((q) => ({
            interview_question_id: q.interview_question_id,
            teacher_score: questionEdits[q.interview_question_id]?.teacher_score === "" ? null : Number(questionEdits[q.interview_question_id]?.teacher_score),
            teacher_remark: questionEdits[q.interview_question_id]?.teacher_remark || "",
          teacher_criteria_scores: Object.fromEntries(Object.entries(questionEdits[q.interview_question_id]?.teacher_criteria_scores || {})
            .filter(([, score]) => score !== "" && score != null).map(([criterion, score]) => [criterion, Number(score)])),
          })),
        }),
      });
      setReport(updated);
      setTeacherScore(updated.teacher_score ?? "");
      setTeacherRemark(updated.teacher_remark || "");
      setQuestionEdits(Object.fromEntries(updated.questions.map((q) => [q.interview_question_id, {
        teacher_score: q.teacher_score ?? "", teacher_remark: q.teacher_remark || "",
        teacher_criteria_scores: q.teacher_review?.teacher_criteria_scores || Object.fromEntries(
          Object.keys(q.evaluation?.criteria_scores || {}).map((criterion) => [criterion, ""]),
        ),
      }])));
      setNotice("Teacher review saved.");
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  async function download(path, filename) {
    setExporting(filename.endsWith(".pdf") ? "pdf" : "excel"); setError("");
    try {
      const blob = await api(path);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl; anchor.download = filename; anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (err) { setError(err.message); }
    finally { setExporting(""); }
  }

  const questions = report?.questions || [];
  const questionStatus = (question) => question.needs_review ? "review" :
    (question.final_ai_score != null || question.content_score != null || question.delivery_score != null || question.evaluation?.feedback) ? "evaluated" : "unavailable";
  const answeredCount = report?.analysis_coverage?.questions_answered ?? 0;
  const toggleSet = (setter, id) => setter((current) => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const overallStatus = report?.report_status === "NEEDS_REVIEW" ? "Teacher review needed" :
    report?.report_status === "REVIEWED" ? "Reviewed" : report?.report_status === "READY" ? "Evaluation complete" :
    (report?.report_status || "Report status unavailable").replaceAll("_", " ").toLowerCase();
  const statusClass = report?.report_status === "NEEDS_REVIEW" ? "review" : "ready";
  const displayScore = (score) => score == null ? "—" : Number(score).toFixed(1);

  if (busy) return <ReportWorkspace user={user}><Loading label="Loading interview report" /></ReportWorkspace>;
  return <ReportWorkspace user={user}><div className="app-shell report-page report-v2">
    <div className="report-heading-actions"><nav className="report-breadcrumb" aria-label="Breadcrumb"><button className="text-button" onClick={() => navigate("/dashboard")}>← Dashboard</button><span aria-hidden="true">/</span><span>Interview report</span></nav>
      {report && <div className="report-export-actions"><button type="button" className="report-download" disabled={!!exporting} onClick={() => download(`/interviews/${interviewId}/report.pdf`, `queme-interview-${interviewId}.pdf`)}>{exporting === "pdf" ? "Preparing PDF…" : "Download PDF"}</button><button type="button" className="report-download" disabled={!!exporting} onClick={() => download(`/interviews/${interviewId}/report.xlsx`, `queme-interview-${interviewId}.xlsx`)}>{exporting === "excel" ? "Preparing Excel…" : "Download Excel"}</button></div>}
    </div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {report && <>
      <header className="report-overview">
        <div className="report-overview-copy"><div className="eyebrow">INTERVIEW REPORT</div><h1>{report.template_title || "Interview report"}</h1>
          <p><strong>{report.student_name || "Student"}</strong>{report.teacher_name && <> <span>·</span> Facilitated by {report.teacher_name}</>}</p>
          <span className={`report-state report-state-${statusClass}`}><i aria-hidden="true" />{overallStatus}</span>
        </div>
      </header>
      {report.report_status === "NEEDS_REVIEW" && <p className="report-review-notice" role="status">Your answers have been recorded. This report is awaiting teacher review.</p>}
      <section className="report-summary-grid" aria-label="Interview scores">
        <div className="report-summary-item"><span>Final score</span><strong>{report.final_score == null ? "Pending review" : <>{displayScore(report.final_score)}<small>/10</small></>}</strong></div>
        <div className="report-summary-item"><span>Content score</span><strong>{report.score_summary?.content_score == null ? "Not evaluated" : <>{displayScore(report.score_summary.content_score)}<small>/10 · {report.score_summary.content_score_count} answers</small></>}</strong></div>
        <div className="report-summary-item"><span>Delivery score</span><strong>{report.score_summary?.delivery_score == null ? "Not evaluated" : <>{displayScore(report.score_summary.delivery_score)}<small>/10 · {report.score_summary.delivery_score_count} answers</small></>}</strong></div>
        <div className="report-summary-item"><span>Questions answered</span><strong>{answeredCount}<small> / {questions.length}</small></strong></div>
      </section>
      <p className="report-score-method">{report.score_method} Configured weights: {Math.round((report.score_weights?.content_weight ?? 0.7) * 100)}% content and {Math.round((report.score_weights?.delivery_weight ?? 0.3) * 100)}% delivery.</p>
      <InterviewAnalyticsSections report={report} />
      {notice && <div className="alert alert-info" role="status">{notice}</div>}
      <form onSubmit={saveReview}>
        <section className="report-question-list" aria-label="Question feedback">{questions.map((q) => {
          const id = q.interview_question_id;
          const isExpanded = expandedQuestions.has(id);
          const state = questionStatus(q);
          const stateLabel = state === "review" ? "Needs review" : state === "evaluated" ? "Evaluated" : "Evaluation unavailable";
          const rubricCriteria = q.evaluation?.rubric_snapshot?.criteria || Object.keys(q.evaluation?.criteria_scores || {}).map((name) => ({ name }));
          return <article className={`report-question-card report-question-${state}`} key={id}>
            <button type="button" className="report-question-toggle" aria-expanded={isExpanded} aria-controls={`question-detail-${id}`} onClick={() => toggleSet(setExpandedQuestions, id)}>
              <span className="report-question-number">{String(q.question_order).padStart(2, "0")}</span><span className="report-question-title"><small>{q.is_followup ? "FOLLOW-UP QUESTION" : `QUESTION ${q.question_order}`}</small><strong>{q.question_text || "Question text unavailable"}</strong>{(q.content_score != null || q.delivery_score != null) && <span className="report-question-inline-scores">{q.content_score != null && <>Content {displayScore(q.content_score)}</>}{q.content_score != null && q.delivery_score != null && <span aria-hidden="true">·</span>}{q.delivery_score != null && <>Delivery {displayScore(q.delivery_score)}</>}</span>}</span>
              {state !== "evaluated" && <span className={`report-question-status report-question-status-${state}`}>{stateLabel}</span>}<span className={`report-chevron ${isExpanded ? "is-open" : ""}`} aria-hidden="true">⌄</span>
            </button>
            {isExpanded && <div id={`question-detail-${id}`} className="report-question-detail">
              {q.analysis_status?.status !== "COMPLETE" && <p className="report-review-notice">{q.analysis_status?.status?.replaceAll("_", " ") || "ANALYSIS STATUS UNAVAILABLE"}: {q.analysis_status?.reason || "No explanation is available."}</p>}
              {q.evaluation?.feedback && <section className="report-feedback"><span className="eyebrow">AI SUMMARY</span><p>{q.evaluation.feedback}</p></section>}
              {(q.evaluation?.technical_accuracy || q.evaluation?.missing_concepts?.length > 0 || q.evaluation?.correct_explanation) && <section className="report-feedback"><span className="eyebrow">ANSWER REVIEW</span>{q.evaluation.technical_accuracy && <p><b>Technical accuracy:</b> {q.evaluation.technical_accuracy}</p>}{q.evaluation.missing_concepts?.length > 0 && <p><b>Missing concepts:</b> {q.evaluation.missing_concepts.join(", ")}</p>}{q.evaluation.correct_explanation && <p><b>Suggested explanation:</b> {q.evaluation.correct_explanation}</p>}</section>}
              <div className="report-feedback-columns">{q.evaluation?.strengths?.length > 0 && <section className="report-feedback-positive"><h3>Strengths</h3><ul>{q.evaluation.strengths.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section>}{q.evaluation?.weaknesses?.length > 0 && <section className="report-feedback-growth"><h3>Areas to improve</h3><ul>{q.evaluation.weaknesses.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section>}</div>
              {rubricCriteria.length > 0 && <section className="report-feedback"><span className="eyebrow">AI RUBRIC BREAKDOWN · {q.evaluation.rubric_snapshot?.name || "Interview rubric"}</span><div className="report-criteria">{rubricCriteria.map((criterionItem) => {
                const criterion = typeof criterionItem === "string" ? criterionItem : criterionItem.name;
                const detail = q.evaluation.criterion_details?.[criterion] || {};
                const score = q.evaluation.criteria_scores?.[criterion];
                const weight = q.evaluation.criteria_weights?.[criterion] ?? criterionItem.weight ?? 0;
                return <article key={criterion}><strong>{criterion}</strong><span>{detail.applicable === false ? "Not applicable" : score == null ? "Score unavailable" : displayScore(score) + "/10"} · {Number(weight).toFixed(0)}% weight</span>{detail.explanation && <p><b>AI interpretation:</b> {detail.explanation}</p>}{detail.evidence && <p><b>Transcript evidence:</b> “{detail.evidence}”</p>}{score != null && !detail.evidence && <p>Transcript evidence is not available for this criterion.</p>}</article>;
              })}</div></section>}
              {q.teacher_review && <section className="report-feedback"><span className="eyebrow">TEACHER REVIEW COMPARISON</span><p>AI score {q.teacher_review.ai_score ?? "—"}/10 · Teacher score {q.teacher_review.teacher_score ?? "—"}/10 · Difference {q.teacher_review.score_difference ?? "—"}</p>{Object.entries(q.teacher_review.criterion_differences || {}).map(([criterion, difference]) => <p key={criterion}>{criterion}: teacher − AI = {difference}</p>)}{q.teacher_review.reviewer_name && <small>Reviewed by {q.teacher_review.reviewer_name}{q.teacher_review.reviewed_at ? " · " + new Date(q.teacher_review.reviewed_at).toLocaleString() : ""}</small>}</section>}
              {q.audio_analysis && <div className="report-audio-metrics"><span>Audio quality: {q.audio_analysis.audio_quality_status || "Not assessed"}</span><span>{q.audio_analysis.words_per_minute ?? "—"} words/min</span><span>{q.audio_analysis.pause_count ?? "—"} pauses</span><span>{q.audio_analysis.filler_word_count ?? "—"} fillers</span></div>}
              <div className="report-answer-materials">{q.transcript?.trim() ? <div className="report-transcript-panel"><button type="button" aria-expanded={openTranscripts.has(id)} onClick={() => toggleSet(setOpenTranscripts, id)}>{openTranscripts.has(id) ? "Hide transcript" : "View transcript"}</button>{openTranscripts.has(id) && <p>{q.transcript}</p>}</div> : null}
                <div className="report-audio-panel">{q.audio_url ? <><span className="report-audio-link">Play recorded answer</span><AuthenticatedAudio path={q.audio_url} /></> : <span className="report-material-unavailable">No recording available</span>}</div></div>
              {canReview && <div className="report-review-fields">{Object.keys(q.evaluation?.criteria_scores || {}).map((criterion) => <label className="field" key={"teacher-" + criterion}><span>Teacher · {criterion} <em>0 to 10</em></span><input type="number" min="0" max="10" step="0.01" value={questionEdits[id]?.teacher_criteria_scores?.[criterion] ?? ""} onChange={(event) => setQuestionEdits((current) => ({ ...current, [id]: { ...current[id], teacher_criteria_scores: { ...current[id]?.teacher_criteria_scores, [criterion]: event.target.value } } }))} /></label>)}<label className="field"><span>Teacher score override <em>Optional · 0 to 10</em></span><input type="number" min="0" max="10" step="0.01" value={questionEdits[id]?.teacher_score ?? ""} onChange={(event) => updateQuestion(id, "teacher_score", event.target.value)} /></label><label className="field"><span>Teacher remark</span><textarea maxLength="5000" rows="3" value={questionEdits[id]?.teacher_remark ?? ""} onChange={(event) => updateQuestion(id, "teacher_remark", event.target.value)} /></label></div>}
            </div>}
          </article>;
        })}</section>
        {canReview && <section className="report-review-summary"><span className="eyebrow">FACILITATOR REVIEW</span><h2>Overall teacher review</h2><div className="field-row"><label className="field"><span>Overall score override <em>Optional · 0 to 10</em></span><input type="number" min="0" max="10" step="0.01" value={teacherScore} onChange={(event) => setTeacherScore(event.target.value)} /></label></div><label className="field"><span>Overall remarks</span><textarea maxLength="5000" rows="4" value={teacherRemark} onChange={(event) => setTeacherRemark(event.target.value)} /></label><button className="button button-primary" disabled={saving}>{saving ? "Saving review…" : "Save teacher review"}<span aria-hidden="true">→</span></button></section>}
      </form>
      {!canReview && report.teacher_remark && <div className="report-review-summary"><span className="eyebrow">FACILITATOR REVIEW</span><h2>Teacher remarks</h2><p>{report.teacher_remark}</p></div>}
    </>}
  </div></ReportWorkspace>;
}

function InterviewerPortrait() {
  return (
    <div className="ai-interviewer-portrait" role="img" aria-label="QueMe AI voice interviewer">
      <span className="interviewer-brand-orbit"><BrandMark /></span>
      <span className="interviewer-audio-icon"><AudioLines size={33} strokeWidth={1.6} /></span>
      <span className="interviewer-voice-label">AI voice interviewer</span>
      <span className="interviewer-voice-caption">Questions are spoken aloud</span>
    </div>
  );
}

function InterviewPage() {
  const { interviewId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(true);
  const [working, setWorking] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingStarting, setRecordingStarting] = useState(false);
  const [playingClip, setPlayingClip] = useState(false);
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [interviewStarted, setInterviewStarted] = useState(false);
  const [muted, setMuted] = useState(false);
  const [speechState, setSpeechState] = useState("ready");
  const [speechError, setSpeechError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [clip, setClip] = useState(null);
  const [transcript, setTranscript] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const cameraVideoRef = useRef(null);
  const mountedRef = useRef(true);
  const clipAudioRef = useRef(null);
  const sessionStatusRef = useRef(session?.status);
  const question = session?.current_question;
  sessionStatusRef.current = session?.status;
  const speechSupported = typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const clipUrl = useMemo(() => (clip ? URL.createObjectURL(clip) : null), [clip]);

  useEffect(() => {
    let alive = true;
    api(`/interviews/${interviewId}`)
      .then((data) => { if (alive) setSession(data); })
      .catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [interviewId]);

  useEffect(() => {
    try { setInterviewStarted(sessionStorage.getItem(`queme-interview-intro-${interviewId}`) === "played"); }
    catch { setInterviewStarted(false); }
  }, [interviewId]);

  useEffect(() => () => cancelSpeech(), [question?.interview_question_id, session?.status, interviewId]);

  useEffect(() => {
    const video = cameraVideoRef.current;
    if (!cameraEnabled || !video || !cameraStreamRef.current) return undefined;
    video.srcObject = cameraStreamRef.current;
    video.play().catch(() => {
      stopCamera();
      setCameraError("Camera preview could not start playing. Try enabling the camera again.");
    });
    return () => {
      if (video.srcObject === cameraStreamRef.current) video.srcObject = null;
    };
  }, [cameraEnabled]);

  useEffect(() => {
    if (session?.status === "COMPLETED" || session?.status === "CANCELLED") stopCamera();
  }, [session?.status]);

  useEffect(() => {
    if (!recording) return undefined;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cancelSpeech();
      clipAudioRef.current?.pause();
      cameraStreamRef.current?.getVideoTracks().forEach((track) => { track.onended = null; track.stop(); });
      cameraStreamRef.current = null;
      if (cameraVideoRef.current) cameraVideoRef.current.srcObject = null;
      if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => () => {
    if (clipUrl) URL.revokeObjectURL(clipUrl);
  }, [clipUrl]);

  async function startSession() {
    if (!consent) return;
    setWorking(true); setError("");
    let permissionStream;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser does not support microphone recording. Try a current version of Chrome, Edge, or Firefox.");
      permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach((track) => track.stop());
      const data = await api(`/interviews/${interviewId}/start`, { method: "POST", body: JSON.stringify({ consent: true }) });
      setSession(data);
      setNotice("");
    } catch (err) {
      permissionStream?.getTracks().forEach((track) => track.stop());
      setError(err.message || "Microphone access is needed to start.");
    } finally { setWorking(false); }
  }

  async function enableCamera() {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("This browser does not support a local camera preview. You can continue without it.");
      return;
    }
    setCameraLoading(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      if (!mountedRef.current || sessionStatusRef.current === "COMPLETED" || sessionStatusRef.current === "CANCELLED") {
        stream.getVideoTracks().forEach((track) => track.stop());
        return;
      }
      cameraStreamRef.current = stream;
      stream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          if (cameraStreamRef.current === stream) {
            stopCamera();
            setCameraError("The camera disconnected. Reconnect it and retry the preview.");
          }
        };
      });
      setCameraEnabled(true);
    } catch (err) {
      const messages = {
        NotAllowedError: "Camera permission was blocked. Allow camera access in your browser settings, then try again.",
        SecurityError: "Camera access is blocked for this page. Use a secure connection and allow camera access.",
        NotFoundError: "No camera was found. Connect a camera or continue without the preview.",
        DevicesNotFoundError: "No camera was found. Connect a camera or continue without the preview.",
        NotReadableError: "The camera could not start. It may be in use by another application.",
        TrackStartError: "The camera could not start. It may be in use by another application.",
        OverconstrainedError: "This camera could not use the requested preview settings. Try again or continue without it.",
        AbortError: "The camera start was interrupted. Please try again.",
      };
      setCameraError(messages[err.name] || "The camera preview could not start. Check your device and try again.");
    } finally {
      if (mountedRef.current) setCameraLoading(false);
    }
  }

  function stopCamera() {
    cameraStreamRef.current?.getVideoTracks().forEach((track) => { track.onended = null; track.stop(); });
    cameraStreamRef.current = null;
    if (cameraVideoRef.current) cameraVideoRef.current.srcObject = null;
    setCameraEnabled(false);
    setCameraLoading(false);
    setCameraError("");
  }

  function playQuestion() {
    if (!question?.question_text || muted) return;
    setSpeechError("");
    const success = speak(question.question_text, (state) => {
      setSpeechState(state === "error" ? "ready" : state);
      if (state === "error") setSpeechError("Question audio could not play. You can still read the question below.");
    });
    if (!success) setSpeechError("Speech is unavailable in this browser. You can still read the question below.");
  }

  function beginInterview() {
    setInterviewStarted(true);
    try { sessionStorage.setItem(`queme-interview-intro-${interviewId}`, "played"); }
    catch { /* The interview still works if session storage is unavailable. */ }
    setSpeechError("");
    if (muted || !speechSupported) {
      if (!speechSupported) setSpeechError("Speech is unavailable in this browser. You can still read each question below.");
      return;
    }
    const intro = "Hello! Welcome to your QueMe interview. Take your time, listen carefully, and answer each question as clearly as you can. Let's begin.";
    const success = speak(intro, (state) => {
      setSpeechState(state === "error" ? "ready" : state);
      if (state === "ready") playQuestion();
      if (state === "error") setSpeechError("Question audio could not play. You can still read the question below.");
    });
    if (!success) setSpeechError("Speech is unavailable in this browser. You can still read each question below.");
  }

  function toggleMute() {
    const nextMuted = !muted;
    if (nextMuted) {
      cancelSpeech();
      setSpeechState("ready");
    }
    setMuted(nextMuted);
  }

  async function beginRecording() {
    if (recording || recordingStarting || working) return;
    setError(""); setNotice(""); setTranscript(""); setSeconds(0);
    setRecordingStarting(true);
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("This browser does not support audio recording. Try a current version of Chrome, Edge, or Firefox.");
      }
      cancelSpeech();
      setSpeechState("ready");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const choices = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
      const supported = choices.find((type) => window.MediaRecorder?.isTypeSupported?.(type));
      const recorder = supported ? new MediaRecorder(stream, { mimeType: supported }) : new MediaRecorder(stream);
      const chunks = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        if (mountedRef.current) {
          setRecording(false);
          if (blob.size) setClip(blob);
          else setError("No audio was captured. Check your microphone and record again.");
        }
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      };
      recorder.onerror = () => {
        if (mountedRef.current) {
          setRecording(false);
          setError("Recording stopped unexpectedly. Check your microphone and try again.");
        }
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      };
      recorderRef.current = recorder;
      recorder.start(500);
      setClip(null);
      setRecording(true);
    } catch (err) {
      setError(err.name === "NotAllowedError" ? "Microphone access was blocked. Allow microphone access in your browser settings, then try again." : err.message || "Could not start microphone recording.");
    } finally { if (mountedRef.current) setRecordingStarting(false); }
  }

  function stopRecording() {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    setRecording(false);
  }

  async function submitRecording() {
    if (!clip || !question) return;
    clipAudioRef.current?.pause();
    setPlayingClip(false);
    setWorking(true); setError(""); setNotice("");
    const form = new FormData();
    const extension = clip.type.includes("ogg") ? "ogg" : clip.type.includes("mp4") ? "m4a" : clip.type.includes("wav") ? "wav" : "webm";
    form.append("audio", clip, `answer.${extension}`);
    try {
      const result = await api(`/interviews/${interviewId}/questions/${question.interview_question_id}/answer`, { method: "POST", body: form });
      cancelSpeech();
      setSpeechState("ready");
      setSession(result.session);
      if (result.action === "retry") {
        setNotice(result.message);
        setClip(null);
      } else if (result.action === "repeat") {
        setNotice(result.message);
        setClip(null);
        if (result.session.current_question && !muted && interviewStarted) playQuestion();
      } else {
        setTranscript(result.transcript || "");
        setClip(null);
        setNotice(result.action === "complete" ? "Your interview is complete. Nice work." : "Answer saved. Moving on.");
      }
    } catch (err) {
      setError(err.message);
    } finally { setWorking(false); }
  }

  async function advance(intent) {
    if (!session || !question) return;
    cancelSpeech();
    setSpeechState("ready");
    setWorking(true); setError(""); setNotice(""); setClip(null); setTranscript("");
    try {
      const result = await api(`/interviews/${interviewId}/advance`, { method: "POST", body: JSON.stringify({ intent }) });
      setSession(result.session);
      setNotice(result.action === "complete" ? "Your interview is complete. Nice work." : intent === "SKIP" ? "Question skipped." : "Moving to the next question.");
    } catch (err) { setError(err.message); }
    finally { setWorking(false); }
  }

  if (busy) return <><TopBar user={user} /><Loading label="Opening your interview" /></>;

  const progress = session?.total_questions ? (session.completed_questions / session.total_questions) * 100 : 0;
  const isScheduled = session?.status === "SCHEDULED";
  const isComplete = session?.status === "COMPLETED";
  const interviewerStatus = error || speechError ? "Error" : recordingStarting ? "Starting microphone" : working ? (clip ? "Uploading and analyzing answer" : isScheduled ? "Preparing interview" : "Processing interview") : recording ? "Listening to your answer" : playingClip ? "Playing back your answer" : speechState === "speaking" ? "Speaking" : notice?.toLowerCase().includes("answer saved") ? "Answer saved" : isComplete ? "Interview complete" : session?.status === "CANCELLED" ? "Interview cancelled" : "Ready";

  return (
    <>
      <TopBar user={user} />
      <main className="interview-page">
        <div className="interview-topline"><button className="text-button" onClick={() => navigate("/dashboard")}>← Dashboard</button><span className="interview-session-label">PRACTICE SESSION <span>·</span> {session?.template_title || "Interview"}</span><span className="privacy-chip">◈ Private session</span></div>
        {error && <div className="alert alert-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
        <section className="interview-room-grid">
          <aside className={`interviewer-card${speechState === "speaking" ? " is-speaking" : ""}`} aria-label="AI interviewer">
            <div className="interviewer-card-top"><span className="ai-badge"><i />AI VOICE INTERVIEWER</span><button className="speech-toggle" type="button" onClick={toggleMute} disabled={!speechSupported} aria-pressed={muted} aria-label={muted ? "Unmute interviewer voice" : "Mute interviewer voice"} title={speechSupported ? (muted ? "Unmute voice" : "Mute voice") : "Speech is unavailable in this browser"}>{muted ? <AudioLines size={16} /> : <Headphones size={16} />}<span>{muted ? "Unmute" : "Mute"}</span></button></div>
            <div className="interviewer-portrait-wrap"><div className="interviewer-halo" /><InterviewerPortrait /><span className="interviewer-spark interviewer-spark-one">✳</span><span className="interviewer-spark interviewer-spark-two">✦</span></div>
            <div className="interviewer-card-copy"><span className="interviewer-name">QueMe AI Interviewer</span><span className="interviewer-status" aria-live="polite"><i className={recording ? "status-dot is-recording" : speechState === "speaking" ? "status-dot is-speaking" : "status-dot"} />{interviewerStatus}</span></div>
            {speechState === "speaking" && <div className="interviewer-wave" aria-label="Interviewer is speaking" role="img"><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>}
            {session?.scheduled_at && <div className="interviewer-schedule">Scheduled {new Date(session.scheduled_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</div>}
          </aside>

          <section className="interview-conversation">
            <header className="conversation-header"><div><span className="rail-kicker">YOUR INTERVIEW</span><h1>{session?.template_title || "Interview practice"}</h1><p>Facilitated by {session?.teacher_name || "your campus teacher"}</p></div><span className="privacy-chip">◈ Private session</span></header>
            {session && <div className="conversation-progress"><div className="rail-progress-copy"><span>Question progress</span><strong>{session?.completed_questions || 0} / {session?.total_questions || 0}</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }} /></div></div>}
            {isScheduled && (
              <div className="consent-panel">
                <div className="step-label"><span>01</span> BEFORE YOU BEGIN</div>
                <h2>Settle in and get ready.</h2>
                <p>Your interviewer will ask the questions aloud. You can listen again at any time. Your microphone is used only to record your answers for this practice interview, and your recordings and transcripts are shared with you and your assigned teacher.</p>
                <label className="consent-check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span>I understand and consent to audio recording for this practice interview.</span></label>
                <button className="button button-primary" disabled={!consent || working} onClick={startSession}>{working ? "Checking microphone…" : "Give consent & continue"}<span aria-hidden="true">→</span></button>
                <p className="consent-footnote">Your browser will ask you to allow microphone access next.</p>
              </div>
            )}

            {session?.status === "IN_PROGRESS" && question && !interviewStarted && (
              <div className="interview-intro-card">
                <span className="intro-kicker">A CONVERSATION AT YOUR PACE</span><h2>Ready when you are.</h2><p>Take your time, listen carefully, and answer each question as clearly as you can. You can replay questions before answering.</p>
                <button className="button button-primary" disabled={working} onClick={beginInterview}>Start interview<span aria-hidden="true">→</span></button>
                {speechError && <p className="speech-fallback" role="status">{speechError}</p>}
              </div>
            )}

            {session?.status === "IN_PROGRESS" && question && interviewStarted && (
              <div className="question-panel">
                <div className="step-label"><span>{String(question.question_order).padStart(2, "0")}</span> QUESTION {String(question.question_order).padStart(2, "0")} OF {String(session.total_questions).padStart(2, "0")}{question.is_followup ? " · FOLLOW-UP" : ""}</div>
                <div className="question-type-row"><span className="question-type">{question.question_type || "Interview question"}</span><span className="difficulty-tag">{question.difficulty || "Practice"} level</span></div>
                <h2 className="question-text">{question.question_text}</h2>
                <div className="speech-controls"><button className="button button-listen" type="button" disabled={!speechSupported || working || recording || playingClip} onClick={playQuestion}><Play size={15} aria-hidden="true" />{speechState === "speaking" ? "Speaking…" : "Listen to question"}</button><button className="text-button" type="button" disabled={!speechSupported || working || recording || playingClip} onClick={playQuestion}>Replay question</button></div>
                {speechError && <p className="speech-fallback" role="status">{speechError}</p>}
                <p className="recording-instruction">When you’re ready, start recording. You can listen back before submitting.</p>

                <div className={`recording-box ${recording ? "is-recording" : ""}`}>
                  {!recording && !clip && <><span className="mic-mark">◎</span><div><strong>{recordingStarting ? "Starting microphone…" : "Ready to record"}</strong><p>{recordingStarting ? "Allow microphone access if your browser asks." : "Start when you feel comfortable. You can retry if needed."}</p></div><button className="button button-primary" disabled={working || recordingStarting} onClick={beginRecording}>{recordingStarting ? "Starting…" : "Start recording"}<span aria-hidden="true">●</span></button></>}
                  {recording && <><span className="recording-pulse" /><div><strong>Listening to your answer</strong><p>Your answer is being recorded.</p></div><span className="record-timer">{String(Math.floor(seconds / 60)).padStart(2, "0")}:{String(seconds % 60).padStart(2, "0")}</span><button className="button button-dark" onClick={stopRecording}>Stop recording</button></>}
                  {!recording && clip && <><span className="mic-mark mic-ready">✓</span><div className="clip-copy"><strong>{working ? "Uploading and analyzing…" : "Recording ready"}</strong><p>{working ? "Keep this page open while your answer is processed." : "Listen back or record a new answer before submitting."}</p><audio ref={clipAudioRef} controls src={clipUrl} onPlay={() => { cancelSpeech(); setSpeechState("ready"); setPlayingClip(true); }} onPause={() => setPlayingClip(false)} onEnded={() => setPlayingClip(false)} /></div><button className="button button-outline button-small" disabled={working} onClick={beginRecording}>Re-record</button><button className="button button-primary" disabled={working} onClick={submitRecording}>{working ? "Processing…" : "Submit answer"}<span aria-hidden="true">→</span></button></>}
                </div>

                {notice && <div className="alert alert-info" role="status">{notice}</div>}
                {transcript && <div className="transcript-box"><span className="eyebrow">YOUR TRANSCRIPT</span><p>{transcript}</p></div>}
                <div className="question-actions"><button className="text-button" disabled={working || recording || Boolean(clip)} onClick={() => advance("SKIP")}>Skip question <span aria-hidden="true">→</span></button><button className="text-button text-button-muted" disabled={working || recording || Boolean(clip)} onClick={() => advance("DONE")}>Finish interview</button></div>
              </div>
            )}

            {(isComplete || session?.status === "COMPLETED") && <div className="completion-panel completion-with-answers"><div className="completion-check">✓</div><div className="step-label">SESSION COMPLETE</div><h2>You showed up. That counts.</h2><p>Your report is ready. Some answers may need a teacher’s review when automatic evaluation is unavailable.</p>
              {session.answers?.length > 0 && <div className="saved-answers"><div className="eyebrow">YOUR RECORDINGS</div>{session.answers.map((answer) => <div className="saved-answer" key={answer.interview_question_id}><div><strong>Question {answer.question_order}</strong><p>{answer.question_text}</p></div><AuthenticatedAudio path={answer.audio_url} /></div>)}</div>}
              <button className="button button-outline" onClick={() => navigate(`/interviews/${interviewId}/report`)}>View report<span aria-hidden="true">→</span></button>
              <button className="button button-primary" onClick={() => navigate("/dashboard")}>Back to dashboard<span aria-hidden="true">→</span></button></div>}
            {session?.status === "CANCELLED" && <div className="completion-panel"><div className="step-label">SESSION CANCELLED</div><h2>This interview is no longer available.</h2><button className="button button-primary" onClick={() => navigate("/dashboard")}>Back to dashboard</button></div>}
            {session && session.status === "IN_PROGRESS" && !question && <div className="completion-panel"><h2>No questions are available.</h2><p>Please contact your teacher.</p></div>}
          </section>

          <aside className={`student-camera-card${cameraEnabled ? " is-on" : ""}`} aria-label="Optional student camera preview">
            <div className="student-camera-heading"><div><span className="rail-kicker">OPTIONAL PREVIEW</span><h2>Your camera</h2></div><span className={`camera-state${cameraEnabled ? " is-on" : ""}`}>{cameraLoading ? "Starting" : cameraEnabled ? "Camera is on" : "Camera is off"}</span></div>
            <div className={`student-camera-frame${cameraEnabled ? " has-video" : ""}`}>
              {cameraEnabled ? <video ref={cameraVideoRef} autoPlay muted playsInline aria-label="Your live camera preview. Video stays on this device." /> : cameraLoading ? <div className="camera-placeholder" role="status"><span className="camera-spinner" /><strong>Starting camera…</strong></div> : <div className="camera-placeholder"><VideoOff size={27} aria-hidden="true" /><strong>Camera is off</strong><span>Enable it only if you want a self-preview.</span></div>}
            </div>
            {cameraError && <p className="camera-error" role="alert">{cameraError}</p>}
            <p className="camera-privacy">Your preview stays on this device. Camera video is not recorded, uploaded, or analyzed.</p>
            {cameraEnabled ? <button className="button camera-toggle-off" type="button" onClick={stopCamera}><VideoOff size={15} />Turn camera off</button> : <button className="button camera-toggle-on" type="button" onClick={enableCamera} disabled={!session || cameraLoading || isComplete || session?.status === "CANCELLED"}><Video size={15} />{cameraLoading ? "Starting camera…" : cameraError ? "Retry camera" : "Enable camera"}</button>}
          </aside>
        </section>
      </main>
    </>
  );
}

function StudentPracticeInterviewsPage() {
  const { user } = useAuth();
  return <PracticeInterviews user={user} />;
}

function StudentRapidFirePage() {
  const { user } = useAuth();
  return <RapidFirePractice user={user} />;
}

function StudentMyProgressPage() {
  const { user } = useAuth();
  return <MyProgress user={user} />;
}

function StudentFeedbackPage() {
  const { user } = useAuth();
  return <StudentFeedback user={user} />;
}

function App() {
  const { ready, user } = useAuth();
  const [introFinished, setIntroFinished] = useState(false);
  const [splashVisible, setSplashVisible] = useState(true);
  const [splashExiting, setSplashExiting] = useState(false);

  useEffect(() => {
    const introDuration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 1450 : 1800;
    const timer = window.setTimeout(() => setIntroFinished(true), introDuration);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!ready || !introFinished) return undefined;
    setSplashExiting(true);
    const timer = window.setTimeout(() => setSplashVisible(false), 260);
    return () => window.clearTimeout(timer);
  }, [ready, introFinished]);

  if (splashVisible) {
    return (
      <main className={`splash-screen${splashExiting ? " splash-exiting" : ""}`} aria-label="QueMe is getting ready">
        <div className="splash-glow splash-glow-one" aria-hidden="true" />
        <div className="splash-glow splash-glow-two" aria-hidden="true" />
        <div className="splash-content" role="status" aria-live="polite">
          <BrandMark className="splash-mark" />
          <h1 className="splash-brand">QueMe<span>.</span></h1>
          <p className="splash-tagline">Practice. Improve. Succeed.</p>
          {!ready && <span className="splash-loading">Preparing your space</span>}
        </div>
        <div className="splash-particles" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div>
      </main>
    );
  }
  return (
    <Routes>
      <Route path="/" element={user ? <Navigate to="/dashboard" replace /> : <HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/pending" element={<PendingPage />} />
      <Route path="/dashboard" element={<Protected><DashboardPage /></Protected>} />

      {/* Student Routes */}
      <Route path="/practice-interviews" element={<Protected roles={["student"]}><StudentPracticeInterviewsPage /></Protected>} />
      <Route path="/interviews" element={<Protected roles={["student"]}><StudentPracticeInterviewsPage /></Protected>} />
      <Route path="/rapidfire" element={<Protected roles={["student"]}><StudentRapidFirePage /></Protected>} />
      <Route path="/my-progress" element={<Protected roles={["student"]}><StudentMyProgressPage /></Protected>} />
      <Route path="/progress" element={<Protected roles={["student"]}><StudentMyProgressPage /></Protected>} />
      <Route path="/feedback" element={<Protected roles={["student"]}><StudentFeedbackPage /></Protected>} />

      {/* Teacher Routes */}
      <Route path="/teacher/students" element={<Protected roles={["teacher"]}><TeacherStudents /></Protected>} />
      <Route path="/teacher/interviews" element={<Protected roles={["teacher"]}><TeacherInterviews /></Protected>} />
      <Route path="/teacher/evaluations" element={<Protected roles={["teacher"]}><TeacherEvaluations /></Protected>} />
      <Route path="/teacher/question-bank" element={<Protected roles={["teacher"]}><TeacherQuestionBank /></Protected>} />
      <Route path="/teacher/rubrics" element={<Protected roles={["teacher"]}><TeacherRubrics /></Protected>} />
      <Route path="/teacher/reports" element={<Protected roles={["teacher"]}><TeacherReports /></Protected>} />

      {/* Admin Routes */}
      <Route path="/admin/users" element={<Protected roles={["admin"]}><AdminUsers /></Protected>} />
      <Route path="/admin/reports" element={<Protected roles={["admin"]}><AdminReports /></Protected>} />
      <Route path="/admin/analytics" element={<Protected roles={["admin"]}><AdminAnalytics /></Protected>} />
      <Route path="/admin/settings" element={<Protected roles={["admin"]}><AdminSettings /></Protected>} />

      <Route path="/interviews/:interviewId" element={<Protected roles={["student"]}><InterviewPage /></Protected>} />
      <Route path="/interviews/:interviewId/report" element={<Protected roles={["student", "teacher", "admin"]}><ReportPage /></Protected>} />
      <Route path="*" element={<Navigate to={user ? "/dashboard" : "/login"} replace />} />
    </Routes>
  );
}

export default App;
