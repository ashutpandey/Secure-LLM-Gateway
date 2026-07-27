# Secure Streaming LLM Gateway

A streaming chat console with a pluggable, ML-ready guardrail control plane for
OWASP LLM Top 10 risks, plus transparent provider failover. The project combines
a React frontend with a FastAPI backend and an optional ML sidecar.

## Run

### Full stack (recommended)
```bash
docker-compose up --build
```
Open the frontend at http://localhost:3000 and the backend at http://localhost:8000.
The UI uses the live backend gateway, and the Security Sandbox tabs (Attacks,
Control, What-if, Signals) exercise the same guardrail pipeline.

### Frontend only
```bash
npm install && npm start
```
Runs the self-contained frontend experience for local development or sandbox use.

### Backend only / tests
```bash
cd backend
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

## Demo flow

Open the Sandbox panel, try one of the attack prompts, and watch the Inspector
and guardrail signals react in real time. The same request path can be switched
between shadow and enforce behavior to show how policy changes affect outcomes.
