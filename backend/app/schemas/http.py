"""HTTP request/response schemas (Pydantic v2).

These are the source of truth for the client contract; generate TS types from the
OpenAPI schema so the frontend can't drift.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16_000)
    # Capped: it's used as a key in the (bounded) session/trust maps, so a huge
    # value from a direct API caller can't bloat per-entry memory.
    conversation_id: str | None = Field(default=None, max_length=128)
    # Demo/test knobs — forwarded to the mock provider. In prod these would be
    # gated to admins or removed entirely.
    opts: dict = Field(default_factory=dict)


class RegistryPatch(BaseModel):
    """Control-plane mutation. In prod this endpoint is admin-RBAC + audited."""

    mode: str | None = Field(default=None, pattern="^(enforce|shadow|off)$")
    weight: float | None = Field(default=None, ge=0, le=10)


class PolicySimulate(BaseModel):
    """What-if: partial policy overrides to dry-run against recent evaluations."""

    overrides: dict = Field(default_factory=dict)
