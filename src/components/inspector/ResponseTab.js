import React from "react";
import { useChatState } from "../../context/ChatContext";
import { DEMO_MODE } from "../../config";
import { ShieldAlert, ShieldCheck, MessageSquare } from "../../icons";

// The "response" side: the delivered (sanitized) text, plus the raw model
// output when LLM02 changed something (before/after). This tab reads the live
// message list (updates per frame while streaming) — it's the only Inspector
// tab that needs to, and it's only mounted when it's the active tab.
export default function ResponseTab({ req }) {
  const state = useChatState();
  if (!req) return <div className="tab-empty muted">No response yet.</div>;

  const message = req ? state.messages.find((m) => m.id === req.id) : null;
  const content = message?.content ?? "";
  const raw = message?.meta?.raw;
  const removed = message?.meta?.removed || req.outputRemoved || [];
  const changed = DEMO_MODE && removed.length > 0 && raw && raw !== content;

  return (
    <div className="resp-tab">
      <section className="resp-block">
        <div className="resp-block-title">
          <MessageSquare size={14} strokeWidth={1.75} />
          Delivered response
        </div>
        {content ? (
          <pre className="resp-body">{content}</pre>
        ) : (
          <div className="muted">Empty.</div>
        )}
      </section>

      {removed.length > 0 && (
        <div className="resp-removed">
          <ShieldCheck size={13} strokeWidth={1.75} />
          <span>Neutralized: {removed.join(", ")}</span>
        </div>
      )}

      {changed && (
        <section className="resp-block">
          <div className="resp-block-title danger">
            <ShieldAlert size={14} strokeWidth={1.75} />
            Raw model output (inert — shown for audit)
          </div>
          <pre className="resp-body danger">{raw}</pre>
        </section>
      )}
    </div>
  );
}
