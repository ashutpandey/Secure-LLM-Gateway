# Operations — SLOs, runbook, dashboards

How to run and keep this healthy in production. See `SECURITY.md` for the threat
model and `ARCHITECTURE.md` for the design.

## SLOs (starting targets)
| SLO | Target | Source |
|---|---|---|
| Availability (`/api/chat` 2xx or graceful failover) | 99.5% | LB / `provider.*.completed` vs `request_error` |
| Time-to-first-token p95 | < 1.5s (mock) / model-dependent | client metric + gateway latency |
| Guardrail catch-rate (LLM01/02/06) | ≥ 90% | red-team gate (CI) |
| Guardrail false-positive rate | 0% on the corpus | red-team gate (CI) |
| Control-plane change auditability | 100% | audit chain (`integrity_ok`) |

## Health & probes
- **Liveness:** `GET /api/health` → process up.
- **Readiness:** `GET /api/ready` → serving; reports (but does not fail on) the
  optional ML sidecar, so a sidecar blip never drains the pool.

## Dashboards (from `GET /api/metrics`)
- **Security:** `events.input_blocked`, `events.input_redacted`, `events.canary_tripped` (rates + spikes).
- **Reliability:** `events.provider_failover`, `events.request_error`, `provider.<name>.completed`.
- **Latency:** `histograms.request_latency_ms` (avg/min/max; export percentiles from your APM).
- **Control plane:** circuit states + cache hit-rate from `GET /api/registry`.
- **Audit:** `GET /api/audit` `integrity_ok` must be `true`.

## Alerts
- `request_error` rate > 5% for 5m → provider/gateway incident.
- Any circuit `open` for > 2m → a detector/sidecar is down (see runbook).
- `integrity_ok == false` → **page**: audit tampering/corruption.
- 429 rate climbing → capacity/limit tuning or abuse.

## Runbook
- **ML sidecar down** → ML detectors fail-**open**; regex baseline still enforces.
  Circuit opens and stops calling it. Fix the sidecar; the circuit half-opens and
  recovers automatically. No chat impact.
- **Primary provider outage / 429s** → gateway retries then fails over to the next
  provider; mock is the last resort. Confirm via `events.provider_failover`. If all
  real providers are down, add/rotate keys or reorder `PROVIDER_CHAIN`.
- **Circuit stuck open** → dependency still failing; check the detector/sidecar
  logs. It won't hammer the dep (that's the point). Resolve the dep.
- **Rate-limit / budget 429s** → tune `RATE_CAPACITY`, `RATE_REFILL_PER_S`,
  `TOKEN_BUDGET_PER_DAY`, or investigate a noisy tenant/IP.
- **Audit integrity false** → suspected tampering/corruption. Preserve the DB,
  investigate; production should HMAC the chain + use a WORM store (see SECURITY.md).
- **Over-blocking (false positives)** → check the Inspector breakdown for the
  culprit detector; drop it to `shadow` via `PATCH /api/registry`, or retune
  thresholds via `POST /api/policy/simulate` then `policy.yaml` + reload.

## Load & chaos testing
```bash
python scripts/loadtest.py --base http://localhost:8000 -n 200 -c 20
```
Chaos: drive load while forcing failures (DEMO_MODE) to verify failover +
circuit-breaker hold — e.g. send with `opts={"force_primary_error":429}`.

## Scaling notes
- Backend/ml-service scale horizontally (stateless request path). In-process
  state (rate limits, trust, session memory, signal cache, in-memory audit) is
  **per replica** — move to **Redis** for multi-replica coherence; the interfaces
  (limits, tracker, cache, audit store) are already swap-shaped.
- Durable audit uses a PVC (`ReadWriteOnce`); for multi-writer use Postgres.
- **Frontend in prod:** build static assets and serve via a CDN/nginx instead of
  the CRA dev server (the k8s manifest uses the dev server for parity with compose).

## Production checklist
- `DEMO_MODE=false`, `ALLOW_CONTROL_PLANE_WRITES=false` (or set `ADMIN_API_KEY`).
- `ALLOW_EXTERNAL_EGRESS=false` unless a vetted hosted detector is required.
- `AUDIT_DB` on durable storage; secrets from a Secret manager, never the client.
- CI red-team gate green; SLO dashboards + alerts wired to the `/metrics` + audit.
