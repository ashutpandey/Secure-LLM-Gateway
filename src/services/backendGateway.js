// Backend-backed gateway: streams POST /api/chat (SSE) and yields the SAME event
// objects the in-process mock gateway does, so ChatContext consumes either
// transport unchanged. The only translation needed is the verdict shape —
// the backend's richer Verdict (signals + per-check breakdown) is mapped onto
// the frontend's expected {injection, redactions, sanitizedText} while ALSO
// carrying the raw breakdown/signals through for the Inspector.

import { API_BASE } from "../config";

// Backend Verdict -> the shape the reducer + SecurityTab expect (plus extras).
function adaptVerdict(v) {
  if (!v) return null;
  const bySig = {};
  (v.signals || []).forEach((s) => {
    if (!bySig[s.check]) bySig[s.check] = s;
  });
  const injBd = v.breakdown ? v.breakdown.LLM01 : null;
  const injSig = bySig.LLM01;
  const piiSig = bySig.LLM06;
  const redactions =
    piiSig && piiSig.meta && Array.isArray(piiSig.meta.redactions)
      ? piiSig.meta.redactions.map((r) => ({
          type: r.type,
          confidence: r.confidence,
        }))
      : ((piiSig && piiSig.labels) || []).map((t) => ({
          type: t,
          confidence: 1,
        }));
  return {
    action: v.action,
    reason: v.reason,
    sanitizedText: v.text,
    injection: {
      check: "LLM01",
      score: (injBd && injBd.score) ?? (injSig && injSig.score) ?? 0,
      action: (injBd && injBd.action) ?? (injSig && injSig.action_hint) ?? "ALLOW",
      signals: ((injSig && injSig.labels) || []).map((l) => ({ label: l })),
    },
    redactions,
    // Richer backend data, surfaced by the Inspector's signal breakdown.
    breakdown: v.breakdown || {},
    backendSignals: v.signals || [],
  };
}

function adaptEvent(ev) {
  switch (ev.type) {
    case "sanitized":
      return { type: "sanitized", verdict: adaptVerdict(ev.verdict) };
    case "blocked":
      return { type: "blocked", verdict: adaptVerdict(ev.verdict) };
    case "token":
      return { type: "token", raw: ev.raw };
    case "done":
      return { type: "done", provider: ev.provider };
    // provider / retry / fallback / canary / error already match 1:1
    default:
      return ev;
  }
}

// The Sandbox attack buttons use the mock gateway's camelCase knob names; the
// backend expects snake_case. Translate so the same demo controls drive both
// transports. (These knobs are honored by the backend ONLY in DEMO_MODE.)
const OPT_MAP = {
  forcePrimaryError: "force_primary_error",
  forcePrimaryFailTimes: "force_primary_fail_times",
  forcePrimaryRetryAfter: "force_primary_retry_after",
  forcePrimaryStall: "force_primary_stall",
  forcePrimaryFailAfter: "force_primary_fail_after",
  forceSecondaryError: "force_secondary_error",
  forceSecondaryStall: "force_secondary_stall",
  forceSecondaryFailAfter: "force_secondary_fail_after",
  forcePoison: "poison",
  forceCanaryLeak: "leak_canary",
};

function toBackendOpts(rest) {
  const out = {};
  for (const [k, v] of Object.entries(rest)) out[OPT_MAP[k] || k] = v;
  return out;
}

export function createBackendGateway({ apiBase = API_BASE } = {}) {
  function stream(prompt, opts = {}) {
    const { conversationId, ...rest } = opts;
    const body = JSON.stringify({
      prompt,
      conversation_id: conversationId ?? null,
      opts: toBackendOpts(rest),
    });

    return new ReadableStream({
      async start(controller) {
        try {
          const res = await fetch(`${apiBase}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
          });
          if (!res.ok || !res.body) {
            controller.enqueue({
              type: "error",
              message: `backend responded HTTP ${res.status}`,
            });
            controller.close();
            return;
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            // SSE frames are separated by a blank line.
            let idx;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              const frame = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              const dataLine = frame
                .split("\n")
                .find((l) => l.startsWith("data:"));
              if (!dataLine) continue;
              const jsonStr = dataLine.slice(5).trim();
              if (!jsonStr) continue;
              try {
                controller.enqueue(adaptEvent(JSON.parse(jsonStr)));
              } catch {
                /* ignore malformed frame */
              }
            }
          }
          controller.close();
        } catch (err) {
          controller.enqueue({
            type: "error",
            message: err.message || String(err),
          });
          controller.close();
        }
      },
    });
  }

  return { stream };
}
