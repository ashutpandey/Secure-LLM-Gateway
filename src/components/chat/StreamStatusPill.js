import React from "react";
import { useChatStatus } from "../../context/ChatContext";
import {
  ShieldCheck,
  ArrowRightLeft,
  Zap,
  CircleCheck,
  Ban,
  AlertTriangle,
  Circle,
} from "../../icons";

const STAGE = {
  validating: {
    Icon: ShieldCheck,
    label: "Running input guardrails…",
    tone: "busy",
  },
  routing: {
    Icon: ArrowRightLeft,
    label: "Routing to provider…",
    tone: "busy",
  },
  streaming: { Icon: Zap, label: "Streaming tokens…", tone: "busy" },
  done: { Icon: CircleCheck, label: "Response complete", tone: "ok" },
  blocked: { Icon: Ban, label: "Blocked by guardrail", tone: "danger" },
  error: { Icon: AlertTriangle, label: "Request failed", tone: "danger" },
  idle: { Icon: Circle, label: "Idle", tone: "idle" },
};

// Compact live indicator above the composer. Reads ONLY the status slice, so it
// updates a few times per request — not per token.
export default function StreamStatusPill() {
  const { stage, isLoading } = useChatStatus();
  // Hide when there's nothing interesting to say.
  if (stage === "idle") return null;

  const s = STAGE[stage] || STAGE.idle;
  const { Icon } = s;
  return (
    <div className={`stream-pill tone-${s.tone} ${isLoading ? "live" : ""}`}>
      <Icon size={14} strokeWidth={1.75} />
      <span>{s.label}</span>
    </div>
  );
}
