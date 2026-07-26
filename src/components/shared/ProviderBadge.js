import React from "react";
import { Cpu } from "../../icons";
import { providerLabel } from "../../utils/format";

// Small chip showing which provider served a request. The two mock providers
// get distinct accent colors so failover is visible at a glance.
export default function ProviderBadge({ name, model, size = "md" }) {
  if (!name) return <span className="muted">—</span>;
  const kind = name.startsWith("gpt") ? "primary" : "secondary";
  return (
    <span
      className={`provider-badge kind-${kind} size-${size}`}
      title={model || name}
    >
      <Cpu size={13} strokeWidth={1.75} />
      <span className="provider-name">{providerLabel(name)}</span>
      {model && size !== "sm" && (
        <span className="provider-model">{model}</span>
      )}
    </span>
  );
}
