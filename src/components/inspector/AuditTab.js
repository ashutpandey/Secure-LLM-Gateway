import React from "react";
import { useChatHistory } from "../../context/ChatContext";
import {
  MessageSquare,
  FlaskConical,
  RefreshCw,
  ArrowRightLeft,
  CircleCheck,
  Ban,
  Eye,
  AlertTriangle,
  Circle,
} from "../../icons";

const KIND_META = {
  prompt: { Icon: MessageSquare, label: "Prompt" },
  "input-guardrail": { Icon: FlaskConical, label: "Input guardrail" },
  retry: { Icon: RefreshCw, label: "Retry" },
  failover: { Icon: ArrowRightLeft, label: "Failover" },
  response: { Icon: CircleCheck, label: "Response" },
  blocked: { Icon: Ban, label: "Blocked" },
  canary: { Icon: Eye, label: "Canary" },
  error: { Icon: AlertTriangle, label: "Error" },
};

function summarize(entry) {
  const d = entry.detail || {};
  switch (entry.kind) {
    case "prompt":
      return `"${(d.text || "").slice(0, 60)}"`;
    case "input-guardrail":
      return `${d.reason}${
        d.redactions?.length ? ` [${d.redactions.join(", ")}]` : ""
      } (injection score ${d.injectionScore})`;
    case "retry":
      return `${d.provider} attempt ${d.attempt} → HTTP ${d.status}, backing off ${d.waitMs}ms`;
    case "failover":
      return `${d.from} → ${d.to} (HTTP ${d.status})`;
    case "response":
      return `${d.provider}${
        d.sanitized ? ` · sanitized: ${d.removed.join(", ")}` : ""
      }`;
    case "blocked":
      return `${d.reason} (score ${d.score}) [${(d.signals || []).join(", ")}]`;
    case "canary":
      return `system-prompt canary leaked by ${d.provider} — response withheld`;
    case "error":
      return d.message;
    default:
      return "";
  }
}

export default function AuditTab() {
  const history = useChatHistory();
  if (history.length === 0)
    return <div className="tab-empty muted">No events yet.</div>;

  return (
    <ul className="audit-list">
      {history
        .slice()
        .reverse()
        .map((e, i) => {
          const meta = KIND_META[e.kind] || { Icon: Circle, label: e.kind };
          const { Icon } = meta;
          return (
            <li key={`${e.at}-${i}`} className={`audit-row kind-${e.kind}`}>
              <span className="audit-at">{e.at}</span>
              <span className="audit-icon">
                <Icon size={14} strokeWidth={1.75} />
              </span>
              <span className="audit-body">
                <span className="audit-label">{meta.label}</span>
                <span className="audit-detail">{summarize(e)}</span>
              </span>
            </li>
          );
        })}
    </ul>
  );
}
