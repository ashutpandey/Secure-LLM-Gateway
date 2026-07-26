"""Provider contract — the swappable model-backend interface.

A provider streams tokens and raises `ProviderError(status=...)` on failure so
the gateway's retry/failover policy is provider-agnostic. Adding OpenAI /
Anthropic / Bedrock = implement this Protocol and register it; failover order is
config, not code.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable


class ProviderError(Exception):
    """Transport/HTTP-style failure. `status` drives retry vs failover."""

    def __init__(self, status: int, provider: str, message: str | None = None, *, retry_after_ms: int | None = None):
        super().__init__(message or f"provider {provider} failed with {status}")
        self.status = status
        self.provider = provider
        self.retry_after_ms = retry_after_ms


@runtime_checkable
class Provider(Protocol):
    name: str
    model: str

    def stream(self, prompt: str, opts: dict) -> AsyncIterator[str]:
        """Yield string tokens. Raise ProviderError before the first token for a
        retryable/failover-able error; a mid-stream raise is surfaced, not retried."""
        ...
