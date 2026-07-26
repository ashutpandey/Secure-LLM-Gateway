# Secure Streaming LLM Gateway

A streaming chat console with a pluggable, ML-ready **guardrail control plane**
(OWASP LLM Top 10) and transparent provider failover. React frontend + Python
FastAPI backend.

- **`ROADMAP.md`** — build plan & phasing (cycles)
- **`ARCHITECTURE.md`** — the design of record (data plane vs control plane, plugin model, prior-art)
- **`DEMO_PLAN.md`** — how to show it off, step by step
- **`SECURITY.md`** — threat model & security posture
- **`OPERATIONS.md`** — SLOs, runbook, dashboards, scaling
- **`backend/README.md`** · **`ml_service/README.md`** — service details
- **`deploy/k8s/`** — Kubernetes manifests · **`.github/workflows/ci.yml`** — CI

## Run

### Full stack (recommended — enables the control plane)
```bash
docker-compose up --build
# frontend → http://localhost:3000   backend → http://localhost:8000
```
The frontend is pointed at the backend via `REACT_APP_API_BASE`, so chat streams
through the real guardrail pipeline and the **Sandbox → Control** and
**Sandbox → What-if** tabs manage the live registry/policy.

### Frontend only (self-contained, no backend)
```bash
npm install && npm start
```
Runs on the in-browser mock gateway (codesandbox-friendly). The control-plane
tabs show a "connect a backend" note.

### Backend only / tests
```bash
cd backend && pip install -r requirements.txt && pytest && uvicorn app.main:app --reload
```

## The demo in one line
Open **Sandbox → Control**, flip a detector to `shadow`, send a prompt, watch its
signal in the Inspector's **Signal breakdown** without it affecting the decision —
then flip it to `enforce` and re-send. Same pipeline, swapped brain, no redeploy.
