import React, { useCallback, useEffect, useState } from "react";
import { apiClient } from "../../services/apiClient";
import { BACKEND_ENABLED } from "../../config";
import { RefreshCw, Cpu, ShieldAlert } from "../../icons";

// The control plane, made operable: every detector with a live mode switch
// (enforce / shadow / off), weight, and circuit state — backed by the real
// backend registry. Flipping a mode here changes what the pipeline enforces on
// the very next message. This is the architecture on screen.

const MODES = ["enforce", "shadow", "off"];

function Health({ service }) {
  if (!service) return null;
  const cache = service.cache;
  return (
    <div className="cp-health">
      <span className="cp-chip">strategy: {service.strategy}</span>
      {cache && (
        <span className="cp-chip">
          cache {cache.hit_rate == null ? "—" : `${Math.round(cache.hit_rate * 100)}%`} hit ·{" "}
          {cache.size} entries
        </span>
      )}
      <span className="cp-chip">sim buffer: {service.sim_buffer}</span>
    </div>
  );
}

export default function ControlPlanePanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await apiClient.getRegistry());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (BACKEND_ENABLED) load();
  }, [load]);

  const setMode = async (id, mode) => {
    setError(null);
    try {
      await apiClient.patchDetector(id, { mode });
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const setWeight = async (id, weight) => {
    try {
      await apiClient.patchDetector(id, { weight: Number(weight) });
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  if (!BACKEND_ENABLED) {
    return (
      <div className="sandbox-section">
        <div className="cp-empty muted">
          <ShieldAlert size={16} strokeWidth={1.75} />
          <span>
            Control plane needs the backend. Set <code>REACT_APP_API_BASE</code>{" "}
            (docker-compose does this) to manage the live registry.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="sandbox-section">
      <div className="cp-head">
        <p className="muted">
          Live plugin registry. Flip a detector to <strong>shadow</strong> to
          observe it without affecting decisions, then <strong>enforce</strong>{" "}
          to promote it — no redeploy.
        </p>
        <button className="ghost-btn sm" onClick={load} disabled={busy}>
          <RefreshCw size={14} strokeWidth={1.75} />
          <span>Refresh</span>
        </button>
      </div>

      {error && <div className="cp-error">{error}</div>}
      <Health service={data && data.service} />

      <div className="cp-list">
        {(data ? data.detectors : []).map((d) => (
          <div key={d.id} className={`cp-row mode-${d.mode}`}>
            <div className="cp-row-main">
              <Cpu size={14} strokeWidth={1.75} className="cp-icon" />
              <div className="cp-id">
                <span className="cp-name">{d.id}</span>
                <span className="cp-sub">
                  {d.check} · {d.model_id || "—"} v{d.version || "?"} ·{" "}
                  {d.last_latency_ms != null
                    ? `${d.last_latency_ms.toFixed(1)}ms`
                    : "idle"}
                  {d.circuit && d.circuit !== "closed" && (
                    <span className="cp-circuit"> · circuit {d.circuit}</span>
                  )}
                </span>
              </div>
            </div>
            <div className="cp-controls">
              <div className="cp-modes">
                {MODES.map((m) => (
                  <button
                    key={m}
                    className={`cp-mode ${d.mode === m ? "active" : ""}`}
                    onClick={() => setMode(d.id, m)}
                    disabled={d.mode === m}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <input
                className="cp-weight"
                type="number"
                min="0"
                max="10"
                step="0.1"
                defaultValue={d.weight}
                title="weight"
                onBlur={(e) => setWeight(d.id, e.target.value)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
