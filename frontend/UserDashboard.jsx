import React from "react";
import "./UserDashboard.css";

export default function UserDashboard({ onLogout }) {
  return (
    <main className="student-dashboard">
      <header className="student-dashboard__header">
        <a href="/student" className="student-dashboard__brand">QueMe</a>
        <button className="student-dashboard__logout" type="button" onClick={onLogout}>Log out</button>
      </header>
      <section className="student-dashboard__empty" aria-labelledby="student-dashboard-title">
        <p>Student workspace</p>
        <h1 id="student-dashboard-title">Your interview records will appear here.</h1>
        <span>
          No local practice data is stored in this application. Assigned interviews, reports, and feedback
          will appear after the secure backend workflow is connected.
        </span>
      </section>
    </main>
  );
}
