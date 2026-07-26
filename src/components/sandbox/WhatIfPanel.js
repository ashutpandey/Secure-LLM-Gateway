import React, { useEffect, useState } from "react";
import { apiClient } from "../../services/apiClient";
import { BACKEND_ENABLED } from "../../config";
import { Target, ShieldAlert } from "../../icons";

// Policy what-if: dry-run alternate thresholds against the recent evaluations the
// backend recorded (signals only, no prompt text), and see how many decisions
// would flip. This is the payoff of keeping the Policy Engine a PURE function —
// you can simulate a config change with zero risk before applying it.

export default function WhatIfPanel() {
  const [block, setBlock] = useState(0.85);
  const [trust, setTrust] = useState(0.2);
  const [current, setCurrent] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!BACKEND_ENABLED) return;
    apiClient
      .getPolicy()
      .then((p) => {
        setCurrent(p);
        const b = p.policy?.block_thresholds?.LLM01;
        if (typeof b === "number") setBlock(b);
        if (typeof p.policy?.trust_sensitivity === "number")
          setTrust(p.policy.trust_sensitivity);
      })
      .catch((e) => setError(e.message));
  }, []);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(
        await apiClient.simulatePolicy({
          block_thresholds: { LLM01: Number(block) },
          trust_sensitivity: Number(trust),
        })
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!BACKEND_ENABLED) {
    return (
      <div className="sandbox-section">
        <div className="cp-empty muted">
          <ShieldAlert size={16} strokeWidth={1.75} />
          <span>
            What-if needs the backend. Set <code>REACT_APP_API_BASE</code> to
            simulate policy against recent traffic.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="sandbox-section">
      <p className="muted">
        Dry-run alternate policy thresholds against recent evaluations
        {current ? ` (${current.sim_buffer} recorded)` : ""}. Read-only — the live
        policy is untouched.
      </p>

      <div className="wi-controls">
        <label className="wi-field">
          <span>
            LLM01 block threshold: <strong>{Number(block).toFixed(2)}</strong>
          </span>
          <input
            type="range"
            min="0.3"
            max="0.99"
            step="0.01"
            value={block}
            onChange={(e) => setBlock(e.target.value)}
          />
        </label>
        <label className="wi-field">
          <span>
            Trust sensitivity: <strong>{Number(trust).toFixed(2)}</strong>
          </span>
          <input
            type="range"
            min="0"
            max="0.6"
            step="0.01"
            value={trust}
            onChange={(e) => setTrust(e.target.value)}
          />
        </label>
        <button className="run-btn" onClick={run} disabled={busy}>
          <Target size={15} strokeWidth={1.75} />
          {busy ? "Simulating…" : "Run what-if"}
        </button>
      </div>

      {error && <div className="cp-error">{error}</div>}

      {report && (
        <div className="wi-report">
          <div className="wi-summary">
            <strong>{report.changed}</strong> of {report.sample_size} recent
            decisions would change.
          </div>
          {report.changes.length > 0 ? (
            <ul className="wi-changes">
              {report.changes.map((c, i) => (
                <li key={i}>
                  <span className={`wi-badge a-${c.before}`}>{c.before}</span>
                  <span className="wi-arrow">→</span>
                  <span className={`wi-badge a-${c.after}`}>{c.after}</span>
                  <span className="wi-reason muted">{c.reason}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="muted">No decisions change under this policy.</div>
          )}
        </div>
      )}
    </div>
  );
}
