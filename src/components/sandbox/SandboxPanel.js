import React, { useEffect, useRef, useState } from "react";
import { useUIState, useUIActions } from "../../context/UIContext";
import Tabs from "../shared/Tabs";
import SecurityPanel from "./SecurityPanel";
import ControlPlanePanel from "./ControlPlanePanel";
import WhatIfPanel from "./WhatIfPanel";
import ObservabilityPanel from "./ObservabilityPanel";
import {
  FlaskConical,
  SlidersHorizontal,
  GitCompare,
  Activity,
  X,
} from "../../icons";

// Slide-over drawer combining the demo tools. Toggled from the header
// (useUIState().sandboxOpen). Everything flows through the backend gateway.
// (Verify/Red-team now live server-side: the red-team gate runs in CI against the
// real detectors — see backend/tests/test_redteam_gate.py.)
const TABS = [
  { key: "security", label: "Attacks", Icon: FlaskConical },
  { key: "control", label: "Control", Icon: SlidersHorizontal },
  { key: "whatif", label: "What-if", Icon: GitCompare },
  { key: "signals", label: "Signals", Icon: Activity },
];

export default function SandboxPanel() {
  const { sandboxOpen } = useUIState();
  const { toggleSandbox } = useUIActions();
  const [tab, setTab] = useState("security");
  const closeRef = useRef(null);
  // Remember what had focus before opening so we can restore it on close.
  const restoreFocusRef = useRef(null);

  // Escape-to-close + focus management for the modal drawer.
  useEffect(() => {
    if (!sandboxOpen) return;
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    // Move focus into the dialog so keyboard users aren't left behind it.
    closeRef.current?.focus();

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        toggleSandbox();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      // Restore focus to the trigger when the drawer closes.
      restoreFocusRef.current?.focus?.();
    };
  }, [sandboxOpen, toggleSandbox]);

  if (!sandboxOpen) return null;

  return (
    <div className="sandbox-overlay" onClick={toggleSandbox}>
      <aside
        className="sandbox-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Security sandbox"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sandbox-head">
          <div className="sandbox-head-title">
            <FlaskConical size={16} strokeWidth={1.75} />
            <span>Security Sandbox</span>
          </div>
          <button
            ref={closeRef}
            className="icon-btn"
            onClick={toggleSandbox}
            aria-label="Close sandbox"
            title="Close"
          >
            <X size={16} strokeWidth={1.75} />
          </button>
        </div>

        <Tabs tabs={TABS} active={tab} onChange={setTab} size="sm" />

        <div className="sandbox-body">
          {tab === "security" && <SecurityPanel />}
          {tab === "control" && <ControlPlanePanel />}
          {tab === "whatif" && <WhatIfPanel />}
          {tab === "signals" && <ObservabilityPanel />}
        </div>
      </aside>
    </div>
  );
}
