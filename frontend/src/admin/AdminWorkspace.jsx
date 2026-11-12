import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart3,
  ChevronDown,
  FileBarChart2,
  FileText,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings2,
  ShieldCheck,
  TrendingUp,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../auth.jsx";
import { Brand } from "../Brand.jsx";

const ADMIN_NAV = [
  { id: "overview", label: "Dashboard", path: "/dashboard", Icon: LayoutDashboard },
  { id: "users", label: "User Management", path: "/admin/users", Icon: Users },
  { id: "reports", label: "Interview Reports", path: "/admin/reports", Icon: FileBarChart2 },
  { id: "analytics", label: "Platform Analytics", path: "/admin/analytics", Icon: TrendingUp },
  { id: "settings", label: "System & Cohorts", path: "/admin/settings", Icon: Settings2 },
];

export function AdminWorkspace({
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
    : "A";

  return (
    <div className="admin-app">
      {sidebarOpen && (
        <button
          className="admin-sidebar-backdrop"
          aria-label="Close navigation"
          type="button"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Primary Left Navigation */}
      <aside className={`admin-sidebar${sidebarOpen ? " is-open" : ""}`}>
        <div className="admin-sidebar-top">
          <Brand to="/dashboard" className="admin-brand" />
          <button
            className="admin-sidebar-close"
            type="button"
            aria-label="Close menu"
            onClick={() => setSidebarOpen(false)}
          >
            <X size={18} />
          </button>
        </div>

        <nav className="admin-side-nav" aria-label="Campus administration navigation">
          {ADMIN_NAV.map(({ id, label, path, Icon }) => {
            const isActive = active === id;
            return (
              <Link
                key={id}
                to={path}
                className={`admin-side-link${isActive ? " active" : ""}`}
                aria-current={isActive ? "page" : undefined}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={17} className="admin-side-icon" aria-hidden="true" />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="admin-sidebar-note">
          <span className="admin-sidebar-shield" aria-hidden="true">
            <ShieldCheck size={19} />
          </span>
          <p>
            Campus governance &amp;
            <br />
            institutional controls.
          </p>
          <span className="admin-note-line" />
        </div>

        <button className="admin-signout" type="button" onClick={logout}>
          <LogOut size={16} aria-hidden="true" />
          <span>Sign out</span>
        </button>
      </aside>

      {/* Main Content Area */}
      <div className="admin-content">
        <header className="admin-topbar">
          <div className="admin-topbar-left">
            <button
              className="admin-menu-button"
              type="button"
              aria-label="Toggle navigation menu"
              onClick={() => setSidebarOpen((prev) => !prev)}
            >
              <Menu size={18} />
            </button>
            <div className="admin-topbar-titles">
              <h1 className="admin-topbar-title">{pageTitle || "Platform Administration"}</h1>
              {pageSubtitle && <span className="admin-topbar-subtitle">{pageSubtitle}</span>}
            </div>
          </div>

          <div className="admin-topbar-center">
            {onSearchChange ? (
              <div className="admin-search">
                <Search size={15} className="admin-search-icon" aria-hidden="true" />
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
              <div className="admin-topbar-badge">
                <span className="badge-pulse admin" />
                <span>Enterprise Platform Control</span>
              </div>
            )}
          </div>

          <div className="admin-topbar-right">
            {actions}
            <details className="admin-profile-menu">
              <summary aria-haspopup="menu" aria-label="Administrator profile menu">
                <span className="avatar admin-avatar">{initials}</span>
                <span className="admin-profile-copy">
                  <strong>{user?.full_name}</strong>
                  <small>Administrator</small>
                </span>
                <ChevronDown size={14} className="profile-chevron" aria-hidden="true" />
              </summary>
              <div className="admin-profile-dropdown" role="menu">
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
                  <LayoutDashboard size={14} />
                  <span>Overview</span>
                </button>
                <button
                  type="button"
                  className="profile-dropdown-item"
                  onClick={() => navigate("/admin/users")}
                >
                  <Users size={14} />
                  <span>User Management</span>
                </button>
                <button
                  type="button"
                  className="profile-dropdown-item"
                  onClick={() => navigate("/admin/settings")}
                >
                  <Settings2 size={14} />
                  <span>System Settings</span>
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

        <main className="admin-main">{children}</main>
      </div>
    </div>
  );
}

