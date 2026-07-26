import React from "react";
import { useChatStatus } from "../../context/ChatContext";
import { providerLabel } from "../../utils/format";
import { Wifi, Cpu, GitBranch, ShieldCheck } from "../../icons";

// Thin status strip. Reads ONLY the status slice (stage/provider/isLoading), so
// it never re-renders while tokens stream.
export default function Footer() {
  const { stage, activeProvider, isLoading } = useChatStatus();

  return (
    <footer className="console-footer">
      <span className="foot-item">
        <Wifi size={13} strokeWidth={1.75} />
        <span>Mock gateway</span>
        <span className={`foot-dot ${isLoading ? "busy" : "ok"}`} />
      </span>
      <span className="foot-item">
        <Cpu size={13} strokeWidth={1.75} />
        <span>{providerLabel(activeProvider)}</span>
      </span>
      <span className="foot-item">
        <GitBranch size={13} strokeWidth={1.75} />
        <span>stage: {stage}</span>
      </span>
      <span className="foot-spacer" />
      <span className="foot-item muted">
        <ShieldCheck size={13} strokeWidth={1.75} />
        <span>OWASP LLM01 · LLM02 · LLM06 guardrails active</span>
      </span>
    </footer>
  );
}
