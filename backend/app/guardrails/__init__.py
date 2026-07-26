"""Guardrail package public surface."""

from .base import (
    Action,
    Context,
    Detector,
    FailMode,
    Mode,
    Signal,
    Span,
    Stage,
    Verdict,
)
from .aggregator import Aggregation, CheckAggregate, aggregate
from .cache import SignalCache
from .circuit import CircuitBreaker, CircuitState
from .policy import PolicyConfig, decide, simulate
from .policy_store import PolicyStore
from .registry import REGISTRY, DetectorRegistry, build_registry, register_detector
from .service import GuardrailService

__all__ = [
    "Action",
    "Context",
    "Detector",
    "FailMode",
    "Mode",
    "Signal",
    "Span",
    "Stage",
    "Verdict",
    "PolicyConfig",
    "decide",
    "simulate",
    "PolicyStore",
    "aggregate",
    "Aggregation",
    "CheckAggregate",
    "REGISTRY",
    "DetectorRegistry",
    "build_registry",
    "register_detector",
    "GuardrailService",
    "SignalCache",
    "CircuitBreaker",
    "CircuitState",
]
