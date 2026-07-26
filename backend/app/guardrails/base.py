"""Core guardrail contracts.

Everything swappable in the guardrail layer is defined here as a small set of
types + a Protocol. The gateway, the Guardrail Service, and the policy engine
only ever depend on THESE — never on a concrete model or SDK. Adding a new
detector (regex, an ML model, a hosted moderation API) means implementing
`Detector` and registering it; nothing upstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

# The Detector contract the host currently understands. A plugin declaring a
# different `contract_version` is rejected at registration (blast-radius: a
# plugin built against an incompatible interface never runs). Bump when the
# Signal/Detector shape changes incompatibly.
SUPPORTED_CONTRACT_VERSION = 1

# Resource caps a single detector's output may occupy (memory containment
# against a buggy/hostile plugin returning millions of spans/labels).
MAX_SPANS_PER_SIGNAL = 1000
MAX_LABELS_PER_SIGNAL = 100
MAX_TRANSFORMED_CHARS = 64_000


class Stage(str, Enum):
    """Where in the request lifecycle a detector runs."""

    INPUT = "input"  # before the prompt reaches a provider
    OUTPUT = "output"  # on model output before it reaches the client
    EGRESS = "egress"  # per-token leak checks (e.g. canary)


class Action(str, Enum):
    """A single detector's recommendation, or the policy's final decision."""

    ALLOW = "ALLOW"
    SANITIZE = "SANITIZE"  # continue, but with modified text
    REDACT = "REDACT"  # PII removed from the text
    BLOCK = "BLOCK"  # reject the request


class Mode(str, Enum):
    """Control-plane mode for a detector (flippable live, see registry)."""

    ENFORCE = "enforce"  # its signal counts toward the decision
    SHADOW = "shadow"  # runs + is recorded, but does NOT affect the decision
    OFF = "off"  # not executed


class FailMode(str, Enum):
    """What to do when a detector errors/times out — THE critical safety knob."""

    CLOSED = "closed"  # treat as suspicious / degrade safely (security detectors)
    OPEN = "open"  # ignore the failure (enrichment detectors)


@dataclass(slots=True)
class Span:
    """A character range a detector wants acted on (e.g. PII to redact)."""

    start: int
    end: int
    label: str
    replacement: str | None = None


@dataclass(slots=True)
class Signal:
    """The uniform output of EVERY detector.

    The policy engine consumes only Signals, which is what makes it model-
    agnostic: regex, an ML classifier, and a hosted API all speak this shape.
    """

    detector_id: str
    check: str  # "LLM01" | "LLM06" | "LLM02" | ...
    score: float  # 0..1 confidence that this check tripped
    action_hint: Action = Action.ALLOW
    labels: list[str] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)
    # Text the detector produced if it rewrote the input (sanitized/redacted).
    transformed_text: str | None = None
    mode: Mode = Mode.ENFORCE  # stamped by the service from live config
    model_id: str | None = None  # for reproducibility / cache invalidation
    version: str | None = None
    latency_ms: float | None = None
    error: str | None = None  # set when the detector failed (see FailMode)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Context:
    """Everything a detector / the policy engine may consider besides the text.

    Deliberately a *narrow* capability surface: detectors get this, never DB
    handles or secrets. It grows over time (role, trust, history) without
    widening what a plugin can touch.
    """

    stage: Stage
    user_id: str | None = None
    user_role: str = "user"  # "user" | "admin" | ...
    conversation_id: str | None = None
    conversation_trust: float = 0.5  # 0..1, reputation of this session
    turn_index: int = 0
    canary: str | None = None  # seeded per request for egress checks
    tenant: str = "default"
    # Recent prior turns in this conversation (summaries only: {score, labels}),
    # populated by the gateway from SessionMemory. Enables cross-turn detection
    # without widening a detector's capability surface beyond text + Context.
    session_history: list = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Verdict:
    """The Guardrail Service's answer for one stage of one request."""

    action: Action
    reason: str
    # The (possibly sanitized/redacted) text to use going forward.
    text: str
    # Every signal that contributed, enforced AND shadow — full attribution.
    signals: list[Signal] = field(default_factory=list)
    stage: Stage = Stage.INPUT
    # Per-check attribution: { check: {score, action, threshold, contributors} }.
    # This is what the Inspector renders as the "why" behind the decision.
    breakdown: dict = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.action == Action.BLOCK


@runtime_checkable
class Detector(Protocol):
    """The one interface a guardrail plugin implements.

    Contract:
      * `analyze` is pure w.r.t. external state where possible, async, and MUST
        return a `Signal` (never raise for a normal "clean" result).
      * It may raise on genuine failure; the Guardrail Service wraps every call
        in a timeout + the detector's FailMode, so a bad plugin degrades to its
        fail behavior rather than crashing the pipeline.
    """

    id: str
    stage: Stage
    check: str
    fail_mode: FailMode
    contract_version: int
    # OPTIONAL (read via getattr, so third-party plugins that omit it still
    # satisfy the protocol): `egress` = "internal" (default) | "external". A
    # detector that sends prompt data off-box (a hosted moderation API) must
    # declare egress="external" so data-residency policy can forbid it.

    async def analyze(self, text: str, ctx: Context) -> Signal: ...
