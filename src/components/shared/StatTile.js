import React from "react";

// One metric cell for the Inspector's Metrics/Request tabs.
// tone: default | good | warn | bad
export default function StatTile({
  Icon,
  label,
  value,
  sub,
  tone = "default",
}) {
  return (
    <div className={`stat-tile tone-${tone}`}>
      <div className="stat-tile-head">
        {Icon && <Icon size={14} strokeWidth={1.75} />}
        <span className="stat-tile-label">{label}</span>
      </div>
      <div className="stat-tile-value">{value}</div>
      {sub != null && <div className="stat-tile-sub">{sub}</div>}
    </div>
  );
}
