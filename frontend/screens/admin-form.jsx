// Shared form controls for admin screens.  Validation mirrors the backend
// schemas (pydantic) and returns actionable field-level errors without
// leaking internal detail.
import React from "react";
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Dialog,
  Field,
  Input,
  Select,
  Textarea,
} from "../design-system/index.js";

export function required(message) {
  return (v) => (v == null || String(v).trim() === "" ? message : undefined);
}

export function pattern(message, regex) {
  return (v) => (v == null || !regex.test(v) ? message : undefined);
}

export function maxLength(message, n) {
  return (v) => (v == null || String(v).length > n ? message : undefined);
}

export function minValue(message, n) {
  return (v) => (v == null || Number(v) < n ? message : undefined);
}

export function maxValue(message, n) {
  return (v) => (v == null || Number(v) > n ? message : undefined);
}

/** Small validation result helper.  fieldErrors is an object keyed by field name. */
export function validateForm(rules, values) {
  const next = {};
  Object.entries(rules).forEach(([field, fns]) => {
    const v = values[field];
    for (const fn of fns) {
      const err = fn(v);
      if (err) {
        next[field] = err;
        break;
      }
    }
  });
  return next;
}

/** Coerce a free-form date string from a text input into an ISO local datetime.
 *  Returns null when the field is empty so the backend keeps its semantics. */
export function toIsoDate(value) {
  if (value == null || String(value).trim() === "") return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export function usePersistedForm(initial, { debounceMs = 300 } = {}) {
  const [values, setValues] = React.useState(initial);
  const [changed, setChanged] = React.useState(false);
  React.useEffect(() => {
    setValues(initial);
    setChanged(false);
  }, [initial]);
  const onChange = (patch) => {
    setValues((prev) => ({ ...prev, ...patch }));
    setChanged(true);
  };
  const reset = () => setValues(initial);
  return { values, changed, reset, setValues, setField: onChange };
}

/** Field error helper that reuses the design system Field. */
export function FieldError({ error, className }) {
  if (!error) return null;
  return <p className="qm-field__error" role="alert">{error}</p>;
}

/** Inline alert shown after a mutation with a long-form description. */
export function Toast({ tone = "info", title, message, onDismiss }) {
  React.useEffect(() => {
    const id = setTimeout(() => {
      if (onDismiss) onDismiss();
    }, 5000);
    return () => clearTimeout(id);
  }, []);
  return (
    <div className={"qm-toast qm-toast--" + tone} role="status" aria-live="polite">
      <div className="qm-toast__copy">
        <p className="qm-toast__title">{title}</p>
        {message ? <p className="qm-toast__message">{message}</p> : null}
      </div>
      {onDismiss ? <Button variant="ghost" size="sm" onClick={onDismiss}>Dismiss</Button> : null}
    </div>
  );
}
