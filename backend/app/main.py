"""FastAPI application entry point.

Run: uvicorn app.main:app --reload  (from the backend/ directory)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, health, observability, policy, registry
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title="Secure Streaming LLM Gateway",
    version="0.1.0",
    description="Pluggable guardrail pipeline + provider failover, streamed over SSE.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(registry.router, prefix="/api", tags=["control-plane"])
app.include_router(policy.router, prefix="/api", tags=["control-plane"])
app.include_router(observability.router, prefix="/api", tags=["observability"])
