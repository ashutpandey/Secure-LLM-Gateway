# Architecture — Secure Streaming LLM Gateway (target design)

Companion to `ROADMAP.md` (build order) and `DEMO_PLAN.md` (how we show it off).
This doc is the *design of record*: the layering, the hard decisions, the plugin
safety model, a prior‑art reality check, and the delivery cycles.

Your four proposed changes are all accepted. Each is folded in below with the
sharp decision it forces — because that decision, not the box on the diagram, is
what makes or breaks these systems.

---

## 1. Layered architecture (data plane vs control plane)

```
                    ┌──────────────── CONTROL PLANE ────────────────┐
                    │  Registry (providers + detectors)             │
                    │   • enabled / mode(enforce|shadow|off)/weight │
                    │   • RBAC-gated PATCH + audited                │
                    │  Policy config (hot-reloadable)               │
                    └───────────────────────────────────────────────┘
                                     ▲ reads config / modes
  Request                           │
    │                               │
    ▼                               │
┌─────────┐   evaluate(input)  ┌────────────────────┐
│ Gateway │ ─────────────────► │ Guardrail Service  │  ← cross-cutting seam
│ (route, │ ◄───────────────── │  timeouts, circuit │    (your change #1)
│  retry, │     Verdict        │  breaker, bulkhead,│
│  failover,                   │  cache, concurrency│
│  stream)│                    │  metrics, events   │
└────┬────┘                    └─────────┬──────────┘
     │                                   │ fan-out (asyncio.gather)   (change #4)
     │                          ┌────────▼─────────┐
     │                          │ Detector Registry│
     │                          │  Regex │ PromptGuard │ Presidio │ …│
     │                          └────────┬─────────┘
     │                                   │ Signal[]
     │                          ┌────────▼─────────┐
     │                          │ Signal Aggregator│  (normalize/dedupe/attribute)
     │                          └────────┬─────────┘
     │                          ┌────────▼─────────┐
     │                          │  Policy Engine   │  ← pure fn (your change #2)
     │                          │ signals+ctx→Verdict(action, reason, contributors)
     │                          └──────────────────┘
     ▼
┌──────────────┐   Provider Registry → Providers (mock, openai, anthropic, …)
│  Provider    │
│  (SSE tokens)│   Egress: canary check per token + optional output moderation
└──────────────┘

        Event bus (emitted throughout): Audit · Metrics · Logging → sinks   (change #3)
```

Two rails, always separate:
- **Data plane** = per‑request pipeline. Never imports a concrete model/SDK.
- **Control plane** = registry + policy config that governs which plugins run and
  how. Operable live; **RBAC‑gated and audited** (see §2.5 — this is a security
  boundary, not a demo toggle).

---

## 2. The hard decisions (where these systems live or die)

### 2.1 Fail‑open vs fail‑closed (per detector) — the single most important knob
When a detector times out / the sidecar is down / it throws, what happens?
- **Security detectors** (injection, canary) → **fail‑closed** by default (treat
  as suspicious or degrade to the regex fast‑path, never silently allow).
- **Enrichment detectors** (toxicity score, topic tags) → **fail‑open**.
- Configurable per detector; the chosen fail‑mode is itself recorded in the
  Verdict’s reason. *A guardrail that fails open on timeout is worse than no
  guardrail — it gives false confidence.*

### 2.2 Cascade vs parallel (your change #4, with the cost edge)
Independent detectors run concurrently (`asyncio.gather`) for lowest latency —
**but ML detectors cost money/latency**, so support two modes per stage:
- **parallel** — lowest latency, run everything, full attribution (needed for
  shadow/compare).
- **cascade** — cheap regex first; only invoke expensive ML if regex is
  inconclusive. Lowest cost.
- **short‑circuit** — in `enforce`, a high‑confidence BLOCK can cancel in‑flight
  detectors (saves cost); in `shadow`/compare we always run all for attribution.
Ordering still matters: `normalize` first; PII redaction must produce the text
that goes to the provider; egress canary runs on output. Concurrency is *within*
a dependency stage, not across the whole pipeline.

### 2.3 Sync audit vs async telemetry (your change #3, done right)
Not everything should be fire‑and‑forget:
- **Security‑decision audit** (a BLOCK/redaction) is **synchronous / at‑least‑once
  and durable** *before* responding — compliance & non‑repudiation demand it.
- **Metrics & logs** are **async fire‑and‑forget**.
Use an in‑process domain **event bus** with pluggable sinks (DB, webhook, later
Kafka) for *business* events, and **OpenTelemetry** for traces/metrics/logs so
SIEM export is a collector config, not custom code. Don’t stand up Kafka on day
one — ship the interface, add the broker sink when volume needs it.

### 2.4 Policy engine: pure function first, rules engine later (your change #2)
Signal Aggregator (normalize/dedupe) → **Policy Engine as a pure function**
`(signals, context, policy_cfg) → Verdict{action, reason, contributors}`. Pure =
trivially testable, hot‑reloadable, and **simulatable** (dry‑run a policy against
historical requests — powers the red‑team “what‑if”). Context grows over time
(user role, conversation trust, prior history) and policy *will* get complex —
keep it isolated. Offer **OPA/Rego** as a pluggable policy backend *later* if
rules outgrow declarative YAML; don’t adopt a DSL prematurely.

### 2.5 Control‑plane authorization (the vuln nobody mentions)
`PATCH /api/registry` changes what’s *enforced*. If it’s world‑writable, an
attacker turns guardrails off. It must be **admin‑RBAC only, audited, and
confirmation‑gated** in prod. In the demo it’s open; the code path is the same,
the policy differs by environment.

### 2.6 Caching: cache signals, not verdicts
Cache **detector outputs keyed by normalized‑input hash** (deterministic
detectors only), never the final verdict — because the verdict depends on
context/policy that changes. Scope cache by tenant. TTL + explicit invalidation
on model/version change. Guards against both latency *and* cache‑poisoning.

### 2.7 Buy vs build (a real senior call)
- **Provider routing/failover/cost‑tracking**: libraries like **LiteLLM** already
  normalize 100+ providers with failover + budgets. Strong case to make our
  Provider layer a thin adapter over LiteLLM and spend our energy on the
  guardrail platform (the actual differentiator). Keep the Provider Protocol so
  it’s swappable either way.
- **Telemetry**: OpenTelemetry, not a bespoke metrics format.
- **Policy**: OPA later, not now.
Build what differentiates (the pluggable, shadow‑able, attributed guardrail
control plane); buy/borrow the commodity plumbing.

---

## 3. Plugin contract & blast radius (safe third‑party integration)

Goal: “someone builds a model → drop it in” **without** letting a bad plugin
crash, hang, leak, or silently weaken the system.

- **Narrow capability surface.** A detector receives `text + typed Context`
  only — never DB handles, secrets, or network creds. Wanting external calls
  (hosted model) is a *declared capability*, not ambient access.
- **Contract versioning.** Each plugin declares `contract_version`; the registry
  rejects incompatibles at load. Every `Signal` carries `model_id + version` for
  reproducibility and cache invalidation.
- **Output validation.** A plugin’s `Signal` is schema‑validated; malformed
  output is rejected and the detector treated per its fail‑mode — a buggy plugin
  can’t inject a bogus decision.
- **Isolation + limits.** The Guardrail Service wraps every call in timeout +
  circuit breaker + try/except (bulkhead), so one plugin degrades to its fail
  mode, never takes down the pipeline. Heavy/untrusted models live in the
  **sidecar** (process isolation); resource caps on input size and concurrency.
- **Supply chain (OWASP LLM05).** Pin model weights by hash; verify checksums;
  no auto‑loading arbitrary code — plugins are allowlisted/signed. Third‑party
  detector = supply‑chain surface, treated as such.
- **Data governance.** Detectors that send data off‑box are flagged
  `egress: external`; policy/compliance can forbid them per tenant (data
  residency). Making “this model sends your prompt to a vendor” explicit is a
  feature.
- **Platform self‑defense (removing our own vulns):** bound every regex
  (ReDoS), cap input size before ML, rate‑limit per user (model DoS), isolate
  LLM‑judge output parsing (the judge itself can be injected), append‑only
  tamper‑evident audit, SSRF‑safe output links (already in LLM02), secure/fail‑
  closed defaults everywhere.

---

## 4. Prior‑art reality check (how others do it, limits, how we do better)

| System | Approach | Limitation | Our edge / what we borrow |
|--------|----------|-----------|---------------------------|
| **NeMo Guardrails** (NVIDIA) | Colang DSL, programmable input/output/dialog rails | DSL learning curve; LLM‑rail latency; no ops control plane/shadow | Borrow “rails as config” for policy; we add live registry + shadow + attribution |
| **Guardrails AI** (RAIL) | Validator hub, output schema validation, re‑ask | Output‑validation centric; embedded lib, not a service | Validator hub ≈ our detector registry; add output‑validation detectors |
| **LLM Guard** (Protect AI) | Library of input/output scanners (injection, Presidio PII, secrets, toxicity) | Library, synchronous, no control plane/shadow/routing | Very close to our detectors — **wrap its scanners as plugins**; we add the platform |
| **Rebuff** | Layered injection defense: heuristics + LLM + vector‑DB of known attacks + **canary tokens** | Injection‑only, less maintained, no PII/output, no ops plane | We already have canary; **borrow the attack vector‑DB** as a future detector |
| **Lakera Guard** | Hosted, strong ML injection/PII, low latency | Closed, per‑call cost, data leaves boundary, black‑box scores | Self‑host + transparent attribution; can wrap Lakera as *one* adapter |
| **Bedrock Guardrails / Azure Content Safety / OpenAI Moderation** | Managed policy (denied topics, PII, filters, grounding) | Vendor lock‑in, data egress, opaque, single‑vendor, no cross‑model A/B | Each becomes a *detector adapter*; we uniquely **run several and compare/shadow** them |
| **LiteLLM / Portkey / Cloudflare AI Gateway** | Provider routing, failover, caching, rate‑limit, observability | Guardrails are shallow bolt‑ons | **Borrow/build‑on** for the commodity gateway layer; our depth is the guardrail control plane |
| **OPA / Rego** | Externalized policy decisions | Rego learning curve, latency | Pluggable policy backend *later*; pure‑fn policy now |
| **Llama Guard / Prompt Guard / Presidio** | Models, not systems | N/A | We host them as detectors behind the stable sidecar contract |

### Where we currently lag (and how to close it)
- No **vector‑DB of known attacks** (Rebuff) → add as a detector (Cycle 9).
- No **LLM‑judge** for borderline scores → add, isolated (Cycle 9).
- No **groundedness/hallucination or output‑schema** checks (Guardrails AI /
  Bedrock) → output detectors (Cycle 9).
- No **multi‑turn / session‑level** attack detection (almost everyone misses
  this) → **our differentiator** (Cycle 9): gradual jailbreaks and injection
  spread across turns.
- No **per‑tenant cost/token budgets** → Cycle 7.

### Where we already lead
A single **open, self‑hostable platform** that unifies *many* detectors +
providers behind uniform contracts, with **shadow mode, live registry, decision
attribution, and cross‑model comparison** — no existing tool combines all of
these in the open. That combination is the pitch.

---

## 5. Delivery cycles

Each cycle is a coherent architectural increment with its own demo and exit gate.
Dependencies flow downward; cycles 1→4 are the spine, 5+ deepen it.

- **Cycle 0 — Foundations.** Monorepo (`/frontend`,`/backend`,`/ml_service`),
  `docker-compose`, CI bootstrap, M0 cleanups (S1–S3, S5), `DEMO_MODE`.
  *Exit:* one‑command run; current app green in CI.

- **Cycle 1 — Contracts & plugin core (the spine).** Pydantic `Signal` /
  `Verdict` / `Context`; `Detector` + `Provider` Protocols; Registry;
  **Guardrail Service** facade; **pure Policy Engine**; port regex/PII/sanitizer/
  canary as the first detectors; mock provider; `GET /api/registry`; SSE `/chat`.
  *Exit:* server‑enforced pipeline; read‑only registry visible.

- **Cycle 2 — Guardrail Service hardening (change #1 + #4).** Concurrency with
  dependency stages; per‑detector timeout + circuit breaker + **fail‑open/closed**
  policy; bulkhead; cascade/parallel/short‑circuit modes; signal cache.
  *Exit:* kill the sidecar → graceful degrade; parallel vs cascade latency shown.

- **Cycle 3 — Policy engine & context (change #2).** Signal Aggregator; isolated
  Policy Engine with `Context` (role, conversation trust, history); attribution
  in the Inspector; hot‑reload; policy **simulation/what‑if**.
  *Exit:* change a weight → decision changes; full attribution breakdown.

- **Cycle 4 — Control plane live + shadow.** `PATCH /api/registry` (**RBAC +
  audit**), `enforce|shadow|off`, Registry UI panel, Signal breakdown UI.
  *Exit:* the money shot — live model swap via shadow → promote.

- **Cycle 5 — Observability & events (change #3).** OTel traces/metrics; domain
  event bus with pluggable sinks; **sync durable audit** for security decisions;
  append‑only audit integrity.
  *Exit:* end‑to‑end request trace; audit export to a SIEM‑style sink.

- **Cycle 6 — ML detectors via sidecar (headline detection).** FastAPI sidecar
  (Prompt‑Guard + Presidio) behind the stable contract; adapter; batching;
  red‑team compare (regex vs ML deltas).
  *Exit:* novel injection caught by ML in shadow; catch/FP deltas table.

- **Cycle 7 — Providers, persistence, auth, limits.** Real providers (direct SDKs
  or LiteLLM adapter), Postgres + SQLAlchemy/Alembic, fastapi‑users, rate limits,
  per‑tenant cost/token budgets, TanStack Query frontend.
  *Exit:* multi‑user, durable, real streaming + failover + quotas.

- **Cycle 8 — Plugin safety & supply chain (blast radius).** Contract versioning,
  Signal schema validation, capability flags (`egress: external`), resource
  limits/isolation, signed/allowlisted plugins, threat model + security tests
  (ReDoS, oversized input, judge‑injection).
  *Exit:* a deliberately broken/hostile plugin degrades to fail‑mode, never
  crashes; external‑egress detector is policy‑gated.

- **Cycle 9 — Advanced detection (surpass prior art).** Multi‑turn/session‑level
  attack detection; attack vector‑DB detector; LLM‑judge (isolated) for
  borderline; output groundedness/schema validation.
  *Exit:* a gradual multi‑turn jailbreak is caught that single‑message detectors miss.

- **Cycle 10 — Productionization.** Load/chaos testing, SLOs, k8s/Helm, dashboards,
  docs, runbooks.
  *Exit:* deployable, observable, documented.

---

## 6. One‑line summary
Two rails (data/control), everything swappable behind a `Signal`/`Verdict`
contract, cross‑cutting concerns in a Guardrail Service, an isolated pure Policy
Engine, shadow‑mode for safe rollout, OTel+events for SIEM, and a plugin safety
model that bounds blast radius — a platform, not a filter.
