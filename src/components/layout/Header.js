import React from "react";
import { useUIState, useUIActions } from "../../context/UIContext";
import { useChatStatus } from "../../context/ChatContext";
import ProviderBadge from "../shared/ProviderBadge";
import {
  Shield,
  Sun,
  Moon,
  FlaskConical,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
} from "../../icons";

const STAGE_LABEL = {
  idle: "Idle",
  validating: "Validating",
  routing: "Routing",
  streaming: "Streaming",
  done: "Ready",
  blocked: "Blocked",
  error: "Error",
};

// Map the request stage to a status-dot tone.
const STAGE_TONE = {
  validating: "busy",
  routing: "busy",
  streaming: "busy",
  blocked: "err",
  error: "err",
  done: "ok",
  idle: "ok",
};

export default function Header() {
  const { theme, sidebarOpen } = useUIState();
  const { toggleTheme, toggleSidebar, toggleInspector, toggleSandbox } =
    useUIActions();
  const { stage, activeProvider, isLoading } = useChatStatus();

  const tone = STAGE_TONE[stage] || "ok";

  return (
    <header className="console-header">
      <div className="header-left">
        <button
          className="icon-btn"
          onClick={toggleSidebar}
          title={sidebarOpen ? "Hide conversations" : "Show conversations"}
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? (
            <PanelLeftClose size={18} strokeWidth={1.75} />
          ) : (
            <PanelLeftOpen size={18} strokeWidth={1.75} />
          )}
        </button>
        <div className="brand">
          <span className="brand-mark">
            <Shield size={18} strokeWidth={2} />
          </span>
          <span className="brand-text">
            <strong>Secure LLM Gateway</strong>
            <span className="brand-sub">Streaming console</span>
          </span>
        </div>
      </div>

      <div className="header-center">
        <span className={`status-dot ${tone} ${isLoading ? "pulse" : ""}`} />
        <span className="status-stage">{STAGE_LABEL[stage] || stage}</span>
        <span className="header-divider" />
        <ProviderBadge name={activeProvider} size="sm" />
      </div>

      <div className="header-right">
        <button
          className="ghost-btn"
          onClick={toggleSandbox}
          title="Security Sandbox"
        >
          <FlaskConical size={16} strokeWidth={1.75} />
          <span>Sandbox</span>
        </button>
        <button
          className="icon-btn"
          onClick={toggleTheme}
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            <Sun size={18} strokeWidth={1.75} />
          ) : (
            <Moon size={18} strokeWidth={1.75} />
          )}
        </button>
        <button
          className="icon-btn"
          onClick={toggleInspector}
          title="Toggle inspector"
          aria-label="Toggle inspector"
        >
          <PanelRight size={18} strokeWidth={1.75} />
        </button>
      </div>
    </header>
  );
}
