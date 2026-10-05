import React from "react";
import { Link } from "react-router-dom";

function PlaceholderPage({ title, scope, onLogout }) {
  return (
    <section className="role-layout-content" aria-labelledby="role-page-title">
      <p>Foundation route</p>
      <h1 id="role-page-title">{title}</h1>
      <p>{scope}</p>
      <p>This route is a UI foundation only. Server-side authentication and scope authorization are not configured yet.</p>
      <button className="btn btn-primary" type="button" onClick={onLogout}>Log out</button>
      <Link to="/login">Return to sign-in</Link>
    </section>
  );
}

export function TeacherPlaceholder({ onLogout }) {
  return <PlaceholderPage title="Teacher workspace" scope="Assigned-student review is not implemented yet." onLogout={onLogout} />;
}

export function CoordinatorPlaceholder({ onLogout }) {
  return <PlaceholderPage title="Coordinator workspace" scope="Assigned-class and course reporting is not implemented yet." onLogout={onLogout} />;
}

export function AdminPlaceholder({ onLogout }) {
  return <PlaceholderPage title="Administration" scope="Account management and department analytics are not implemented yet." onLogout={onLogout} />;
}
