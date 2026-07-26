import React, { useMemo } from "react";
import { useChatRequests, useChatHistory } from "../../context/ChatContext";
import { useUIState, useUIActions } from "../../context/UIContext";
import Tabs from "../shared/Tabs";
import AuditTab from "./AuditTab";
import SecurityTab from "./SecurityTab";
import RequestTab from "./RequestTab";
import ResponseTab from "./ResponseTab";
import MetricsTab from "./MetricsTab";
import {
  ScrollText,
  Shield,
  FileText,
  MessageSquare,
  BarChart3,
} from "../../icons";

export default function Inspector() {
  // Subscribe only to requests + history (both change on lifecycle events, not
  // per token), so the Inspector shell stays quiet while a response streams. The
  // per-frame message lookup lives in ResponseTab, which is the only tab that
  // needs it and is only mounted when it's the active tab.
  const requests = useChatRequests();
  const history = useChatHistory();
  const { inspectorTab, inspectId } = useUIState();
  const { setInspectorTab } = useUIActions();

  // Selected request: the one the user clicked "Inspect" on, else the latest.
  const req = useMemo(() => {
    if (inspectId) {
      const found = requests.find((r) => r.id === inspectId);
      if (found) return found;
    }
    return requests[requests.length - 1] || null;
  }, [requests, inspectId]);

  const threatCount = history.filter(
    (h) => h.kind === "blocked" || h.kind === "canary"
  ).length;

  const tabs = [
    { key: "audit", label: "Audit", Icon: ScrollText, badge: history.length },
    { key: "security", label: "Security", Icon: Shield, badge: threatCount },
    { key: "request", label: "Request", Icon: FileText },
    { key: "response", label: "Response", Icon: MessageSquare },
    { key: "metrics", label: "Metrics", Icon: BarChart3 },
  ];

  return (
    <aside className="console-inspector">
      <div className="inspector-head">
        <span className="inspector-title">Inspector</span>
      </div>
      <Tabs
        tabs={tabs}
        active={inspectorTab}
        onChange={setInspectorTab}
        size="sm"
      />
      <div className="inspector-body">
        {inspectorTab === "audit" && <AuditTab />}
        {inspectorTab === "security" && <SecurityTab req={req} />}
        {inspectorTab === "request" && <RequestTab req={req} />}
        {inspectorTab === "response" && <ResponseTab req={req} />}
        {inspectorTab === "metrics" && <MetricsTab req={req} />}
      </div>
    </aside>
  );
}
