// REST client for the FastAPI backend's control-plane + policy endpoints.
// (Chat streaming lives in backendGateway.js.) Every call is scoped to API_BASE;
// callers should only use these when BACKEND_ENABLED is true.

import { API_BASE } from "../config";

async function json(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const apiClient = {
  health: () => json("/api/health"),

  // Control plane
  getRegistry: () => json("/api/registry"),
  patchDetector: (id, patch) =>
    json(`/api/registry/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // Policy
  getPolicy: () => json("/api/policy"),
  reloadPolicy: () => json("/api/policy/reload", { method: "POST" }),
  simulatePolicy: (overrides) =>
    json("/api/policy/simulate", {
      method: "POST",
      body: JSON.stringify({ overrides }),
    }),

  // Observability
  getMetrics: () => json("/api/metrics"),
  getAudit: (limit = 50) => json(`/api/audit?limit=${limit}`),
};
