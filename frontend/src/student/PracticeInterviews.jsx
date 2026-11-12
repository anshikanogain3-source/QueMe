import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BriefcaseBusiness,
  Calendar,
  CheckCircle2,
  Clock3,
  FileBarChart2,
  Filter,
  Play,
  RotateCcw,
  Search,
  User,
} from "lucide-react";
import { api } from "../api.js";
import { StudentWorkspace } from "./StudentWorkspace.jsx";

export function PracticeInterviews({ user }) {
  const [interviews, setInterviews] = useState([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all"); // 'all' | 'ready' | 'completed'
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setBusy(true);
    api("/interviews")
      .then((data) => {
        if (active) setInterviews(data || []);
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

  const counts = useMemo(() => {
    const ready = interviews.filter(
      (i) => i.status === "SCHEDULED" || i.status === "IN_PROGRESS"
    ).length;
    const completed = interviews.filter((i) => i.status === "COMPLETED").length;
    return { all: interviews.length, ready, completed };
  }, [interviews]);

  const filteredInterviews = useMemo(() => {
    let list = interviews;

    if (statusFilter === "ready") {
      list = list.filter(
        (i) => i.status === "SCHEDULED" || i.status === "IN_PROGRESS"
      );
    } else if (statusFilter === "completed") {
      list = list.filter((i) => i.status === "COMPLETED");
    }

    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(
        (i) =>
          (i.template_title && i.template_title.toLowerCase().includes(q)) ||
          (i.teacher_name && i.teacher_name.toLowerCase().includes(q))
      );
    }

    return list;
  }, [interviews, statusFilter, searchTerm]);

  return (
    <StudentWorkspace
      user={user}
      active="interviews"
      pageTitle="Practice Interviews"
      pageSubtitle="Assigned Sessions"
      searchPlaceholder="Search interviews or teachers..."
      searchValue={searchTerm}
      onSearchChange={setSearchTerm}
    >
      <div className="practice-interviews-page">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* Toolbar: Filters and Search Stats */}
        <div className="practice-toolbar">
          <div className="filter-tabs" role="tablist" aria-label="Interview status filters">
            <button
              type="button"
              role="tab"
              aria-selected={statusFilter === "all"}
              className={`filter-tab${statusFilter === "all" ? " active" : ""}`}
              onClick={() => setStatusFilter("all")}
            >
              All Interviews <span className="tab-count">{counts.all}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={statusFilter === "ready"}
              className={`filter-tab${statusFilter === "ready" ? " active" : ""}`}
              onClick={() => setStatusFilter("ready")}
            >
              Ready to Practice <span className="tab-count">{counts.ready}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={statusFilter === "completed"}
              className={`filter-tab${statusFilter === "completed" ? " active" : ""}`}
              onClick={() => setStatusFilter("completed")}
            >
              Completed <span className="tab-count">{counts.completed}</span>
            </button>
          </div>

          <div className="toolbar-status">
            <span>
              Showing {filteredInterviews.length} of {interviews.length} session
              {interviews.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        {/* Interviews List / Cards */}
        {busy ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Loading assigned interviews…</span>
          </div>
        ) : filteredInterviews.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <BriefcaseBusiness size={24} />
            </div>
            <h3>
              {searchTerm || statusFilter !== "all"
                ? "No matching interviews found"
                : "No interviews scheduled yet"}
            </h3>
            <p>
              {searchTerm || statusFilter !== "all"
                ? "Try adjusting your search query or switching to another filter tab."
                : "Your instructors will schedule interview practice assignments here."}
            </p>
            {(searchTerm || statusFilter !== "all") && (
              <button
                type="button"
                className="button button-outline button-small"
                onClick={() => {
                  setSearchTerm("");
                  setStatusFilter("all");
                }}
              >
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <div className="interviews-grid">
            {filteredInterviews.map((item) => {
              const isDone = item.status === "COMPLETED";
              const isRunning = item.status === "IN_PROGRESS";
              const dateLabel = item.scheduled_at
                ? new Date(item.scheduled_at).toLocaleDateString([], {
                    dateStyle: "medium",
                  })
                : "Schedule open";
              const timeLabel = item.scheduled_at
                ? new Date(item.scheduled_at).toLocaleTimeString([], {
                    timeStyle: "short",
                  })
                : "";

              return (
                <article key={item.interview_id} className="interview-saas-card">
                  <div className="card-topline">
                    <span
                      className={`status-pill status-${item.status.toLowerCase()}`}
                    >
                      {item.status.replaceAll("_", " ")}
                    </span>
                    {isDone && item.final_score != null && (
                      <span className="card-score-badge">
                        Score: <strong>{item.final_score}/10</strong>
                      </span>
                    )}
                  </div>

                  <div className="card-body">
                    <h2 className="card-title">
                      {item.template_title || "Practice Interview"}
                    </h2>

                    <div className="card-meta">
                      <div className="meta-row">
                        <User size={13} aria-hidden="true" />
                        <span>
                          Assigned by{" "}
                          <strong>{item.teacher_name || "Instructor"}</strong>
                        </span>
                      </div>
                      <div className="meta-row">
                        <Calendar size={13} aria-hidden="true" />
                        <span>
                          {dateLabel} {timeLabel ? `· ${timeLabel}` : ""}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="card-actions">
                    {isDone ? (
                      <button
                        type="button"
                        className="button button-outline button-wide"
                        onClick={() =>
                          navigate(`/interviews/${item.interview_id}/report`)
                        }
                      >
                        <FileBarChart2 size={14} aria-hidden="true" />
                        <span>View Evaluation Report</span>
                        <ArrowRight size={13} aria-hidden="true" />
                      </button>
                    ) : isRunning ? (
                      <button
                        type="button"
                        className="button button-primary button-wide"
                        onClick={() =>
                          navigate(`/interviews/${item.interview_id}`)
                        }
                      >
                        <RotateCcw size={14} aria-hidden="true" />
                        <span>Continue Practice</span>
                        <ArrowRight size={13} aria-hidden="true" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="button button-primary button-wide"
                        onClick={() =>
                          navigate(`/interviews/${item.interview_id}`)
                        }
                      >
                        <Play size={14} aria-hidden="true" />
                        <span>Start Interview</span>
                        <ArrowRight size={13} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </StudentWorkspace>
  );
}

