import React from "react";
import ProviderBadge from "../shared/ProviderBadge";
import { FileText, RefreshCw, ArrowRightLeft, Hash } from "../../icons";

// The "request" side of the exchange: what was sent and how it was routed.
export default function RequestTab({ req }) {
  if (!req) return <div className="tab-empty muted">No request selected.</div>;

  return (
    <div className="req-tab">
      <section className="req-block">
        <div className="req-block-title">
          <FileText size={14} strokeWidth={1.75} />
          Prompt
        </div>
        <pre className="req-prompt">{req.prompt}</pre>
      </section>

      <div className="req-kv-grid">
        <div className="req-kv">
          <span className="k">Provider</span>
          <span className="v">
            <ProviderBadge name={req.provider} model={req.model} size="sm" />
          </span>
        </div>
        <div className="req-kv">
          <span className="k">Model</span>
          <span className="v">{req.model || "—"}</span>
        </div>
        <div className="req-kv">
          <span className="k">
            <RefreshCw size={12} strokeWidth={1.75} /> Retries
          </span>
          <span className="v">{req.retries ?? 0}</span>
        </div>
        <div className="req-kv">
          <span className="k">
            <ArrowRightLeft size={12} strokeWidth={1.75} /> Failovers
          </span>
          <span className="v">{req.fallbacks ?? 0}</span>
        </div>
        <div className="req-kv">
          <span className="k">Completion</span>
          <span className="v">{req.completion || "in progress"}</span>
        </div>
        <div className="req-kv">
          <span className="k">
            <Hash size={12} strokeWidth={1.75} /> Request ID
          </span>
          <span className="v mono">{req.id}</span>
        </div>
      </div>
    </div>
  );
}
