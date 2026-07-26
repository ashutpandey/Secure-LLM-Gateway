import React, { useEffect } from "react";
import { useUIState, useUIActions } from "../../context/UIContext";
import { CircleCheck, AlertTriangle, ShieldAlert, Info, X } from "../../icons";

const TONE_ICON = {
  success: CircleCheck,
  warn: AlertTriangle,
  danger: ShieldAlert,
  info: Info,
};

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(toast.id), 4500);
    return () => clearTimeout(t);
  }, [toast.id, onDismiss]);

  const Icon = TONE_ICON[toast.tone] || Info;
  return (
    <div className={`toast tone-${toast.tone}`} role="status">
      <Icon size={16} strokeWidth={1.75} className="toast-icon" />
      <div className="toast-body">
        {toast.title && <div className="toast-title">{toast.title}</div>}
        {toast.message && <div className="toast-msg">{toast.message}</div>}
      </div>
      <button
        className="toast-close"
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
      >
        <X size={14} strokeWidth={2} />
      </button>
    </div>
  );
}

export default function Toaster() {
  const { toasts } = useUIState();
  const { dismissToast } = useUIActions();
  if (!toasts.length) return null;
  return (
    <div className="toaster" aria-live="polite">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onDismiss={dismissToast} />
      ))}
    </div>
  );
}
