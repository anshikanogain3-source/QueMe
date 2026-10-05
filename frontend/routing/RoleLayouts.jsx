import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import "./roleLayouts.css";

function RoleFrame({ role, title }) {
  return (
    <main className={`role-layout role-layout-${role}`}>
      <header className="role-layout-header">
        <a className="role-layout-brand" href="/">QueMe</a>
        <span>{title}</span>
      </header>
      <Outlet />
    </main>
  );
}

export function RequireRole({ session, allowedRole }) {
  if (!session) return <Navigate to="/login" replace />;
  if (session.role !== allowedRole) return <Navigate to={`/${session.role}`} replace />;
  return <Outlet />;
}

export function StudentLayout() {
  return <div className="student-route-layout"><Outlet /></div>;
}

export function TeacherLayout() {
  return <RoleFrame role="teacher" title="Teacher workspace" />;
}

export function CoordinatorLayout() {
  return <RoleFrame role="coordinator" title="Coordinator workspace" />;
}

export function AdminLayout() {
  return <RoleFrame role="admin" title="Administration" />;
}
