// Role-pages: maps each role to its workspace shell and route.
import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import AdminLayout from "./AdminLayout.jsx";
import { RequireRole } from "./RoleLayouts.jsx";

/** Admin workspace: full management shell with protected routes. */
export function AdminLayoutWrapper() {
  return <AdminLayout><Outlet /></AdminLayout>;
}

/** Admin routes.  Every route below is mounted inside AdminLayout and is
 *  additionally protected by the server (require_admin + DB RLS).  Nothing
 *  here relies on which items the sidebar shows. */
export default function AdminRoutes() {
  return (
    <RequireRole session={null} allowedRole="admin">
      <AdminLayoutWrapper />
      <Outlet />
    </RequireRole>
  );
}
