import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  FileBarChart2,
  FilePlus2,
  LogOut,
  Menu,
  Search,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../auth.jsx";
import { Brand } from "../Brand.jsx";

const TEACHER_NAV = [
  { id: "overview", label: "Dashboard", path: "/dashboard", Icon: BarChart3 },
  { id: "students", label: "My Students", path: "/teacher/students", Icon: Users },
  { id: "interviews", label: "Interview Management", path: "/teacher/interviews", Icon: BriefcaseBusiness },
  { id: "evaluations", label: "Assessments & Reviews", path: "/teacher/evaluations", Icon: ClipboardCheck },
  { id: "questions", label: "Question Bank", path: "/teacher/question-bank", Icon: BookOpen },
  { id: "rubrics", label: "Rubrics", path: "/teacher/rubrics", Icon: ClipboardList },
  { id: "reports", label: "Reports & Analytics", path: "/teacher/reports", Icon: FileBarChart2 },
];

export function TeacherWorkspace({
  user,
  active = "overview",
  pageTitle,
  pageSubtitle,
  searchPlaceholder,
  searchValue,
  onSearchChange,
  actions,
  children,
}) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const handleKey = (e) => {
      if (e.key === "Escape") setSidebarOpen(false);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [sidebarOpen]);

  const initials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((p) => p[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "T";

  return (
    <div className="teacher-app">
      {sidebarOpen && (
        <button
          className="teacher-sidebar-backdrop"
          aria-label="Close navigation"
          type="button"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Primary Left Sidebar Navigation */}
      <aside className={`teacher-sidebar${sidebarOpen ? " is-open" : ""}`}>
        <div className="teacher-sidebar-top">
          <Brand to="/dashboard" className="teacher-sidebar-brand" />
          <button
            className="teacher-sidebar-close"
            type="button"
            aria-label="Close menu"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="teacher-side-nav" aria-label="Teacher workspace navigation">
          {TEACHER_NAV.map(({ id, label, path, Icon }) => {
            const isActive = active === id;
            return (
              <Link
                key={id}
                to={path}
                className={`teacher-side-link${isActive ? " active" : ""}`}
                aria-current={isActive ? "page" : undefined}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={17} className="teacher-side-icon" aria-hidden="true" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="teacher-sidebar-note">
          <span className="teacher-sidebar-sprout" aria-hidden="true">
            <Users size={19} />
          </span>
          <p>
            Support every student’s
            <br />
            next opportunity.
          </p>
          <span className="teacher-note-line" />
        </div>

        <button className="teacher-signout" type="button" onClick={logout}>
          <LogOut size={16} aria-hidden="true" />
          <span>Sign out</span>
        </button>
      </aside>

      {/* Main Content Shell with Sticky Topbar */}
      <div className="teacher-content">
        <header className="teacher-topbar">
          <div className="teacher-topbar-left">
            <button
              className="teacher-menu-button"
              type="button"
              aria-label="Toggle navigation menu"
              onClick={() => setSidebarOpen((prev) => !prev)}
            >
              <Menu size={18} />
            </button>
            <div className="teacher-topbar-titles">
              <h1 className="teacher-topbar-title">{pageTitle || "Teacher Dashboard"}</h1>
              {pageSubtitle && <span className="teacher-topbar-subtitle">{pageSubtitle}</span>}
            </div>
          </div>

          <div className="teacher-topbar-center">
            {onSearchChange ? (
              <div className="teacher-search">
                <Search size={15} className="teacher-search-icon" aria-hidden="true" />
                <input
                  type="text"
                  value={searchValue || ""}
                  onChange={(e) => onSearchChange(e.target.value)}
                  placeholder={searchPlaceholder || "Search..."}
                  aria-label={searchPlaceholder || "Search"}
                />
                {searchValue && (
                  <button
                    type="button"
                    className="search-clear-btn"
                    onClick={() => onSearchChange("")}
                    aria-label="Clear search"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
            ) : (
              <div className="teacher-topbar-badge">
                <span className="badge-pulse" />
                <span>Faculty Assessment Portal</span>
              </div>
            )}
          </div>

          <div className="teacher-topbar-right">
            {actions}
            <details className="teacher-profile-menu">
              <summary aria-haspopup="menu" aria-label="Teacher profile menu">
                <span className="teacher-avatar">{initials}</span>
                <span className="teacher-profile-copy">
                  <strong>{user?.full_name}</strong>
                  <small>Instructor</small>
                </span>
                <ChevronDown size={14} className="profile-chevron" aria-hidden="true" />
              </summary>
              <div className="teacher-profile-dropdown" role="menu">
                <div className="profile-dropdown-header">
                  <strong>{user?.full_name}</strong>
                  <span>{user?.email}</span>
                </div>
                <div className="profile-dropdown-divider" />
                <button
                  type="button"
                  className="profile-dropdown-item"
                  onClick={() => navigate("/dashboard")}
                >
                  <BarChart3 size={14} />
                  <span>Overview</span>
                </button>
                <button
                  type="button"
                  className="profile-dropdown-item"
                  onClick={() => navigate("/teacher/interviews")}
                >
                  <FilePlus2 size={14} />
                  <span>Interview Management</span>
                </button>
                <div className="profile-dropdown-divider" />
                <button
                  type="button"
                  className="profile-dropdown-item signout-item"
                  onClick={logout}
                >
                  <LogOut size={14} />
                  <span>Sign out</span>
                </button>
              </div>
            </details>
          </div>
        </header>

        <main className="teacher-main">{children}</main>
      </div>
    </div>
  );
}

