import React from "react";

// Generic tab strip. `tabs` = [{ key, label, Icon }]. Controlled via `active`.
export default function Tabs({ tabs, active, onChange, size = "md" }) {
  return (
    <div className={`tabs tabs-${size}`} role="tablist">
      {tabs.map((t) => {
        const Icon = t.Icon;
        const on = t.key === active;
        return (
          <button
            key={t.key}
            role="tab"
            aria-selected={on}
            className={`tab ${on ? "on" : ""}`}
            onClick={() => onChange(t.key)}
          >
            {Icon && <Icon size={14} strokeWidth={1.75} />}
            <span>{t.label}</span>
            {typeof t.badge === "number" && t.badge > 0 && (
              <span className="tab-badge">{t.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
