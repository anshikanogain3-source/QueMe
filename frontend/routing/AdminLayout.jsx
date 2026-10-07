// Admin management shell.
//
// Sidebar navigation is the source of truth for which management screens are
// reachable.  There is no hidden navigation: every route below is mounted and
// protected by the server.  Each screen is a plain presentational component
// that never bypasses the FastAPI backend.
import React from "react";
import { useLocation } from "react-router-dom";
import {
  AppNav,
  AppShell,
  Badge,
  Button,
  PageHeader,
  Skeleton,
} from "../design-system/index.js";

const sections = [
  { id: "accounts", label: "Accounts", icon: "ⓘ", href: "/admin/accounts" },
  { id: "academic", label: "Academic structure", icon: "📐", href: "/admin/academic" },
  { id: "people", label: "People", icon: "👥", href: "/admin/people" },
  { id: "interviews", label: "Interviews", icon: "🎙️", href: "/admin/interviews" },
  { id: "audit", label: "Audit log", icon: "📋", href: "/admin/audit" },
];

const navBySection = {
  accounts: [
    { id: "accounts", label: "Accounts", href: "/admin/accounts" },
    { id: "invitations", label: "Invitations", href: "/admin/invitations" },
    { id: "invite", label: "Invite new", href: "/admin/accounts?mode=invite" },
  ],
  academic: [
    { id: "departments", label: "Departments", href: "/admin/academic/departments" },
    { id: "courses", label: "Courses", href: "/admin/academic/courses" },
    { id: "semesters", label: "Semesters", href: "/admin/academic/semesters" },
    { id: "batches", label: "Batches", href: "/admin/academic/batches" },
    { id: "classes", label: "Classes", href: "/admin/academic/classes" },
  ],
  people: [
    { id: "enrollments", label: "Enrollments", href: "/admin/people/enrollments" },
    { id: "teacher-assignments", label: "Teacher assignments", href: "/admin/people/teacher-assignments" },
    { id: "coordinator-assignments", label: "Coordinator scope", href: "/admin/people/coordinator-assignments" },
  ],
  interviews: [
    { id: "assignments", label: "Assignments", href: "/admin/interviews/assignments" },
  ],
  audit: [],
};

const sectionTitle = {
  accounts: "Accounts",
  academic: "Academic structure",
  people: "People",
  interviews: "Interviews",
  audit: "Audit log",
};

const sectionSubtitle = {
  accounts: "Invite, activate, and deactivate students, teachers, and coordinators.",
  academic: "Set up departments, courses, semesters, batches, and classes.",
  people: "Manage enrollments, teacher and coordinator assignments.",
  interviews: "View and manage interview assignments and deadlines.",
  audit: "Review the administrative audit trail.",
};

/** Constrained status pill used in the admin shell. */
export function StatusPill({ status, tone }) {
  const map = {
    active: { tone: "success", label: "Active" },
    inactive: { tone: "neutral", label: "Inactive" },
    pending: { tone: "amber", label: "Pending" },
    invited: { tone: "neutral", label: "Invited" },
    assigned: { tone: "info", label: "Assigned" },
    in_progress: { tone: "accent", label: "In progress" },
    completed: { tone: "success", label: "Completed" },
    cancelled: { tone: "danger", label: "Cancelled" },
  };
  const resolvedTone = tone || map[status]?.tone || "neutral";
  const resolvedLabel = tone || map[status]?.label || status || "--";
  return <Badge tone={resolvedTone} size="sm">{resolvedLabel}</Badge>;
}

/** Resolve the secondary title + subtitle for the current admin route. */
export function useAdminTitle() {
  const location = useLocation();
  const header = React.useMemo(() => {
    const p = location.pathname.split("/");
    if (p[2] === "academic") {
      switch (p[3]) {
        case "departments": return "Departments";
        case "courses": return "Courses";
        case "semesters": return "Semesters";
        case "batches": return "Batches";
        case "classes": return "Classes";
        default: return "Academic structure";
      }
    }
    if (p[2] === "people") {
      switch (p[3]) {
        case "enrollments": return "Enrollments";
        case "teacher-assignments": return "Teacher assignments";
        case "coordinator-assignments": return "Coordinator scope";
        default: return "People";
      }
    }
    if (p[2] === "interviews") {
      if (p[3] === "assignments") return "Interview assignments";
      return "Interviews";
    }
    switch (p[2]) {
      case "accounts": return "Accounts";
      case "audit": return "Audit log";
      default: return "Administration";
    }
  }, [location.pathname]);
  const subtitle = React.useMemo(() => {
    if (location.search.includes("mode=invite")) return "Send an invitation for a new account (pending until activated).";
    return sectionSubtitle[location.pathname.split("/")[2]] || "Manage roles, academic structure, enrollments, and schedules.";
  }, [location.search, location.pathname]);
  return { header, subtitle };
}

export default function AdminLayout({ children }) {
  const location = useLocation();
  const { header, subtitle } = useAdminTitle();
  const section = React.useMemo(() => sections.find((s) => s.href === location.pathname) || sections[0], [location.pathname]);

  return (
    <AppShell
      nav={sections.map((s) => ({
        icon: s.icon,
        label: s.label,
        active: location.pathname === s.href,
        href: s.href,
      }))}
      currentPath={location.pathname}
      topbarTitle={header}
      topbarSubtitle={subtitle}
      topbarActions={
        <div className="qm-appshell__actions">
          <Button variant="ghost" size="sm" onClick={() => {}}>
            Export report
          </Button>
          <Button variant="secondary" size="sm" onClick={() => {}}>
            Settings
          </Button>
        </div>
      }
    >
      <div className="qm-appshell__content">{children}</div>
    </AppShell>
  );
}
