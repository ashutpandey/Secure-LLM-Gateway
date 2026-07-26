import React, { useCallback, useEffect, useState } from "react";
import { apiClient } from "../../services/apiClient";
import { BACKEND_ENABLED } from "../../config";
import { RefreshCw, ShieldAlert, ShieldCheck } from "../../icons";

// Backend observability: live metrics counters + latency, and the tamper-evident
// security audit trail (hash-chained). This is the SIEM-ready surface — the same
// events feed structured logs and could fan out to an OTel/webhook sink.

function Metric({ label, value }) {
  return (
    <div className="obs-metric">
      <div className="obs-metric-val">{value}</div>
      <div className="obs-metric-label">{label}</div>
    </div>
  );
}

export default function ObservabilityPanel() {
  const [metrics, setMetrics] = useState(null);
  const [audit, setAudit] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [m, a] = await Promise.all([
        apiClient.getMetrics(),
        apiClient.getAudit(50),
      ]);
      setMetrics(m);
      setAudit(a);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (BACKEND_ENABLED) load();
  }, [load]);

  if (!BACKEND_ENABLED) {
    return (
      <div className="sandbox-section">
        <div className="cp-empty muted">
          <ShieldAlert size={16} strokeWidth={1.75} />
          <span>
            Observability needs the backend. Set <code>REACT_APP_API_BASE</code>{" "}
            to view live metrics + the audit trail.
          </span>
        </div>
      </div>
    );
  }

  const c = (metrics && metrics.counters) || {};
  const lat = metrics && metrics.histograms && metrics.histograms.request_latency_ms;

  return (
    <div className="sandbox-section">
      <div className="cp-head">
        <p className="muted">Live metrics and the tamper-evident audit trail.</p>
        <button className="ghost-btn sm" onClick={load} disabled={busy}>
          <RefreshCw size={14} strokeWidth={1.75} />
          <span>Refresh</span>
        </button>
      </div>
      {error && <div className="cp-error">{error}</div>}

      <div className="obs-metrics">
        <Metric label="blocked" value={c["events.input_blocked"] || 0} />
        <Metric label="redacted" value={c["events.input_redacted"] || 0} />
        <Metric label="canary" value={c["events.canary_tripped"] || 0} />
        <Metric label="failovers" value={c["events.provider_failover"] || 0} />
        <Metric label="completed" value={c["events.response_completed"] || 0} />
        <Metric
          label="avg latency"
          value={lat ? `${Math.round(lat.avg)}ms` : "—"}
        />
      </div>

      <div className="obs-audit">
        <div className="obs-audit-head">
          <span>Security audit</span>
          <span
            className={`obs-integrity ${
              audit && audit.integrity_ok ? "ok" : "bad"
            }`}
          >
            <ShieldCheck size={12} strokeWidth={1.75} />
            {audit ? (audit.integrity_ok ? "chain intact" : "TAMPERED") : "—"}
          </span>
        </div>
        {audit && audit.entries.length > 0 ? (
          <ul className="obs-audit-list">
            {audit.entries
              .slice()
              .reverse()
              .map((e) => (
                <li key={e.seq} className={`obs-audit-row kind-${e.kind}`}>
                  <span className="obs-seq">#{e.seq}</span>
                  <span className="obs-kind">{e.kind}</span>
                  <span className="obs-detail muted">
                    {e.check ? `${e.check} ` : ""}
                    {e.action || ""}
                    {e.provider ? ` · ${e.provider}` : ""}
                  </span>
                  <span className="obs-hash" title={e.hash}>
                    {e.hash.slice(0, 8)}
                  </span>
                </li>
              ))}
          </ul>
        ) : (
          <div className="muted">
            No security decisions recorded yet — send an attack from the Attacks
            tab.
          </div>
        )}
      </div>
    </div>
  );
}
