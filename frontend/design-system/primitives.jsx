import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import "./tokens.css";
import "./components.css";

/* Small class-name joiner. */
export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ */
/* Form field context                                                  */
/* ------------------------------------------------------------------ */

const FieldContext = createContext(null);

let fieldSeq = 0;
function nextFieldId() {
  fieldSeq += 1;
  return `qm-field-${fieldSeq}`;
}

/** Wraps a single control, wiring label/hint/error ids and aria. */
export function Field({ label, hint, error, id, required = false, children, className }) {
  const generatedId = useId();
  const controlId = id || generatedId;
  const hintId = hint ? `${controlId}-hint` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;

  return (
    <FieldContext.Provider value={{ controlId, describedBy: [hintId, errorId].filter(Boolean).join(" ") || undefined, invalid: Boolean(error), required }}>
      <div className={cx("qm-field", className)}>
        {label && (
          <label className="qm-field__label" htmlFor={controlId}>
            {label}
            {required && <span className="qm-field__req" aria-hidden="true"> *</span>}
          </label>
        )}
        {children}
        {hint && <p className="qm-field__hint" id={hintId}>{hint}</p>}
        {error && <p className="qm-field__error" id={errorId} role="alert">{error}</p>}
      </div>
    </FieldContext.Provider>
  );
}

function useFieldProps() {
  const ctx = useContext(FieldContext);
  if (!ctx) return {};
  return { id: ctx.controlId, "aria-describedby": ctx.describedBy, "aria-invalid": ctx.invalid || undefined, required: ctx.required };
}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */

export const Button = React.forwardRef(function Button(
  { variant = "primary", size = "md", loading = false, fullWidth = false, iconLeft, iconRight, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx("qm-btn", `qm-btn--${variant}`, `qm-btn--${size}`, fullWidth && "qm-btn--block", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className="qm-btn__spinner" aria-hidden="true" />}
      {iconLeft && <span className="qm-btn__icon" aria-hidden="true">{iconLeft}</span>}
      <span className="qm-btn__label">{children}</span>
      {iconRight && <span className="qm-btn__icon" aria-hidden="true">{iconRight}</span>}
    </button>
  );
});

export function IconButton({ label, variant = "ghost", size = "md", className, children, ...rest }) {
  return (
    <button
      type="button"
      className={cx("qm-iconbtn", `qm-iconbtn--${variant}`, `qm-iconbtn--${size}`, className)}
      aria-label={label}
      title={label}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Inputs                                                              */
/* ------------------------------------------------------------------ */

export const Input = React.forwardRef(function Input({ className, invalid, ...rest }, ref) {
  const field = useFieldProps();
  return <input ref={ref} className={cx("qm-input", className)} {...field} aria-invalid={invalid || field["aria-invalid"] || undefined} {...rest} />;
});

export const Textarea = React.forwardRef(function Textarea({ className, rows = 6, invalid, ...rest }, ref) {
  const field = useFieldProps();
  return <textarea ref={ref} rows={rows} className={cx("qm-textarea", className)} {...field} aria-invalid={invalid || field["aria-invalid"] || undefined} {...rest} />;
});

export function Select({ className, children, invalid, ...rest }) {
  const field = useFieldProps();
  return (
    <div className={cx("qm-select", className)}>
      <select {...field} aria-invalid={invalid || field["aria-invalid"] || undefined} {...rest}>
        {children}
      </select>
      <span className="qm-select__caret" aria-hidden="true">▾</span>
    </div>
  );
}

export function Checkbox({ label, description, className, ...rest }) {
  const id = useId();
  return (
    <label className={cx("qm-checkbox", className)} htmlFor={rest.id || id}>
      <input id={rest.id || id} type="checkbox" {...rest} />
      <span className="qm-checkbox__box" aria-hidden="true">✓</span>
      <span className="qm-checkbox__text">
        <span className="qm-checkbox__label">{label}</span>
        {description && <span className="qm-checkbox__desc">{description}</span>}
      </span>
    </label>
  );
}

/* ------------------------------------------------------------------ */
/* Surfaces, badges, headers                                           */
/* ------------------------------------------------------------------ */

export function Card({ as: Tag = "div", padding = "md", interactive = false, className, children, ...rest }) {
  return (
    <Tag className={cx("qm-card", `qm-card--pad-${padding}`, interactive && "qm-card--interactive", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function Badge({ tone = "neutral", size = "md", dot = false, className, children }) {
  return (
    <span className={cx("qm-badge", `qm-badge--${tone}`, `qm-badge--${size}`, className)}>
      {dot && <span className="qm-badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function Eyebrow({ className, children }) {
  return <p className={cx("qm-eyebrow", className)}>{children}</p>;
}

export function PageHeader({ eyebrow, title, description, actions, className }) {
  return (
    <header className={cx("qm-pageheader", className)}>
      <div className="qm-pageheader__main">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 className="qm-pageheader__title">{title}</h1>
        {description && <p className="qm-pageheader__desc">{description}</p>}
      </div>
      {actions && <div className="qm-pageheader__actions">{actions}</div>}
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Stat cards + infographics                                           */
/* ------------------------------------------------------------------ */

export function StatCard({ label, value, suffix, hint, trend, trendTone = "neutral", icon, className }) {
  return (
    <Card className={cx("qm-stat", className)}>
      <div className="qm-stat__top">
        <span className="qm-stat__label">{label}</span>
        {icon && <span className="qm-stat__icon" aria-hidden="true">{icon}</span>}
      </div>
      <div className="qm-stat__value">
        {value}
        {suffix && <span className="qm-stat__suffix">{suffix}</span>}
      </div>
      <div className="qm-stat__foot">
        {trend && <Badge tone={trendTone} size="sm">{trend}</Badge>}
        {hint && <span className="qm-stat__hint">{hint}</span>}
      </div>
    </Card>
  );
}

export function ProgressBar({ value = 0, max = 100, tone = "accent", size = "md", label, showValue = false, className }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className={cx("qm-progress", className)}>
      {(label || showValue) && (
        <div className="qm-progress__head">
          {label && <span>{label}</span>}
          {showValue && <span className="qm-progress__value">{Math.round(pct)}%</span>}
        </div>
      )}
      <div
        className={cx("qm-progress__track", `qm-progress__track--${size}`)}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <span className={cx("qm-progress__fill", `qm-progress__fill--${tone}`)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function ProgressRing({ value = 0, max = 100, size = 96, stroke = 8, tone = "accent", label, sublabel }) {
  const pct = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="qm-ring" style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label || `${Math.round(pct * 100)} percent`}>
        <circle cx={size / 2} cy={size / 2} r={r} className="qm-ring__track" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          className={cx("qm-ring__value", `qm-ring__value--${tone}`)}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="qm-ring__center">
        <span className="qm-ring__num">{Math.round(pct * 100)}%</span>
        {sublabel && <span className="qm-ring__sub">{sublabel}</span>}
      </div>
    </div>
  );
}

/** Simple, dependency-free SVG line/area chart. */
export function LineChart({ data = [], height = 180, ariaLabel = "Trend chart", className }) {
  const width = 560;
  const pad = 26;
  if (data.length < 2) return <p className="qm-muted">Not enough points to chart yet.</p>;
  const max = Math.max(...data), min = Math.min(...data, 0);
  const span = max - min || 1;
  const points = data.map((d, i) => ({
    x: pad + (i * (width - pad * 2)) / (data.length - 1),
    y: height - pad - ((d - min) / span) * (height - pad * 2),
  }));
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L ${points[points.length - 1].x} ${height - pad} L ${points[0].x} ${height - pad} Z`;
  return (
    <svg className={cx("qm-chart", className)} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel} preserveAspectRatio="none">
      <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} className="qm-chart__axis" />
      <path d={area} className="qm-chart__area" />
      <path d={line} className="qm-chart__line" />
      {points.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r="3.5" className="qm-chart__dot" />)}
    </svg>
  );
}

/** Horizontal comparison bars — good for skill breakdowns. */
export function BarChart({ data = [], max = 100, ariaLabel = "Bar chart", className }) {
  return (
    <ul className={cx("qm-barchart", className)} aria-label={ariaLabel}>
      {data.map((item) => (
        <li className="qm-barchart__row" key={item.label}>
          <span className="qm-barchart__label">{item.label}</span>
          <span className="qm-barchart__track">
            <span className="qm-barchart__fill" style={{ width: `${(item.value / max) * 100}%` }} />
          </span>
          <span className="qm-barchart__value">{item.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function ChartContainer({ title, subtitle, legend, action, footer, children, className }) {
  return (
    <Card className={cx("qm-chartbox", className)}>
      <div className="qm-chartbox__head">
        <div>
          {title && <h3 className="qm-chartbox__title">{title}</h3>}
          {subtitle && <p className="qm-chartbox__subtitle">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="qm-chartbox__body">{children}</div>
      {legend && <ul className="qm-chartbox__legend">{legend}</ul>}
      {footer && <div className="qm-chartbox__footer">{footer}</div>}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Tabs                                                                */
/* ------------------------------------------------------------------ */

export function Tabs({ tabs = [], value, defaultValue, onChange, className, idBase }) {
  const autoId = useId();
  const base = idBase || `qm-tabs-${autoId}`;
  const [internal, setInternal] = useState(defaultValue ?? tabs[0]?.id);
  const active = value ?? internal;

  function select(nextId) {
    if (value === undefined) setInternal(nextId);
    onChange?.(nextId);
  }

  function onKeyDown(event, index) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    select(tabs[next].id);
    event.currentTarget.parentElement?.querySelectorAll('[role="tab"]')[next]?.focus();
  }

  return (
    <div className={cx("qm-tabs", className)}>
      <div className="qm-tabs__list" role="tablist">
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`${base}-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${base}-${tab.id}-panel`}
              tabIndex={selected ? 0 : -1}
              className={cx("qm-tabs__tab", selected && "is-active")}
              onClick={() => select(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {tab.label}
              {tab.badge != null && <Badge size="sm" tone={selected ? "accent" : "neutral"}>{tab.badge}</Badge>}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${base}-${tab.id}-panel`}
          aria-labelledby={`${base}-${tab.id}`}
          hidden={tab.id !== active}
          className="qm-tabs__panel"
          tabIndex={0}
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tooltip                                                             */
/* ------------------------------------------------------------------ */

export function Tooltip({ label, side = "top", children, className }) {
  const id = useId();
  return (
    <span className={cx("qm-tooltip", `qm-tooltip--${side}`, className)}>
      {React.isValidElement(children)
        ? React.cloneElement(children, { "aria-describedby": id })
        : children}
      <span role="tooltip" id={id} className="qm-tooltip__bubble">{label}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Dialog + Drawer + Confirm                                           */
/* ------------------------------------------------------------------ */

function useModalFocus(open, onClose, containerRef) {
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement;
    const focusableSelector = "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

    function getFocusableElements() {
      return [...(containerRef.current?.querySelectorAll(focusableSelector) || [])];
    }

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current?.();
        return;
      }

      if (event.key !== "Tab") return;
      const focusable = getFocusableElements();
      if (focusable.length === 0) {
        event.preventDefault();
        containerRef.current?.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !containerRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !containerRef.current?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }

    const firstFocusable = getFocusableElements()[0];
    (firstFocusable || containerRef.current)?.focus();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [open, containerRef]);
}

export function Dialog({ open, onClose, title, description, children, footer, size = "md", className }) {
  const ref = useRef(null);
  const titleId = useId();
  const descriptionId = useId();
  useModalFocus(open, onClose, ref);
  if (!open) return null;
  return (
    <div className="qm-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-describedby={description ? descriptionId : undefined}
        ref={ref}
        tabIndex={-1}
      >
        <div className="qm-dialog__head">
          {title && <h2 id={titleId} className="qm-dialog__title">{title}</h2>}
        </div>
        {description && <p id={descriptionId} className="qm-dialog__desc">{description}</p>}
        {footer && <div className="qm-dialog__footer">{footer}</div>}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, side = "right", children, footer, className }) {
  const ref = useRef(null);
  const titleId = useId();
  useModalFocus(open, onClose, ref);
  if (!open) return null;
  return (
    <div className="qm-overlay qm-overlay--drawer" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
      >
        <div className="qm-drawer__head">
          <h2 id={titleId} className="qm-drawer__title">{title}</h2>
        </div>
        <div className="qm-drawer__body">{children}</div>
        {footer && <div className="qm-drawer__footer">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, onClose, onConfirm, title = "Are you sure?", message, confirmLabel = "Confirm", cancelLabel = "Cancel", tone = "danger" }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={message}
      size="sm"
      footer={(
        <div className="qm-dialog__actions">
          <Button variant="secondary" onClick={onClose}>{cancelLabel}</Button>
          <Button variant={tone} onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      )}
    />
  );
}

/* ------------------------------------------------------------------ */
/* Data table (with card alternative on small screens)                 */
/* ------------------------------------------------------------------ */

export function DataTable({
  columns = [],
  rows = [],
  getRowKey = (row, index) => row.id ?? index,
  caption,
  onRowClick,
  emptyState,
  mobilePrimaryKey,
  className,
}) {
  if (!rows.length) {
    return emptyState || <p className="qm-muted">No records to display.</p>;
  }

  const primaryKey = mobilePrimaryKey || columns[0]?.key;

  return (
    <div className={cx("qm-datatable", className)}>
      <div className="qm-datatable__scroll">
        <table className="qm-datatable__table">
          {caption && <caption className="qm-visually-hidden">{caption}</caption>}
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} scope="col" style={col.align ? { textAlign: col.align } : undefined}>{col.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr
                key={getRowKey(row, index)}
                className={cx(onRowClick && "qm-datatable__row--clickable")}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={onRowClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRowClick(row); } } : undefined}
              >
                {columns.map((col) => (
                  <td key={col.key} style={col.align ? { textAlign: col.align } : undefined}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="qm-datatable__cards">
        {rows.map((row, index) => (
          <li className="qm-datatable__card" key={getRowKey(row, index)}>
            {columns.map((col) => (
              <div className={cx("qm-datatable__kv", col.key === primaryKey && "qm-datatable__kv--primary")} key={col.key}>
                <span className="qm-datatable__k">{col.header}</span>
                <span className="qm-datatable__v">{col.render ? col.render(row) : row[col.key]}</span>
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Skeletons                                                           */
/* ------------------------------------------------------------------ */

export function Skeleton({ variant = "text", lines = 3, width, height, className }) {
  if (variant === "card") {
    return (
      <div className={cx("qm-skeleton-card", className)} aria-hidden="true">
        <span className="qm-skeleton qm-skeleton--title" />
        <span className="qm-skeleton qm-skeleton--text" />
        <span className="qm-skeleton qm-skeleton--text qm-skeleton--short" />
      </div>
    );
  }
  if (variant === "chart") {
    return <span className={cx("qm-skeleton qm-skeleton--chart", className)} style={{ width, height }} aria-hidden="true" />;
  }
  if (variant === "circle") {
    return <span className={cx("qm-skeleton qm-skeleton--circle", className)} style={{ width, height: height || width }} aria-hidden="true" />;
  }
  if (variant === "title") {
    return <span className={cx("qm-skeleton qm-skeleton--title", className)} style={{ width }} aria-hidden="true" />;
  }
  return (
    <span className={cx("qm-skeleton-lines", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <span key={index} className={cx("qm-skeleton qm-skeleton--text", index === lines - 1 && "qm-skeleton--short")} />
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Empty / error states + notifications                                */
/* ------------------------------------------------------------------ */

export function EmptyState({ icon = "◌", title, message, action, className }) {
  return (
    <div className={cx("qm-state", "qm-state--empty", className)}>
      <span className="qm-state__icon" aria-hidden="true">{icon}</span>
      <h3 className="qm-state__title">{title}</h3>
      {message && <p className="qm-state__message">{message}</p>}
      {action && <div className="qm-state__action">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry, retryLabel = "Try again", className }) {
  return (
    <div className={cx("qm-state", "qm-state--error", className)} role="alert">
      <span className="qm-state__icon" aria-hidden="true">!</span>
      <h3 className="qm-state__title">{title}</h3>
      {message && <p className="qm-state__message">{message}</p>}
      {onRetry && <div className="qm-state__action"><Button variant="secondary" onClick={onRetry}>{retryLabel}</Button></div>}
    </div>
  );
}

export function Notice({ tone = "info", title, children, onDismiss, className }) {
  const role = tone === "danger" || tone === "amber" ? "alert" : "status";
  return (
    <div className={cx("qm-notice", `qm-notice--${tone}`, className)} role={role}>
      <span className="qm-notice__mark" aria-hidden="true">{tone === "danger" ? "!" : tone === "success" ? "✓" : "i"}</span>
      <div className="qm-notice__content">
        {title && <p className="qm-notice__title">{title}</p>}
        {children && <div className="qm-notice__body">{children}</div>}
      </div>
      {onDismiss && <IconButton label="Dismiss" size="sm" onClick={onDismiss}>✕</IconButton>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Toasts                                                              */
/* ------------------------------------------------------------------ */

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback((toast) => {
    const id = `qm-toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts((current) => [...current, { id, tone: "info", ...toast }]);
    window.setTimeout(() => dismiss(id), toast.duration ?? 5000);
    return id;
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ push, dismiss }}>
      {children}
      <div className="qm-toaster" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div key={toast.id} className={cx("qm-toast", `qm-toast--${toast.tone}`)}>
            <span className="qm-toast__mark" aria-hidden="true">
              {toast.tone === "success" ? "✓" : toast.tone === "danger" ? "!" : "i"}
            </span>
            <div className="qm-toast__content">
              {toast.title && <p className="qm-toast__title">{toast.title}</p>}
              {toast.message && <p className="qm-toast__message">{toast.message}</p>}
            </div>
            <IconButton label="Dismiss notification" size="sm" onClick={() => dismiss(toast.id)}>✕</IconButton>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) return { push: () => {}, dismiss: () => {} };
  return ctx;
}

/* ------------------------------------------------------------------ */
/* AppShell + AppNav                                                   */
/* ------------------------------------------------------------------ */

export function AppNav({ items = [], currentPath, onNavigate, className }) {
  return (
    <nav className={cx("qm-appnav", className)} aria-label="Application">
      <ul className="qm-appnav__list">
        {items.map((item) => {
          const active = currentPath
            ? currentPath === item.href
            : item.active;
          return (
            <li key={item.href ?? item.label}>
              {item.href ? (
                <a
                  href={item.href}
                  className={cx("qm-appnav__item", active && "is-active")}
                  aria-current={active ? "page" : undefined}
                >
                  {item.icon && <span className="qm-appnav__icon" aria-hidden="true">{item.icon}</span>}
                  <span className="qm-appnav__label">{item.label}</span>
                  {item.badge != null && <Badge size="sm" tone={active ? "accent" : "neutral"}>{item.badge}</Badge>}
                </a>
              ) : (
                <button
                  type="button"
                  className={cx("qm-appnav__item", active && "is-active")}
                  aria-current={active ? "page" : undefined}
                  onClick={() => onNavigate?.(item)}
                >
                  {item.icon && <span className="qm-appnav__icon" aria-hidden="true">{item.icon}</span>}
                  <span className="qm-appnav__label">{item.label}</span>
                  {item.badge != null && <Badge size="sm" tone={active ? "accent" : "neutral"}>{item.badge}</Badge>}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function AppShell({
  nav = [],
  currentPath,
  onNavigate,
  user,
  onLogout,
  topbarTitle,
  topbarSubtitle,
  topbarActions,
  mobileNavItems,
  children,
  className,
}) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const initials = user?.name
    ? user.name.split(" ").slice(0, 2).map((n) => n[0]).join("").toUpperCase()
    : "?";

  return (
    <div className={cx("qm qm-appshell", className)}>
      {/* Sidebar (≥1024px) */}
      <aside className="qm-appshell__sidebar" aria-label="Sidebar navigation">
        <a className="qm-appshell__brand" href="/">
          <span className="qm-appshell__mark" aria-hidden="true" />
          <span>QueMe</span>
        </a>
        <AppNav items={nav} currentPath={currentPath} onNavigate={onNavigate} />
        {user && (
          <div className="qm-appshell__user">
            <span className="qm-appshell__avatar" aria-hidden="true">{initials}</span>
            <div className="qm-appshell__user-meta">
              <span className="qm-appshell__user-name">{user.name || user.email}</span>
              <span className="qm-appshell__user-role">{user.role}</span>
            </div>
            <IconButton label="Log out" size="sm" onClick={onLogout} title="Log out">✕</IconButton>
          </div>
        )}
      </aside>

      {/* Mobile nav drawer */}
      {drawerOpen && (
        <Drawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          side="left"
          title="Navigation"
        >
          <AppNav items={nav} currentPath={currentPath} onNavigate={(item) => { onNavigate?.(item); setDrawerOpen(false); }} />
          {user && (
            <div className="qm-appshell__user" style={{ marginTop: "auto", paddingTop: "var(--qm-space-5)", borderTop: "1px solid var(--qm-border)" }}>
              <span className="qm-appshell__avatar" aria-hidden="true">{initials}</span>
              <div className="qm-appshell__user-meta">
                <span className="qm-appshell__user-name">{user.name || user.email}</span>
                <span className="qm-appshell__user-role">{user.role}</span>
              </div>
            </div>
          )}
          {onLogout && (
            <Button variant="secondary" fullWidth onClick={() => { onLogout(); setDrawerOpen(false); }} style={{ marginTop: "var(--qm-space-4)" }}>Log out</Button>
          )}
        </Drawer>
      )}

      {/* Main area */}
      <div className="qm-appshell__main">
        <header className="qm-appshell__topbar">
          <div className="qm-appshell__topbar-left">
            <IconButton
              label="Open navigation"
              className="qm-appshell__menu"
              onClick={() => setDrawerOpen(true)}
            >☰</IconButton>
            <div>
              {topbarTitle && <p className="qm-appshell__title">{topbarTitle}</p>}
              {topbarSubtitle && <p className="qm-appshell__subtitle">{topbarSubtitle}</p>}
            </div>
          </div>
          {topbarActions && <div className="qm-appshell__actions">{topbarActions}</div>}
        </header>

        <main className="qm-appshell__content">
          {children}
        </main>

        {/* Mobile bottom pill nav */}
        {(mobileNavItems ?? nav).length > 0 && (
          <nav className="qm-pilotnav" aria-label="Mobile navigation">
            {(mobileNavItems ?? nav).slice(0, 5).map((item) => {
              const active = currentPath
                ? currentPath === item.href
                : item.active;
              return (
                <button
                  key={item.href ?? item.label}
                  type="button"
                  className={cx("qm-pilotnav__item", active && "is-active")}
                  aria-current={active ? "page" : undefined}
                  onClick={() => item.href ? (window.location.href = item.href) : onNavigate?.(item)}
                >
                  {item.icon && <span className="qm-pilotnav__icon" aria-hidden="true">{item.icon}</span>}
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* RadioGroup                                                          */
/* ------------------------------------------------------------------ */

export function RadioGroup({ name, options = [], value, onChange, layout = "column", className }) {
  return (
    <div className={cx("qm-radiogroup", layout === "row" && "qm-radiogroup--row", className)} role="group">
      {options.map((opt) => {
        const id = `${name}-${opt.value}`;
        return (
          <label key={opt.value} className="qm-radio" htmlFor={id}>
            <input
              id={id}
              type="radio"
              name={name}
              value={opt.value}
              checked={value === opt.value}
              onChange={() => onChange?.(opt.value)}
            />
            <span className="qm-radio__dot" aria-hidden="true" />
            <span>
              <span className="qm-radio__label">{opt.label}</span>
              {opt.description && <span className="qm-radio__desc">{opt.description}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Toggle                                                              */
/* ------------------------------------------------------------------ */

export function Toggle({ label, checked, onChange, id: propId, className }) {
  const autoId = useId();
  const id = propId || autoId;
  return (
    <label className={cx("qm-toggle", className)} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange?.(e.target.checked)}
      />
      <span className="qm-toggle__track" aria-hidden="true">
        <span className="qm-toggle__thumb" />
      </span>
      {label && <span className="qm-toggle__label">{label}</span>}
    </label>
  );
}

/* ------------------------------------------------------------------ */
/* Breadcrumb                                                          */
/* ------------------------------------------------------------------ */

export function Breadcrumb({ crumbs = [], className }) {
  return (
    <nav aria-label="Breadcrumb" className={cx("qm-breadcrumb", className)}>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: 4 }}>
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li key={crumb.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {i > 0 && <span className="qm-breadcrumb__sep" aria-hidden="true">›</span>}
              {isLast
                ? <span className="qm-breadcrumb__current" aria-current="page">{crumb.label}</span>
                : <a className="qm-breadcrumb__link" href={crumb.href}>{crumb.label}</a>
              }
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/* ------------------------------------------------------------------ */
/* Steps                                                               */
/* ------------------------------------------------------------------ */

export function Steps({ steps: stepList = [], current = 0, className }) {
  return (
    <ol className={cx("qm-steps", className)} aria-label="Progress">
      {stepList.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li
            key={step}
            className={cx("qm-step", done && "qm-step--done", active && "qm-step--active")}
            aria-current={active ? "step" : undefined}
          >
            <span className="qm-step__circle" aria-hidden="true">{done ? "✓" : i + 1}</span>
            <span className="qm-step__label">{step}</span>
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ */
/* AudioPlayer                                                         */
/* ------------------------------------------------------------------ */

export function AudioPlayer({ title, src, className }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [rate, setRate] = useState(1);

  const fmt = (s) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
  };

  function toggle() {
    const el = audioRef.current;
    if (!el) return;
    if (playing) { el.pause(); } else { el.play(); }
    setPlaying(!playing);
  }

  if (!src) {
    return (
      <div className={cx("qm-audioplayer qm-audioplayer--empty", className)}>
        <p className="qm-muted" style={{ margin: 0 }}>No audio recording available yet.</p>
      </div>
    );
  }

  return (
    <div className={cx("qm-audioplayer", className)}>
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => setCurrent(e.target.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.target.duration)}
        onEnded={() => setPlaying(false)}
        onVolumeChange={(e) => setVolume(e.target.volume)}
      />
      <div className="qm-audioplayer__head">
        <IconButton
          label={playing ? "Pause" : "Play"}
          variant="primary"
          size="md"
          onClick={toggle}
        >{playing ? "⏸" : "▶"}</IconButton>
        <div className="qm-audioplayer__meta">
          {title && <span className="qm-audioplayer__title">{title}</span>}
          <span className="qm-audioplayer__time">{fmt(current)} / {fmt(duration)}</span>
        </div>
        <div className="qm-audioplayer__rate">
          {[0.75, 1, 1.25, 1.5].map((r) => (
            <button
              key={r}
              type="button"
              className={cx("qm-rate", rate === r && "is-active")}
              onClick={() => { setRate(r); if (audioRef.current) audioRef.current.playbackRate = r; }}
            >{r}×</button>
          ))}
        </div>
      </div>
      <Waveform progress={duration ? current / duration : 0} />
      <div className="qm-audioplayer__foot">
        <div className="qm-audioplayer__volume">
          <input
            type="range" min={0} max={1} step={0.05} value={volume}
            aria-label="Volume"
            onChange={(e) => { const v = parseFloat(e.target.value); setVolume(v); if (audioRef.current) audioRef.current.volume = v; }}
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Waveform                                                            */
/* ------------------------------------------------------------------ */

export function Waveform({ bars = 60, heights, progress = 0, tone = "accent", onClick, className }) {
  const BAR_W = 3;
  const BAR_GAP = 2;
  const H = 48;

  const defaultHeights = React.useMemo(() => {
    if (heights) return heights;
    // Deterministic pseudo-random heights so waveform looks consistent
    return Array.from({ length: bars }, (_, i) => {
      const seed = Math.sin(i * 127.1 + 311.7) * 43758.5453;
      return 0.2 + 0.8 * Math.abs(seed - Math.floor(seed));
    });
  }, [bars, heights]);

  const totalBars = defaultHeights.length;
  const playedCount = Math.round(progress * totalBars);

  return (
    <div
      className={cx("qm-waveform", className)}
      role="progressbar"
      aria-valuenow={Math.round(progress * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Audio progress"
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(e); } } : undefined}
      style={{ height: H }}
    >
      <div className="qm-waveform__bars">
        {defaultHeights.map((h, i) => (
          <span
            key={i}
            className={cx("qm-waveform__bar", i < playedCount && "is-played", tone === "amber" && "qm-waveform__bar--amber")}
            style={{
              width: BAR_W,
              height: Math.max(4, h * H),
              marginRight: i < totalBars - 1 ? BAR_GAP : 0,
              flexShrink: 0,
            }}
          />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* TranscriptPanel                                                     */
/* ------------------------------------------------------------------ */

export function TranscriptPanel({ segments = [], activeId, onSegmentClick, className }) {
  return (
    <div className={cx("qm-transcript", className)}>
      <div className="qm-transcript__head">
        <h3 className="qm-transcript__title">Transcript</h3>
        {segments.length > 0 && <Badge tone="neutral" size="sm">{segments.length} segments</Badge>}
      </div>
      {segments.length === 0 ? (
        <p className="qm-muted qm-transcript__empty">Transcript will appear here as you speak.</p>
      ) : (
        <ul className="qm-transcript__list">
          {segments.map((seg) => (
            <li key={seg.id}>
              <button
                type="button"
                className={cx("qm-transcript__seg", seg.id === activeId && "is-active")}
                onClick={() => onSegmentClick?.(seg)}
              >
                <span className="qm-transcript__meta">
                  <span className="qm-transcript__speaker">{seg.speaker || "You"}</span>
                  <span className="qm-transcript__time">{seg.time}</span>
                </span>
                <span className="qm-transcript__text">{seg.text}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* InterviewControls                                                   */
/* ------------------------------------------------------------------ */

export function InterviewControls({ isLive = false, statusText, actions, className }) {
  return (
    <div className={cx("qm-controls", className)}>
      <div className="qm-controls__status">
        <span
          className={cx("qm-controls__pulse", isLive && "is-live")}
          aria-hidden="true"
        />
        <span className="qm-controls__status-text">
          {statusText || (isLive ? "Recording…" : "Ready")}
        </span>
      </div>
      {actions && <div className="qm-controls__actions">{actions}</div>}
    </div>
  );
}
