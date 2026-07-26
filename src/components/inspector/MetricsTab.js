import React from "react";
import StatTile from "../shared/StatTile";
import { ms, rate, num } from "../../utils/format";
import { Timer, Clock, Zap, Activity, Gauge, BarChart3 } from "../../icons";

// Latency + throughput for the selected request, computed in ChatProvider from
// performance.now() and stored on the request record.
export default function MetricsTab({ req }) {
  if (!req)
    return (
      <div className="tab-empty muted">No metrics yet — send a message.</div>
    );

  return (
    <div className="metrics-tab">
      <div className="stat-grid">
        <StatTile
          Icon={Timer}
          label="Time to first token"
          value={ms(req.ttftMs)}
          tone={req.ttftMs != null && req.ttftMs < 400 ? "good" : "default"}
        />
        <StatTile
          Icon={Clock}
          label="Total duration"
          value={ms(req.durationMs)}
        />
        <StatTile
          Icon={Activity}
          label="Stream duration"
          value={ms(req.streamMs)}
        />
        <StatTile
          Icon={Gauge}
          label="Throughput"
          value={rate(req.tokensPerSec)}
          tone={
            req.tokensPerSec != null && req.tokensPerSec > 20
              ? "good"
              : "default"
          }
        />
        <StatTile Icon={Zap} label="Tokens" value={num(req.tokenCount)} />
        <StatTile
          Icon={BarChart3}
          label="Avg chunk"
          value={
            req.avgChunkSize != null ? `${num(req.avgChunkSize, 1)} ch` : "—"
          }
        />
      </div>

      <div className="metrics-foot muted">
        {req.retries
          ? `${req.retries} retr${req.retries === 1 ? "y" : "ies"} · `
          : ""}
        {req.fallbacks
          ? `${req.fallbacks} failover${req.fallbacks === 1 ? "" : "s"} · `
          : ""}
        completion: {req.completion || "in progress"}
      </div>
    </div>
  );
}
