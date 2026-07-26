# Threat model & security posture

This is a security *product* (a guardrail control plane), so it's also an attack
surface. This document maps the threats to the mitigations already in the code.
See `ARCHITECTURE.md` §2–§3 for the design rationale.

## Assets
- User prompts (may contain PII/secrets) and model output.
- The guardrail decisions + audit trail (integrity matters for compliance).
- Provider API keys and the control-plane configuration.

## Trust boundaries
- **Client is untrusted.** Enforcement is server-side; the client keeps only UX
  feedback + render-time output sanitization.
- **Detector plugins are semi-trusted.** They run in-process and are contained
  (see below); heavy/untrusted models run in the **sidecar** (process isolation).
- **The sidecar is internal** (self-hosted); detectors that would send data
  off-box must declare `egress="external"`.

## Threats → mitigations

| Threat (OWASP LLM where applicable) | Mitigation |
|---|---|
| **Prompt injection (LLM01)** | Regex fast-path + ML detector + egress **canary** (defense-in-depth); Unicode normalization defeats homoglyph/zero-width evasions |
| **Sensitive data disclosure (LLM06)** | Validated regex (Luhn/structural) + Presidio NER; user message redacted at rest; audit/metrics store **no prompt text** |
| **Insecure output handling / XSS (LLM02)** | Render-boundary sanitization (client) + server-side sanitizer; React text nodes, never `dangerouslySetInnerHTML` |
| **Plugin compromise / blast radius (LLM05 supply chain)** | Per-detector **timeout + circuit breaker + fail-mode**; **contract-version** rejection; **Signal validation** (bad output → fail-mode, can't inject a decision); **resource caps** (spans/labels/output); narrow capability surface (text + Context only) |
| **Data residency** | `egress` capability + `ALLOW_EXTERNAL_EGRESS` gate skips off-box detectors |
| **Model / regex DoS** | Input-size cap; per-tenant rate limit + token budget; bounded regex (no catastrophic backtracking); circuit breaker on a flaky sidecar |
| **Control-plane abuse** | `PATCH /registry`, `/policy/reload` gated by admin key (constant-time compare) or the DEMO_MODE flag |
| **Audit tampering** | Append-only **hash chain**, verifiable, durable across restarts (sqlite) |
| **Fail-open weakening** | Security detectors fail **closed**; the ML detector fails **open** but the regex baseline is always enforced, so an outage never removes all enforcement |

## Plugin blast-radius contract
A detector receives only `text + Context` (never secrets/DB handles). Every call
is wrapped in timeout + circuit breaker + fail-mode; its `Signal` is validated
(type/score/action) and capped (spans/labels/output) before it can influence a
decision. A plugin with an incompatible `contract_version` never registers.

## Known limitations (honest)
- **Tenant identity is self-asserted** without full auth (headers/IP). Real
  multi-tenant isolation needs authenticated identity (fastapi-users — deferred);
  today a determined actor can rotate identities to evade limits.
- **Audit is tamper-evident, not tamper-proof** — a code-level actor could
  recompute the sha256 chain. Production: HMAC with a server secret / WORM store.
- **Regex/heuristic detectors are bypassable** by novel paraphrase/encoding; the
  ML detector + canary reduce this but injection is not "solved."
- In-process state (limits, trust, cache) is **per-replica**; multi-replica needs
  a shared store (Redis) — the interfaces are swappable.
- Plugin **code** is trusted at import (allowlisted by what's registered); true
  untrusted-code isolation would need a subprocess/WASM sandbox.

## Reporting
For real deployments, wire the `EventBus` audit/log sinks to your SIEM and set
`ADMIN_API_KEY`, `ALLOW_EXTERNAL_EGRESS=false` (unless a vetted hosted detector is
needed), and `AUDIT_DB` to a durable/WORM-backed path.
