import React from "react";
import { MessageSquare, ShieldAlert, Clock, Trash2 } from "../../icons";
import { ms, ago, providerLabel } from "../../utils/format";

// One conversation entry in the sidebar. `conv` is the lightweight projection
// from ConversationsContext (id, title, timestamps, derived stats) — no message
// bodies, so re-rendering the list is cheap.
function HistoryCard({ conv, active, onSelect, onDelete, now }) {
  const { title, stats, updatedAt } = conv;
  const label = title || "New conversation";

  return (
    <div
      className={`conv-card ${active ? "active" : ""}`}
      onClick={() => onSelect(conv.id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onSelect(conv.id);
      }}
    >
      <div className="conv-card-top">
        <MessageSquare size={14} strokeWidth={1.75} className="conv-icon" />
        <span className="conv-title">{label}</span>
        <button
          className="conv-del"
          title="Delete conversation"
          aria-label="Delete conversation"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(conv.id);
          }}
        >
          <Trash2 size={14} strokeWidth={1.75} />
        </button>
      </div>

      <div className="conv-card-meta">
        <span className="conv-chip">
          <MessageSquare size={11} strokeWidth={1.75} />
          {stats.messageCount}
        </span>
        {stats.threatCount > 0 && (
          <span className="conv-chip danger">
            <ShieldAlert size={11} strokeWidth={1.75} />
            {stats.threatCount}
          </span>
        )}
        {stats.avgLatencyMs != null && (
          <span className="conv-chip">
            <Clock size={11} strokeWidth={1.75} />
            {ms(stats.avgLatencyMs)}
          </span>
        )}
        {stats.lastProvider && (
          <span className="conv-chip subtle">
            {providerLabel(stats.lastProvider)}
          </span>
        )}
        <span className="conv-ago">{ago(updatedAt, now)}</span>
      </div>
    </div>
  );
}

export default React.memo(HistoryCard);
