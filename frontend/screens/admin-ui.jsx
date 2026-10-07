// Shared admin UI widgets: paginated table, actions, empty state, confirm.
import React from "react";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  Notice,
  Skeleton,
} from "../design-system/index.js";

export function EmptyStateAction({ title, message, action, actionLabel = "Go to" }) {
  return (
    <EmptyState
      icon="＋"
      title={title}
      message={message}
      action={<Button variant="primary" onClick={action}>{actionLabel}</Button>}
    />
  );
}

/** Status pill for a known set of statuses. */
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

/** Pagination control for a paged admin list. */
export function Pager({ page, page_size, total, onPage, currentLabel = "Page", ariaLabel = "Pagination" }) {
  const totalPages = Math.max(1, Math.ceil((total || 0) / (page_size || 1)) || 1);
  const [show, setShow] = React.useState(5);
  React.useEffect(() => {
    const density = window.innerWidth < 760 ? 3 : 5;
    setShow(density);
  }, []);
  const pages = React.useMemo(() => {
    const range = [];
    const start = Math.max(1, page - 1);
    const end = Math.min(totalPages, page + 1);
    for (let i = start; i <= end; i += 1) range.push(i);
    return range;
  }, [page, totalPages]);
  return (
    <nav aria-label={ariaLabel} className="qm-pagination">
      <ul className="qm-pagination__list">
        <li>
          <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
            « Previous
          </Button>
        </li>
        {pages.map((p) => (
          <li key={p}>
            <Button variant={p === page ? "primary" : "ghost"} size="sm" active={p === page} onClick={() => onPage(p)}>
              {p}
            </Button>
          </li>
        ))}
        <li>
          <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => onPage(page + 1)} aria-label="Next page">
            Next «
          </Button>
        </li>
      </ul>
      <span className="qm-pagination__meta">
        {currentLabel} {page} of {totalPages} · {total} result{total !== 1 ? "s" : ""}
      </span>
    </nav>
  );
}

/** Thin wrapper for a two-step destructive action. */
export function ConfirmDialog({ open, title, message, confirmLabel, cancelLabel, tone = "danger", onConfirm, onCancel }) {
  const [ack, setAck] = React.useState("");
  const submitting = ack.length > 0;
  const submit = React.useCallback(() => {
    if (ack.trim().toLowerCase() !== "confirm" && ack.trim().toLowerCase() !== "yes") return;
    onConfirm();
  }, [ack, onConfirm]);
  return (
    <Dialog open={open} onClose={onCancel} title={title} description={message} size="sm">
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--qm-space-3)", marginTop: "var(--qm-space-6)" }}>
        <Button variant="secondary" onClick={onCancel} disabled={submitting}>
          {cancelLabel}
        </Button>
        <Button
          variant="danger"
          onClick={submit}
          loading={submitting}
          disabled={ack.trim().length === 0}
          aria-describedby="confirm-ack-help"
        >
          {confirmLabel}
        </Button>
        <p id="confirm-ack-help" className="qm-field__hint">
          Type <kbd className="qm-field__req">confirm</kbd> to acknowledge.
        </p>
      </div>
    </Dialog>
  );
}

/** Shared toast hooks wired to a globally-provided notification system. */
export function useAdminToast({ onShowError, onShowSuccess }) {
  return {
    showError: (err) => {
      if (err?.status === 401 || err?.status === 403) {
        onShowError("Your session expired or you do not have permission to make this change. Please sign in again.");
        return;
      }
      const msg = err?.data?.detail || err?.message || "Something went wrong.";
      onShowError(msg);
    },
    showSuccess: (msg) => onShowSuccess(msg),
  };
}
