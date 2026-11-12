import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BriefcaseBusiness,
  GraduationCap,
  Mail,
  Search,
  UserCheck,
  Users,
} from "lucide-react";
import { api } from "../api.js";
import { TeacherWorkspace } from "./TeacherWorkspace.jsx";

export function TeacherStudents({ user }) {
  const [cohorts, setCohorts] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState("");
  const [students, setStudents] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    Promise.all([api("/admin/semesters"), api("/interviews")])
      .then(([cohortRows, interviewRows]) => {
        if (!active) return;
        const validCohorts = (cohortRows || []).filter((c) => c.academic_year);
        setCohorts(validCohorts);
        setInterviews(interviewRows || []);
        if (validCohorts.length > 0) {
          setSelectedBatch(String(validCohorts[0].batch_id));
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedBatch) {
      setStudents([]);
      return;
    }
    let active = true;
    setBusy(true);
    api(`/teacher/students?batch_id=${selectedBatch}`)
      .then((data) => {
        if (active) setStudents(data || []);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
    };
  }, [selectedBatch]);

  const filteredStudents = useMemo(() => {
    if (!searchTerm.trim()) return students;
    const q = searchTerm.toLowerCase();
    return students.filter(
      (s) =>
        (s.full_name && s.full_name.toLowerCase().includes(q)) ||
        (s.email && s.email.toLowerCase().includes(q)) ||
        (s.roll_number && s.roll_number.toLowerCase().includes(q))
    );
  }, [students, searchTerm]);

  return (
    <TeacherWorkspace
      user={user}
      active="students"
      pageTitle="My Students"
      pageSubtitle="Cohort Directory & Student Management"
      searchPlaceholder="Search by name, roll number, or email..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="teacher-students-page">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* Toolbar: Batch Filter & Student Counts */}
        <div className="practice-toolbar">
          <div className="selector-copy">
            <span className="selector-label">Class Group / Cohort:</span>
            <select
              value={selectedBatch}
              onChange={(e) => setSelectedBatch(e.target.value)}
              className="session-select-dropdown"
              aria-label="Filter students by class group"
            >
              {cohorts.map((cohort) => (
                <option key={cohort.batch_id} value={cohort.batch_id}>
                  {cohort.course_name || cohort.course_id} · {cohort.semester} · {cohort.academic_year}
                </option>
              ))}
            </select>
          </div>

          <div className="toolbar-status">
            <span>
              Showing {filteredStudents.length} of {students.length} student
              {students.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {/* Students Table */}
        {busy ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Loading student cohort…</span>
          </div>
        ) : filteredStudents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <Users size={24} />
            </div>
            <h3>
              {searchTerm
                ? "No matching students found"
                : "No students registered in this class group"}
            </h3>
            <p>
              {searchTerm
                ? "Try searching with a different student name, email, or roll number."
                : "Students who register with this class group will automatically appear here."}
            </p>
          </div>
        ) : (
          <section className="overview-panel">
            <div className="history-table-wrapper">
              <table className="saas-table">
                <thead>
                  <tr>
                    <th>Student Name</th>
                    <th>Roll Number</th>
                    <th>Email</th>
                    <th>Course & Semester</th>
                    <th>Interviews Assigned</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStudents.map((s) => {
                    const initials = s.full_name
                      ? s.full_name
                          .split(" ")
                          .map((n) => n[0])
                          .slice(0, 2)
                          .join("")
                          .toUpperCase()
                      : "S";

                    return (
                      <tr key={s.user_id}>
                        <td>
                          <div className="table-user-cell">
                            <span className="table-avatar">{initials}</span>
                            <strong>{s.full_name}</strong>
                          </div>
                        </td>
                        <td>{s.roll_number || "—"}</td>
                        <td>
                          <span className="table-email-link">{s.email}</span>
                        </td>
                        <td>
                          {s.course ? `${s.course} · ${s.semester || ""}` : "General"}
                        </td>
                        <td>
                          <span className="table-score-badge">
                            {s.teacher_interview_count} assigned
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            className="button button-outline button-small"
                            onClick={() =>
                              navigate(`/teacher/interviews?tab=assign&student_id=${s.user_id}`)
                            }
                          >
                            <BriefcaseBusiness size={13} />
                            <span>Assign Practice</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </TeacherWorkspace>
  );
}

