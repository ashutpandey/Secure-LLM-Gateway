"""Guardrail ML sidecar.

A separate FastAPI service that hosts the guardrail models behind a STABLE,
model-agnostic contract. The main backend reaches it through a detector adapter,
so swapping Prompt-Guard for Llama Guard, or local for hosted, changes only this
service. The active model is a pluggable backend (see backends/): a zero-dep
heuristic by default, or the real transformers/Presidio models via USE_REAL_MODELS.

Run: uvicorn main:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backends import select_backend

app = FastAPI(title="Guardrail ML Sidecar", version="0.2.0")
backend = select_backend()


class TextIn(BaseModel):
    # Bounded so a caller can't push an unbounded tensor / regex workload.
    text: str = Field(default="", max_length=16000)


@app.get("/health")
async def health():
    return {"status": "ok", "backend": backend.id}


@app.post("/score/injection")
async def score_injection(body: TextIn):
    return backend.score_injection(body.text)


@app.post("/scan/pii")
async def scan_pii(body: TextIn):
    return backend.scan_pii(body.text)
