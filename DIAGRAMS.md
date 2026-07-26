# Architecture & data-flow diagrams

Mermaid diagrams for the whole system, matching the code. Paste any block into a
Mermaid renderer (GitHub renders these natively). See `ARCHITECTURE.md` for the
prose design and `SECURITY.md` for the threat model.

---

## 1. System containers (how the pieces connect)

```mermaid
flowchart LR
  User([User / Browser])

  subgraph Client
    FE["React Frontend<br/>ChatContext + panels"]
    LS[("localStorage<br/>conversations")]
    FE --- LS
  end

  subgraph Server
    BE["FastAPI Backend<br/>gateway + guardrails + control plane"]
    ML["ML Sidecar (FastAPI)<br/>heuristic | Prompt-Guard + Presidio"]
    AUD[("sqlite<br/>durable audit")]
    BE -- "HTTP /score,/scan" --> ML
    BE --- AUD
  end

  subgraph Providers
    MK["Mock provider"]
    OA[("OpenAI")]
    AN[("Anthropic")]
  end

  User --> FE
  FE -- "SSE POST /api/chat" --> BE
  FE -- "REST /api/registry,policy,metrics,audit" --> BE
  BE -- "stream tokens (retry/failover)" --> MK
  BE -.-> OA
  BE -.-> AN
```

- Enforcement is entirely server-side; the client streams from the backend and
  only sanitizes output at the render boundary (LLM02).
- The ML sidecar is reached through a stable contract; real providers are opt-in
  (mock is the keyless default + last-resort fallback).

---

## 2. Chat request — end-to-end data flow

```mermaid
sequenceDiagram
  actor U as User
  participant FE as Frontend (ChatContext)
  participant API as "POST /api/chat"
  participant LIM as RateLimiter + Budget
  participant GW as Gateway
  participant GS as GuardrailService
  participant DET as Detectors (parallel)
  participant SC as ML Sidecar
  participant POL as Policy Engine
  participant PR as Provider chain

  U->>FE: type prompt
  FE->>API: {prompt, conversation_id, opts}
  API->>LIM: allow(tenant)? budget?
  alt over limit
    LIM-->>FE: 429 + Retry-After
  else ok
    API->>GW: stream(prompt, ctx)
    Note over GW: inject trust + session_history
    GW->>GS: evaluate(INPUT)
    GS->>DET: analyze() gather + timeout + circuit + cache
    DET->>SC: (ML detectors) score/scan
    SC-->>DET: score / entities
    DET-->>GS: Signal[]
    GS->>POL: aggregate -> decide
    POL-->>GW: Verdict (+ breakdown)
    alt BLOCK
      GW-->>FE: event: blocked (audit: record)
    else ALLOW / SANITIZE / REDACT
      GW-->>FE: event: sanitized (verdict)
      loop each provider token
        GW->>GS: egress canary (windowed)
        GW-->>FE: event: token(raw)
        FE->>FE: sanitizeOutput -> render (LLM02)
      end
      GW-->>FE: event: done (metrics + trust update)
    end
  end
```

---

## 3. Guardrail pipeline — data plane vs control plane

```mermaid
flowchart TB
  subgraph CP["CONTROL PLANE (governs, live)"]
    YML["guardrails.yaml<br/>PATCH /api/registry<br/>mode: enforce|shadow|off, weight"]
    PYML["policy.yaml<br/>POST /api/policy/simulate + reload<br/>thresholds, role/trust knobs"]
  end

  subgraph DP["DATA PLANE (per request)"]
    IN["input text"] --> NORM["normalize (NFKC + strip invisible)"]
    NORM --> REG{{"Detector Registry"}}
    REG --> D1["Regex Injection (LLM01)"]
    REG --> D2["Regex PII (LLM06)"]
    REG --> D3["Prompt-Guard (LLM01, ML)"]
    REG --> D4["Presidio (LLM06, ML)"]
    REG --> D5["Known-attacks (LLM01)"]
    REG --> D6["Multi-turn (LLM01)"]
    D1 --> AGG["Signal Aggregator<br/>weighted combine per check"]
    D2 --> AGG
    D3 --> AGG
    D4 --> AGG
    D5 --> AGG
    D6 --> AGG
    AGG --> POL["Policy Engine (pure)<br/>score vs threshold, role/trust adj, span-merge"]
    POL --> V["Verdict: action + reason + breakdown"]
  end

  YML -. governs .-> REG
  PYML -. governs .-> POL
```

- **Detection** (detectors) → **Aggregation** (combine per check) → **Decision**
  (pure policy) are three isolated stages. Adding a detector never touches the
  policy engine — the aggregator folds it into the check's score.

---

## 4. Guardrail Service internals (resilience per detector)

```mermaid
flowchart TB
  EV["evaluate(text, ctx)"] --> EG{"egress external<br/>allowed?"}
  EG -- no --> SKIP["skip external-egress detectors"]
  EG -- yes --> CAP["cap input size"]
  SKIP --> CAP
  CAP --> RUN["for each detector: _run_one (gather)"]
  RUN --> CB{"circuit open?"}
  CB -- yes --> FM["fail-mode signal<br/>closed=BLOCK, open=ALLOW"]
  CB -- no --> CH{"cache hit?"}
  CH -- yes --> SIG["Signal"]
  CH -- no --> TO["asyncio.wait_for (timeout)"]
  TO -- raises --> FM
  TO -- ok --> AN["detector.analyze"]
  AN --> VAL["validate + clamp + cap spans/labels"]
  VAL --> SIG
  FM --> AGG2["aggregate -> decide"]
  SIG --> AGG2
```

---

## 5. Provider routing — retry then failover

```mermaid
flowchart TB
  S["safe prompt"] --> P1["Provider 1"]
  P1 -- "tokens" --> STREAM["stream to client"]
  P1 -- "429/5xx before 1st token" --> R{"retries left?"}
  R -- yes --> BO["backoff + jitter"] --> P1
  R -- no --> HN{"next provider?"}
  HN -- yes --> P2["Provider 2 (failover)"]
  HN -- no --> ERR["error event"]
  P2 -- tokens --> STREAM
  P2 -- fail --> ERR
  P1 -- "mid-stream failure" --> ERRMID["surface error, NO retry<br/>(avoid duplicate output)"]
  STREAM -. "per token" .-> CAN{"canary leaked?"}
  CAN -- yes --> WH["withhold response (egress block)"]
```

---

## 6. Control plane + shadow mode (the demo)

```mermaid
flowchart LR
  UI["Control panel (PATCH /registry)"] --> REG["Registry entry"]
  REG --> M{"mode"}
  M -- enforce --> ENF["counts toward the decision"]
  M -- shadow --> SH["runs + recorded, does NOT decide"]
  M -- off --> OFF["not executed"]
  ENF --> BR["Inspector: Signal breakdown"]
  SH --> BR
  BR --> NOTE["shadow signals shown greyed:<br/>'observed, not enforced'"]
```

- Flip a detector to **shadow**, watch its signal appear in the breakdown without
  changing outcomes, then flip to **enforce** — same pipeline, no redeploy.

---

## 7. Observability — sync audit vs async telemetry

```mermaid
flowchart LR
  GW["Gateway emits Events"] --> BUS["EventBus"]
  BUS -- "record() SECURITY<br/>(sync, durable)" --> AUD["AuditSink<br/>hash chain + sqlite"]
  BUS -- "record()+observe()" --> MET["MetricsSink<br/>counters + latency histogram"]
  BUS -- "observe() TELEMETRY<br/>(best-effort)" --> LOG["LogSink (structured)"]
  AUD --> EAUD["GET /api/audit (+ integrity)"]
  MET --> EMET["GET /api/metrics"]
```

- Security decisions are audited **synchronously before responding**; metrics/logs
  are best-effort so a telemetry failure never breaks a request.

---

## 8. Multi-turn / trust session loop

```mermaid
flowchart TB
  T1["turn N: evaluate"] --> REC["record probe<br/>(excl. multi-turn's own score)"]
  REC --> SM[("SessionMemory<br/>rolling probe window")]
  REC --> TR[("ConversationTracker<br/>trust decays on block")]
  SM -- "session_history" --> T2["turn N+1: ctx"]
  TR -- "conversation_trust" --> T2
  T2 --> MT["Multi-turn detector escalates<br/>on accumulated probes"]
  T2 --> POL["Policy tightens thresholds<br/>on low trust"]
```

---

## 9. Backend package structure

```mermaid
flowchart TB
  MAIN["app.main (FastAPI)"] --> API["app.api<br/>chat, registry, policy, observability, health"]
  API --> CORE["app.core<br/>state, sse, limits, conversations, sessions, deps"]
  CORE --> GW["app.gateway<br/>orchestrator"]
  CORE --> OBS["app.observability<br/>bus, sinks, store, events"]
  GW --> GUARD["app.guardrails<br/>service, registry, aggregator, policy, circuit, cache, normalize, base"]
  GW --> PROV["app.providers<br/>base, mock, openai, anthropic, registry"]
  GUARD --> DET["app.guardrails.detectors<br/>regex_injection, pii, output_sanitizer, canary,<br/>promptguard, presidio_pii, known_attacks, multiturn"]
  DET -- "ML detectors -> sidecar.py" --> MLS["ml_service (separate)"]
```

---

## 10. Frontend structure

```mermaid
flowchart TB
  APP["App"] --> PROV["UIProvider &gt; ConversationsProvider &gt; ChatProvider"]
  PROV --> SHELL["AppShell: Header, Sidebar, Workspace, Inspector, Sandbox"]
  ChatCtx["ChatProvider (useReducer)"] --> BG["backendGateway (SSE)"]
  BG --> BE["backend /api/chat"]
  ChatCtx --> SAN["sanitizeOutput at render (LLM02)"]
  Panels["Control / What-if / Signals panels"] --> AC["apiClient (REST)"]
  AC --> BE2["backend control-plane + observability"]
  ConvCtx["ConversationsProvider"] --> LS[("localStorage")]
```

- State is split by rate-of-change (ChatState/Status/Requests/History) so
  streaming re-renders only the message list, not the inspector/panels.

---

## 11. Deployment topology (docker-compose / k8s)

```mermaid
flowchart TB
  subgraph Cluster["docker-compose / k8s"]
    FE["frontend<br/>:3000"]
    BE["backend<br/>:8000 (2 replicas)"]
    ML["ml-service<br/>:8100"]
    PVC[("audit PVC / volume")]
    FE --> BE
    BE --> ML
    BE --- PVC
  end
  Browser([Browser]) --> FE
  Browser -. "REACT_APP_API_BASE" .-> BE
  SEC["Secrets: provider + admin keys"] -. env .-> BE
```

- Backend/ml-service are stateless on the request path (scale horizontally);
  in-process state (limits, trust, session, cache, in-mem audit) is per-replica →
  move to Redis for multi-replica coherence (interfaces are swap-shaped).
