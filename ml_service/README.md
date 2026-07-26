# Guardrail ML sidecar

A separate FastAPI service hosting the guardrail models behind a stable,
model-agnostic contract. The main backend calls it through a detector adapter, so
swapping the model changes only this service.

## Contract
```
POST /score/injection  {text} -> {score, labels, model_id, version}
POST /scan/pii         {text} -> {entities:[{type,start,end,score}], model_id, version}
GET  /health           -> {status, backend}
```

## Backends (swappable)
- **heuristic** (default, zero-dep) — a broad intent-category injection scorer +
  email/phone/name PII finder. Runs anywhere; broader than the main backend's
  regex so shadow-mode visibly catches extra.
- **transformers** (`USE_REAL_MODELS=true`) — Meta **Prompt-Guard-86M** +
  Microsoft **Presidio**. Needs `requirements-ml.txt` + a spaCy model; falls back
  to heuristic if the deps/weights aren't present.

## Run
```bash
cd ml_service
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8100
# real models:  pip install -r requirements-ml.txt && USE_REAL_MODELS=true uvicorn main:app ...
```

The main backend reaches it via `ML_SERVICE_URL` (docker-compose sets this).
Enable the `promptguard` / `presidio-pii` detectors from the Control panel to use it.
