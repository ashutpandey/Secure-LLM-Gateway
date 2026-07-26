"""Model backend interface for the guardrail ML sidecar.

The sidecar exposes a STABLE contract (/score/injection, /scan/pii); the actual
model behind it is a swappable backend. That's what lets "swap the model" be a
config flag, not a rewrite: HeuristicBackend (zero-dep, always available) vs
TransformersBackend (real Prompt-Guard + Presidio, optional heavy deps).
"""

from __future__ import annotations

from typing import Protocol, TypedDict


class Entity(TypedDict):
    type: str
    start: int
    end: int
    score: float


class InjectionResult(TypedDict):
    score: float
    labels: list[str]
    model_id: str
    version: str


class PIIResult(TypedDict):
    entities: list[Entity]
    model_id: str
    version: str


class ModelBackend(Protocol):
    id: str

    def score_injection(self, text: str) -> InjectionResult: ...
    def scan_pii(self, text: str) -> PIIResult: ...
