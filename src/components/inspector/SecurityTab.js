import React from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Ban,
  Eye,
  KeyRound,
  CreditCard,
  Lock,
  BarChart3,
} from "../../icons";

// Renders the security posture of ONE request: input-guardrail verdict (LLM01
// injection + LLM06 redactions), output handling (LLM02), and the terminal
// completion (blocked / canary / error / done).
export default function SecurityTab({ req }) {
  if (!req)
    return (
      <div className="tab-empty muted">
        Send a message to see its guardrail activity.
      </div>
    );

  const verdict = req.verdict;
  const injection = verdict?.injection;
  const redactions = verdict?.redactions || [];
  const removed = req.outputRemoved || [];
  const breakdown = verdict?.breakdown || null;
  const checks = breakdown
    ? Object.keys(breakdown).filter((k) => k !== "_shadow")
    : [];
  const shadow = (breakdown && breakdown._shadow) || [];
  const fx = (n) => (typeof n === "number" ? n.toFixed(2) : n);

  const injScore = injection?.score;
  const injAction =
    injection?.action || (req.completion === "blocked" ? "BLOCK" : "ALLOW");

  const completionMeta = {
    blocked: {
      Icon: Ban,
      tone: "bad",
      label: "Prompt blocked by input guardrail",
    },
    canary: {
      Icon: Eye,
      tone: "bad",
      label: "Response withheld — canary egress",
    },
    error: { Icon: ShieldAlert, tone: "bad", label: "Request errored" },
    done: {
      Icon: ShieldCheck,
      tone: "good",
      label: "Delivered after guardrails",
    },
  }[req.completion] || { Icon: Lock, tone: "default", label: "In progress" };
  const CompletionIcon = completionMeta.Icon;

  return (
    <div className="sec-tab">
      <div className={`sec-status tone-${completionMeta.tone}`}>
        <CompletionIcon size={16} strokeWidth={1.75} />
        <span>{completionMeta.label}</span>
      </div>

      {/* LLM01 — prompt injection */}
      <section className="sec-block">
        <div className="sec-block-title">
          <ShieldAlert size={14} strokeWidth={1.75} />
          LLM01 · Prompt injection
        </div>
        <div className="sec-kv">
          <span>Action</span>
          <span className={injAction === "BLOCK" ? "val-bad" : "val-good"}>
            {injAction}
          </span>
        </div>
        <div className="sec-kv">
          <span>Injection score</span>
          <span>{injScore != null ? injScore : "—"}</span>
        </div>
        {injection?.signals?.length > 0 && (
          <div className="sec-signals">
            {injection.signals.map((s, i) => (
              <span key={i} className="sec-signal">
                {s.label}
              </span>
            ))}
          </div>
        )}
      </section>

      {/* LLM06 — sensitive data redaction */}
      <section className="sec-block">
        <div className="sec-block-title">
          <KeyRound size={14} strokeWidth={1.75} />
          LLM06 · Sensitive data
        </div>
        {redactions.length === 0 ? (
          <div className="muted sec-none">
            No PII or secrets detected in the input.
          </div>
        ) : (
          <ul className="sec-tag-list">
            {redactions.map((r, i) => {
              const type = typeof r === "string" ? r : r.type;
              const conf = typeof r === "object" ? r.confidence : null;
              const Icon = /CARD/i.test(type) ? CreditCard : KeyRound;
              return (
                <li key={i} className="sec-tag">
                  <Icon size={12} strokeWidth={1.75} />
                  <span>{type}</span>
                  {conf != null && <span className="sec-conf">{conf}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* LLM02 — output handling */}
      <section className="sec-block">
        <div className="sec-block-title">
          <ShieldCheck size={14} strokeWidth={1.75} />
          LLM02 · Output handling
        </div>
        {removed.length === 0 ? (
          <div className="muted sec-none">Output passed through clean.</div>
        ) : (
          <ul className="sec-tag-list">
            {removed.map((r, i) => (
              <li key={i} className="sec-tag warn">
                <ShieldCheck size={12} strokeWidth={1.75} />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Signal breakdown — per-check aggregated score + each detector's
          contribution + policy threshold + shadow observations (backend only). */}
      {breakdown && (checks.length > 0 || shadow.length > 0) && (
        <section className="sec-block">
          <div className="sec-block-title">
            <BarChart3 size={14} strokeWidth={1.75} />
            Signal breakdown
          </div>
          {checks.map((check) => {
            const b = breakdown[check];
            return (
              <div key={check} className="bd-check">
                <div className="bd-head">
                  <span className="bd-check-name">{check}</span>
                  <span
                    className={b.action === "BLOCK" ? "val-bad" : "val-good"}
                  >
                    {b.action} · {fx(b.score)}
                    {b.threshold != null ? ` / thr ${fx(b.threshold)}` : ""}
                  </span>
                </div>
                <div className="bd-contribs">
                  {(b.contributors || []).map((c, i) => (
                    <span key={i} className={`bd-sig mode-${c.mode}`}>
                      {c.id}: {fx(c.score)}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
          {shadow.length > 0 && (
            <div className="bd-shadow">
              <div className="bd-shadow-title">
                Shadow — observed, not enforced
              </div>
              <div className="bd-contribs">
                {shadow.map((s, i) => (
                  <span key={i} className="bd-sig mode-shadow">
                    {s.id}: {s.check} {fx(s.score)} → {s.action}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
