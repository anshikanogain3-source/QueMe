import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  BarChart3,
  BriefcaseBusiness,
  ChevronDown,
  FileBarChart2,
  House,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
  X,
} from "lucide-react";
import { useAuth } from "../auth.jsx";
import { Brand } from "../Brand.jsx";

const NAV_ITEMS = [
  { id: "dashboard", label: "Dashboard", path: "/dashboard", Icon: House },
  { id: "interviews", label: "Practice Interviews", path: "/practice-interviews", Icon: BriefcaseBusiness },
  { id: "rapidfire", label: "RapidFire", path: "/rapidfire", Icon: Activity },
  { id: "progress", label: "My Progress", path: "/my-progress", Icon: BarChart3 },
  { id: "feedback", label: "Feedback", path: "/feedback", Icon: FileBarChart2 },
];

export function StudentWorkspace({
  user,
  active = "dashboard",
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
    : "Q";

  return (
    <div className="student-app">
      {sidebarOpen && (
        <button
          className="student-sidebar-backdrop"
          aria-label="Close navigation"
          type="button"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Primary Left Sidebar Navigation */}
      <aside className={`student-sidebar${sidebarOpen ? " is-open" : ""}`}>
        <div className="student-sidebar-top">
          <Brand to="/dashboard" className="student-brand" />
          <button
            className="student-sidebar-close"
            type="button"
            aria-label="Close menu"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="student-side-nav" aria-label="Student workspace">
          {NAV_ITEMS.map(({ id, label, path, Icon }) => {
            const isActive = active === id;
            return (
              <Link
                key={id}
                to={path}
                className={`student-side-link${isActive ? " active" : ""}`}
                aria-current={isActive ? "page" : undefined}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={17} aria-hidden="true" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="student-sidebar-note">
          <span className="student-sidebar-note-icon">
            <ShieldCheck size={20} />
          </span>
          <p>
            Practice with purpose.
            <br />
            Progress with confidence.
          </p>
          <small>QueMe · Campus training</small>
        </div>

        <button className="student-signout" type="button" onClick={logout}>
          <LogOut size={16} aria-hidden="true" />
          <span>Sign out</span>
        </button>
      </aside>

      {/* Main Content Shell with Sticky Topbar */}
      <div className="student-content">
        <header className="student-topbar">
          <div className="student-topbar-left">
            <button
              className="student-menu-toggle"
              type="button"
              aria-label="Toggle navigation menu"
              onClick={() => setSidebarOpen((prev) => !prev)}
            >
              <Menu size={18} />
            </button>
            <div className="student-topbar-titles">
              <h1 className="student-topbar-title">{pageTitle || "Dashboard"}</h1>
              {pageSubtitle && <span className="student-topbar-subtitle">{pageSubtitle}</span>}
            </div>
          </div>

          <div className="student-topbar-center">
            {onSearchChange ? (
              <div className="student-topbar-search">
                <Search size={15} className="search-icon" aria-hidden="true" />
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
              <div className="student-topbar-badge">
                <span className="badge-pulse" />
                <span>Practice Workspace</span>
              </div>
            )}
          </div>

          <div className="student-topbar-right">
            {actions}
            <details className="student-profile-menu">
              <summary aria-haspopup="menu" aria-label="Student profile menu">
                <span className="student-avatar">{initials}</span>
                <span className="student-profile-copy">
                  <strong>{user?.full_name}</strong>
                  <small>Student</small>
                </span>
                <ChevronDown size={14} className="profile-chevron" aria-hidden="true" />
              </summary>
              <div className="student-profile-dropdown" role="menu">
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
                  <House size={14} />
                  <span>Dashboard Overview</span>
                </button>
                <button
                  type="button"
                  className="profile-dropdown-item"
                  onClick={() => navigate("/practice-interviews")}
                >
                  <BriefcaseBusiness size={14} />
                  <span>My Interviews</span>
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

        <main className="student-main">{children}</main>
      </div>
    </div>
  );
}

