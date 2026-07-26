# Roadmap — Secure Streaming LLM Gateway → Full‑stack product

Status: planning. This document is the plan of record for (a) trimming
over‑implementation, (b) porting to a real frontend + backend, and (c) replacing
the regex guardrails with ML‑based scoring.

## Guiding principle

**Security enforcement belongs on the server.** Today the guardrail pipeline,
provider routing, and persistence all run in the browser — which means every
control is bypassable (open devtools, call the provider directly, edit
localStorage). The port’s north star:

- **Server = enforcement.** Input guardrails, routing/failover, egress canary,
  rate limits, secrets, persistence.
- **Client = feedback + render‑time defense.** Instant UX hints (optimistic
  “this looks like an injection”) and LLM02 output sanitization at the DOM
  boundary. Never the source of truth.

This reclassifies a lot of current code from “core logic” to “client mock /
UX‑only,” which is where the real simplification comes from.

---

## Part 1 — Simplifications & over‑implementation (low‑risk, do first)

These change no user‑facing behavior if done carefully.

| ID | Item | Action | Why |
|----|------|--------|-----|
| S1 | **Raw before/after reveal** (`meta.raw`, `MessageBubble` diff, `ResponseTab` raw block, raw trimming in storage) | Gate behind a `DEMO_MODE` flag; **off in prod** (don’t persist raw model output at rest) | Great for the demo, but storing raw poisoned/PII‑adjacent output at rest is a liability in prod. Removing it doesn’t affect safe rendering. |
| S2 | **Double sanitize on `done`** — `ChatContext` re‑runs `sanitizeOutput(lastRaw)` on the `done` event to recompute `removed`, which the last rAF commit already computed | Stash the last commit’s `removed` in a variable and reuse it | One redundant full sanitize per request. |
| S3 | **`activeProvider` stored twice** — as a top‑level state field *and* on each request record | Derive header’s provider from the latest request; drop the separate field (optional) | Minor duplication; single source of truth. |
| S4 | **Client input guardrails as enforcement** | Keep them, but demote to *optimistic UX only*; the server verdict is authoritative | Client scan is bypassable; keeping it only for instant feedback is fine. |
| S5 | **Mock provider failure knobs** (`failTimes`, `stall`, `failAfterTokens`, …) | Move to a test‑only fixtures module; keep the demo’s subset | Keeps prod provider code lean; knobs are test/demo scaffolding. |
| S6 | **`services/gateway.js` + `providers.js` (~350 lines)** | Becomes a thin client + a **server** implementation; keep the mock only for offline dev/Storybook | This is the single biggest chunk that *moves* rather than grows. |
| S7 | **`verify/runChecks.js` in‑app runner** | Keep (it’s the required “Security Sandbox”), but it now also backs the Jest suite — no duplicate assertions | Already deduped; note only. |

**Not worth removing:** the 3→5 context split (it’s the in‑constraint render
optimization), rAF coalescing, Luhn/structural validators, the canary. These
earn their keep.

---

## Part 2 — Backend architecture (Python)

### Stack (decided)
- **Python 3.11 + FastAPI** — the single backend. Async throughout; SSE via
  `sse-starlette` (or `StreamingResponse`). The current client reader‑loop maps
  1:1 onto SSE events, so the event contract carries over unchanged.
- **FastAPI ML sidecar** — a *second* FastAPI service that hosts the guardrail
  models (Prompt‑Guard + Presidio). The main backend talks to it through an
  adapter interface, so the models can be swapped/upgraded/relocated (local →
  hosted) without touching the gateway. See Part 2b.
- **Postgres + SQLAlchemy 2.0 (async) + Alembic** — conversations, messages,
  audit log, request metrics. SQLite for local dev.
- **Pydantic v2** — request/response + event schemas (one source of truth,
  mirrored to TS types on the client).
- **fastapi-users** (or JWT) — per‑user conversations. **Redis** — rate limiting,
  optional streaming session state.
- **Frontend stays React** (current CRA) — only its data layer changes (Part 4).

### Repo layout
```
/frontend                     # existing React app (data layer swapped in Part 4)
/backend
  app/
    main.py                   # FastAPI app, router mounts, middleware
    config.py                 # pydantic-settings; env-validated secrets
    api/                      # chat.py, conversations.py, guardrails.py, health.py
    core/                     # sse.py, errors.py, deps.py
    gateway/                  # orchestrator: routing + retry + failover + canary
    providers/                # base.py (Protocol) + mock.py, openai.py, anthropic.py + registry.py
    guardrails/               # base.py (Detector Protocol, Signal, Verdict)
      registry.py             # decorator-based plugin registry
      normalize.py
      input/                  # regex_injection.py, promptguard.py, presidio_pii.py
      output/                 # sanitizer.py, moderation.py
      egress/                 # canary.py
      policy.py               # policy engine (config-driven thresholds)
    persistence/              # models.py, repo.py, db.py, migrations/
    schemas/                  # pydantic DTOs + event models
  ml_service/                 # the FastAPI sidecar
    main.py                   # /score/injection, /scan/pii, /health
    models/                   # promptguard.py, presidio_pii.py (loaders)
  tests/                      # pytest: guardrails, gateway resilience, red-team gate
```

### API surface
```
POST   /api/chat                 → SSE: {sanitized?, provider, retry, fallback, token, canary, done, error}
GET    /api/conversations        → list projections (no bodies)
POST   /api/conversations        → create
GET    /api/conversations/{id}   → full snapshot
DELETE /api/conversations/{id}
POST   /api/guardrails/scan      → { verdict, signals[] }  (client optimistic-UX pre-check)
GET    /api/health

# --- Control plane (what makes the design demonstrable, see Part 2c) ---
GET    /api/registry             → all plugins (providers + detectors): id, kind,
                                    model_id, version, enabled, mode, weight, latency
PATCH  /api/registry/{id}        → { enabled?, mode: enforce|shadow|off, weight? }  (live, no redeploy)
POST   /api/redteam/run          → run the labeled corpus against the CURRENT config
                                    → confusion matrix + per-detector attribution
```

### What moves server‑side
- The entire `createGateway` pipeline → `backend/app/gateway` (input scan →
  retry/failover → egress canary → token stream).
- Real provider SDKs behind the provider Protocol, keyed by server‑side secrets;
  the mock provider stays as one registered implementation for dev/tests.
- Persistence (replaces localStorage), audit log, and the metrics already
  computed (ttft, duration, tokens/s) written per request.
- Real rate limiting → genuine 429s the existing failover logic already handles.

---

## Part 2b — Extensibility: plugin architecture (the priority)

Everything swappable is defined by a small **Protocol** + a **registry**, so
adding a model/provider = drop one file + enable it in config. Nothing in the
gateway imports a concrete model or SDK directly.

### Provider plugins
```python
class Provider(Protocol):
    name: str
    model: str
    async def stream(self, prompt: str, opts: dict) -> AsyncIterator[str]: ...
# providers raise ProviderError(status=429/500/504,...) so the gateway’s
# retry/failover policy is provider-agnostic.
@register_provider("anthropic")
class AnthropicProvider: ...
```
Failover order + which providers are active come from config, not code.

### Guardrail detector plugins  ← this is what makes “port an ML model easily” true
```python
@dataclass
class Signal:            # what every detector returns
    check: str           # "LLM01" | "LLM06" | "LLM02"
    score: float         # 0..1
    labels: list[str]
    action_hint: str     # "BLOCK" | "SANITIZE" | "ALLOW" | "REDACT"
    spans: list[Span]    # optional (for redaction)
    meta: dict

class Detector(Protocol):
    id: str
    stage: str           # "input" | "output" | "egress"
    async def analyze(self, text: str, ctx: Context) -> Signal: ...

@register_detector
class RegexInjection(Detector):  ...        # fast-path, offline fallback
@register_detector
class PromptGuard(Detector):     ...        # calls the ML sidecar via an adapter
@register_detector
class PresidioPII(Detector):     ...
```
- **Swapping a model** = write a new `Detector` (or a new sidecar adapter behind
  the same HTTP contract) and flip it on in `guardrails.yaml`. The pipeline and
  policy engine don’t change.
- The **pipeline** runs the enabled detectors for a stage (in parallel where
  possible) and hands their `Signal`s to the **policy engine**.

### Policy engine
Config‑driven: weights per signal, thresholds per action, per‑tenant overrides.
Combines {regex, ML injection, PII confidence, canary, output moderation} →
`BLOCK | SANITIZE | ALLOW`, and records *which* signals fired for the audit log.

### Detector modes — `enforce | shadow | off` (the demo’s secret weapon)
Every detector runs in one of three modes, flippable live via the control plane:
- **enforce** — its `Signal` counts toward the policy decision.
- **shadow** — it runs and is logged/shown in the Inspector, but does **not**
  affect the outcome. This is how you roll out a new ML model safely and how you
  *show* “the new model would have caught this” side‑by‑side with the incumbent.
- **off** — not executed.

Shadow mode turns the extensibility story from a claim into a live comparison:
run regex in `enforce` and Prompt‑Guard in `shadow`, and the Inspector shows both
scores on every message before you promote the ML model to `enforce` with one click.

### ML sidecar contract (stable, model‑agnostic)
```
POST /score/injection  {text} → {score, labels, model_id, version}
POST /scan/pii         {text} → {entities:[{type,start,end,score}], model_id}
GET  /health
```
Swap Prompt‑Guard → Llama‑Guard, or local → hosted, by changing only the sidecar
implementation; the detector adapter and everything above it stay put.

---

## Part 3 — Guardrails 2.0 (ML‑based scoring)

Pattern: **regex fast‑path + ML scorer + policy engine** — regex is a cheap,
high‑precision pre‑filter and offline fallback, not the decision maker. All of
it is expressed as detector plugins (Part 2b), served by the FastAPI sidecar.

### Input — LLM01 (prompt injection / jailbreak)
- **Meta Prompt‑Guard** (86M, BERT‑class) in the sidecar (transformers/ONNX) →
  benign/injection/jailbreak probabilities. **Llama Guard 3** as an optional
  heavier taxonomy detector. **LLM‑judge** only for borderline scores.
- Flow: `normalize → RegexInjection → PromptGuard → (borderline?) LLMJudge → policy`.

### Input — LLM06 (PII / secrets)
- **Microsoft Presidio** in the sidecar (NER + context + checksum validators;
  ships card/SSN recognizers with Luhn). Keep the structured card/SSN/key
  regex+Luhn as a fast detector / offline fallback. Retire the bespoke
  `LONG_TOKEN` fuzzy detector once Presidio is in.

### Output — LLM02 (insecure output handling)
- Keep render‑boundary sanitization on the client. Add a **server‑side**
  sanitizer detector as defense‑in‑depth. If rich rendering is added later:
  **DOMPurify** on the client + a markdown parser. Optional output‑moderation
  detector for harmful content.

### Serving — FastAPI sidecar (decided)
Self‑host Prompt‑Guard + Presidio in `ml_service/`; the main backend calls it via
the adapter. Calibrate thresholds against the labeled red‑team corpus, run as a
**CI gate** (fpRate == 0, catchRate ≥ floor).

---

## Part 4 — Frontend refactor for the backend

- Replace the client `gateway.stream()` with a `fetch()`+SSE reader (same event
  `switch`, minimal diff) + **AbortController** for cancel/stop.
- Replace `ConversationsContext` localStorage with server calls; adopt
  **TanStack Query** for server state (list/create/get/delete + the chat
  mutation). **Keep `useReducer`** for ephemeral stream/UI state — that split is
  still correct.
- Generate **TS types from the backend’s Pydantic/OpenAPI** so the event and DTO
  contracts can’t drift.
- Add: **retry a failed message**, optimistic guardrail feedback via
  `/api/guardrails/scan`, auth‑gated conversation list, real loading/empty/error
  states.

### Control‑plane UI (the “wow” surface — builds on the existing Sandbox/Inspector)
- **Registry panel** (new Sandbox tab): live list of every provider + detector
  with `model_id`, `version`, `latency`, and a mode switch
  (`enforce | shadow | off`) + weight slider. Toggling calls `PATCH /api/registry`.
  This is the architecture, made operable on screen.
- **Signal breakdown** (Inspector → Security tab, extended): for the selected
  request, show *each* detector’s `Signal` (id, score, labels, mode) and the
  policy math that combined them into the decision. Shadow signals shown greyed,
  clearly “observed, not enforced.”
- **Live model swap**: flip LLM01 from `regex` to `promptguard` (or run one in
  shadow) and re‑send — same pipeline, different brain, visible in the breakdown.
- **Red‑team compare**: the existing Red‑team panel gains a “compare configs”
  mode — run the corpus under the current registry config and show catch/FP
  deltas vs the regex‑only baseline in one table.

---

## Part 5 — Other hardening / gaps

- **Tests:** component/integration tests (React Testing Library); keep guardrail
  + resilience Jest suites; wire a **CI pipeline** (lint + test on PR); red‑team
  thresholds as a gate.
- **Secrets/config:** `.env` + schema validation; never ship keys to the client.
- **Rendering:** if rich text is wanted, markdown + DOMPurify (today’s plain‑text
  render is safe but limited).
- **a11y:** finish the sandbox focus *trap* (Tab cycling) — Escape/focus/restore
  already done.
- **UX:** conversation search/export, message copy (exists), keyboard map, i18n.
- **Resilience:** resumable streams (sequence IDs) so a mid‑stream failure can
  recover instead of only surfacing.
- **Observability:** ship audit log + metrics to a store; error tracking in the
  `ErrorBoundary` hook.

---

## Part 6 — Phasing (every milestone ends in something you can demo)

- **M0 — Cleanup (½ day):** S1–S3, S5. *Demo:* the current app, unchanged, but
  raw‑at‑rest gated behind `DEMO_MODE`.
- **M1 — Python backend + plugin core (2–3 days):** FastAPI app; port the
  gateway + guardrails to `backend/`; **Provider/Detector Protocols + registry +
  policy engine** (Part 2b); SSE endpoint; mock provider; `GET /api/registry`.
  Client swaps to `fetch` SSE. *Demo:* same UX, now server‑enforced, and a
  read‑only Registry panel listing the live plugins.
- **M2 — Control plane live (1–2 days):** `PATCH /api/registry`, detector
  `enforce|shadow|off` modes, Signal breakdown in the Inspector. *Demo:* toggle a
  detector off/on and watch behavior change; see per‑detector signals + policy math.
- **M3 — Persistence + auth (2–3 days):** Postgres + SQLAlchemy/Alembic,
  conversations API, fastapi-users; TanStack Query; TS types from OpenAPI.
  *Demo:* multi‑user, durable history, reload‑safe.
- **M4 — Real providers + limits (2 days):** Anthropic/OpenAI provider plugins,
  env‑validated secrets, rate limiting. *Demo:* real streamed answer, then force a
  429 and watch transparent failover.
- **M5 — Guardrails 2.0 / the headline (3–5 days):** FastAPI ML sidecar
  (Prompt‑Guard + Presidio) behind the sidecar contract; PromptGuard/Presidio
  detector plugins; red‑team compare. *Demo:* the money shot — regex in
  `enforce`, Prompt‑Guard in `shadow`, send a novel injection regex misses →
  shadow catches it → promote to `enforce` with one click; PII regex→Presidio for
  names/addresses; red‑team catch/FP deltas table.
- **M6 — Hardening (ongoing):** CI (pytest + red‑team gate + frontend tests),
  cancel/retry, server‑side output sanitizer, DOMPurify (if rich text), a11y
  focus trap, observability, `docker-compose up` one‑command demo.

## Decisions (resolved)
1. **Backend:** Python only — **FastAPI**, designed plugin‑first so new
   models/providers port in via Protocol + registry (Part 2b).
2. **ML serving:** self‑hosted **FastAPI sidecar** (Prompt‑Guard + Presidio),
   reached through a swappable adapter.
3. **Providers:** **real keys available** — wire Anthropic/OpenAI plugins in M3,
   keep mock as a registered dev/test provider.
4. **Server state:** **TanStack Query** for server data; `useReducer` stays for
   ephemeral stream/UI state.
