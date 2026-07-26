import React, { useState } from "react";
import { useUIActions } from "../../context/UIContext";
import { DEMO_MODE } from "../../config";
import {
  ShieldCheck,
  ShieldAlert,
  Ban,
  AlertTriangle,
  Eye,
  EyeOff,
  Copy,
  Search,
  Sparkles,
} from "../../icons";

// Memoized: the reducer returns the SAME object reference for messages that
// didn't change (only the streaming bubble gets a new object per commit), so
// every finished bubble skips re-rendering while tokens stream.
const MessageBubble = React.memo(function MessageBubble({ msg }) {
  const { role, content, meta } = msg;
  const { inspectRequest } = useUIActions();
  const removed = meta?.removed || [];
  // The before/after reveal only exists in DEMO_MODE (raw is absent otherwise).
  const wasSanitized =
    DEMO_MODE && removed.length > 0 && meta?.raw && meta.raw !== content;
  const [showRaw, setShowRaw] = useState(false);

  const isUser = role === "user";
  // The request record is keyed by the assistant message's own id, so that's
  // the id the Inspector deep-links to. (There is no request for a user bubble.)
  const requestId = isUser ? null : msg.id;
  const redacted = meta?.redacted || [];

  const copy = () => {
    try {
      navigator.clipboard?.writeText(content);
    } catch {}
  };

  return (
    <div
      className={`msg-row ${isUser ? "user" : "assistant"} ${
        meta?.blocked ? "blocked" : ""
      } ${meta?.error ? "err" : ""}`}
    >
      <div className="msg-avatar">
        {isUser ? (
          <span className="avatar-you">You</span>
        ) : (
          <Sparkles size={15} strokeWidth={1.75} />
        )}
      </div>

      <div className="msg-main">
        <div className="msg-head">
          <span className="msg-author">{isUser ? "You" : "Assistant"}</span>
          {meta?.blocked && (
            <span className="msg-tag danger">
              <Ban size={12} strokeWidth={2} /> blocked
            </span>
          )}
          {meta?.error && (
            <span className="msg-tag danger">
              <AlertTriangle size={12} strokeWidth={2} /> error
            </span>
          )}
        </div>

        {/* SAFE RENDER: content is a plain React text node — never
            dangerouslySetInnerHTML — so nothing here can execute. */}
        <div className="msg-content">
          {content}
          {meta?.streaming && <span className="caret" />}
        </div>

        {/* LLM06: the user's own message was redacted before storage/display, so
            no card/SSN/key is ever persisted or left in the DOM. */}
        {isUser && redacted.length > 0 && (
          <div className="sanitize-report">
            <span className="badge sanitized">
              <ShieldCheck size={13} strokeWidth={1.75} />
              Sensitive data redacted: {redacted.join(", ")}
            </span>
          </div>
        )}

        {removed.length > 0 && (
          <div className="sanitize-report">
            <span className="badge sanitized">
              <ShieldCheck size={13} strokeWidth={1.75} />
              Output sanitized: {removed.join(", ")}
            </span>
            {wasSanitized && (
              <button
                type="button"
                className="reveal-toggle"
                onClick={() => setShowRaw((v) => !v)}
                aria-expanded={showRaw}
              >
                {showRaw ? (
                  <>
                    <EyeOff size={13} strokeWidth={1.75} /> Hide raw output
                  </>
                ) : (
                  <>
                    <Eye size={13} strokeWidth={1.75} /> Show raw model output
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* BEFORE / AFTER. The raw payload is rendered as a plain text node too,
            so even the "dangerous" version on screen is inert. */}
        {wasSanitized && showRaw && (
          <div className="diff">
            <div className="diff-col danger">
              <div className="diff-label">
                <ShieldAlert size={12} strokeWidth={1.75} /> Raw (what the model
                sent)
              </div>
              <pre className="diff-body">{meta.raw}</pre>
            </div>
            <div className="diff-col safe">
              <div className="diff-label">
                <ShieldCheck size={12} strokeWidth={1.75} /> Rendered (after
                LLM02)
              </div>
              <pre className="diff-body">{content}</pre>
            </div>
          </div>
        )}

        {!isUser && !meta?.streaming && (
          <div className="msg-actions">
            <button className="msg-action" onClick={copy} title="Copy">
              <Copy size={13} strokeWidth={1.75} /> Copy
            </button>
            {requestId && (
              <button
                className="msg-action"
                onClick={() => inspectRequest(requestId, "request")}
                title="Inspect this request"
              >
                <Search size={13} strokeWidth={1.75} /> Inspect
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

export default MessageBubble;
