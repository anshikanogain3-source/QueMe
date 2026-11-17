import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from "lucide-react";

const FeedbackContext = createContext(null);
const icons = { success: CheckCircle2, error: AlertCircle, warning: TriangleAlert, info: Info };

export function FeedbackProvider({ children }) {
  const [toast, setToast] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const timer = useRef(null);
  const lastToast = useRef(null);
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const resolver = useRef(null);

  const notify = useCallback((message, type = "info") => {
    if (!message) return;
    const now = Date.now();
    if (lastToast.current?.message === message && lastToast.current.type === type && now - lastToast.current.at < 1500) return;
    lastToast.current = { message, type, at: now };
    window.clearTimeout(timer.current);
    setToast({ message, type, id: now });
    timer.current = window.setTimeout(() => setToast(null), type === "error" ? 7000 : 5000);
  }, []);

  const confirmAction = useCallback((options) => {
    if (resolver.current) resolver.current(false);
    setConfirmation(options);
    return new Promise((resolve) => { resolver.current = resolve; });
  }, []);

  const settleConfirmation = useCallback((result) => {
    const resolve = resolver.current;
    resolver.current = null;
    if (dialogRef.current?.open) dialogRef.current.close();
    setConfirmation(null);
    resolve?.(result);
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!confirmation || !dialog) return;
    if (!dialog.open) dialog.showModal();
    cancelRef.current?.focus();
  }, [confirmation]);

  useEffect(() => () => {
    window.clearTimeout(timer.current);
    resolver.current?.(false);
  }, []);

  const Icon = toast ? icons[toast.type] || Info : Info;
  return (
    <FeedbackContext.Provider value={{ notify, confirmAction }}>
      {children}
      <div className="qm-toast-region" aria-live={toast?.type === "error" ? "assertive" : "polite"} aria-atomic="true">
        {toast && <div key={toast.id} className={`qm-toast qm-toast-${toast.type}`} role={toast.type === "error" ? "alert" : "status"}>
          <Icon size={18} aria-hidden="true" /><span>{toast.message}</span>
          <button type="button" className="qm-toast-close" aria-label="Dismiss notification" onClick={() => { window.clearTimeout(timer.current); setToast(null); }}><X size={16} /></button>
        </div>}
      </div>
      <dialog ref={dialogRef} className="qm-confirm-dialog" aria-labelledby="qm-confirm-title" aria-describedby="qm-confirm-description" onCancel={(event) => { event.preventDefault(); settleConfirmation(false); }} onClose={() => { if (resolver.current) settleConfirmation(false); }}>
        {confirmation && <>
          <div className={`qm-confirm-mark${confirmation.destructive ? " is-destructive" : ""}`} aria-hidden="true">{confirmation.destructive ? <TriangleAlert size={21} /> : <Info size={21} />}</div>
          <h2 id="qm-confirm-title">{confirmation.title}</h2>
          <p id="qm-confirm-description">{confirmation.description}</p>
          <div className="qm-confirm-actions">
            <button ref={cancelRef} type="button" className="button button-outline" onClick={() => settleConfirmation(false)}>{confirmation.cancelLabel || "Cancel"}</button>
            <button type="button" className={`button ${confirmation.destructive ? "qm-button-danger" : "button-primary"}`} onClick={() => settleConfirmation(true)}>{confirmation.confirmLabel || "Continue"}</button>
          </div>
        </>}
      </dialog>
    </FeedbackContext.Provider>
  );
}

export function useFeedback() {
  const value = useContext(FeedbackContext);
  if (!value) throw new Error("useFeedback must be used inside FeedbackProvider.");
  return value;
}
