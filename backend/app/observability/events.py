"""Domain events — the vocabulary the gateway emits for observability.

A small, typed event is emitted at each meaningful point in a request. Sinks
(audit / metrics / log) consume them; adding a SIEM or OTel exporter later is a
new sink, not a change to the emitters.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class EventKind:
    # Security-relevant -> go through EventBus.record (durable audit + metrics).
    INPUT_BLOCKED = "input_blocked"
    INPUT_REDACTED = "input_redacted"
    CANARY_TRIPPED = "canary_tripped"
    # Operational telemetry -> EventBus.observe (best-effort metrics/log only).
    PROVIDER_SELECTED = "provider_selected"
    PROVIDER_RETRY = "provider_retry"
    PROVIDER_FAILOVER = "provider_failover"
    RESPONSE_COMPLETED = "response_completed"
    REQUEST_ERROR = "request_error"


# The set the audit sink treats as security decisions (kept explicit so a new
# telemetry kind can't accidentally land in the tamper-evident audit log).
SECURITY_KINDS = frozenset(
    {EventKind.INPUT_BLOCKED, EventKind.INPUT_REDACTED, EventKind.CANARY_TRIPPED}
)


@dataclass(slots=True)
class Event:
    kind: str
    stage: str | None = None
    conversation_id: str | None = None
    provider: str | None = None
    action: str | None = None
    check: str | None = None
    status: int | None = None
    latency_ms: float | None = None
    meta: dict = field(default_factory=dict)
