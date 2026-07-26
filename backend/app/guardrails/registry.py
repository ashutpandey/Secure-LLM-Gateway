"""Detector registry — the control plane's data structure.

Detectors self-register at import time via `@register_detector`. The registry
tracks each one's live control state (mode, weight, enabled) which the control-
plane API (`GET/PATCH /api/registry`) reads and mutates. The Guardrail Service
asks the registry which detectors to run for a stage and in what mode.

Adding a model = drop a file that implements `Detector` and decorate it. Nothing
here or upstream changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import SUPPORTED_CONTRACT_VERSION, Detector, Mode, Stage


@dataclass
class DetectorEntry:
    detector: Detector
    mode: Mode = Mode.ENFORCE
    weight: float = 1.0
    # rolling health, updated by the service (surfaced in the registry API)
    last_latency_ms: float | None = None
    error_count: int = 0

    def describe(self) -> dict:
        d = self.detector
        return {
            "id": d.id,
            "kind": "detector",
            "stage": d.stage.value,
            "check": d.check,
            "mode": self.mode.value,
            "weight": self.weight,
            "fail_mode": d.fail_mode.value,
            "contract_version": d.contract_version,
            "egress": getattr(d, "egress", "internal"),
            "model_id": getattr(d, "model_id", None),
            "version": getattr(d, "version", None),
            "last_latency_ms": self.last_latency_ms,
            "error_count": self.error_count,
        }


class DetectorRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, DetectorEntry] = {}

    def register(self, detector: Detector, *, mode: Mode = Mode.ENFORCE, weight: float = 1.0) -> None:
        if detector.id in self._entries:
            raise ValueError(f"detector id already registered: {detector.id}")
        self._entries[detector.id] = DetectorEntry(detector=detector, mode=mode, weight=weight)

    def get(self, detector_id: str) -> DetectorEntry:
        return self._entries[detector_id]

    def for_stage(self, stage: Stage) -> list[DetectorEntry]:
        return [e for e in self._entries.values() if e.detector.stage == stage and e.mode != Mode.OFF]

    def all(self) -> list[DetectorEntry]:
        return list(self._entries.values())

    def set_mode(self, detector_id: str, mode: Mode) -> DetectorEntry:
        e = self._entries[detector_id]
        e.mode = mode
        return e

    def set_weight(self, detector_id: str, weight: float) -> DetectorEntry:
        e = self._entries[detector_id]
        e.weight = weight
        return e


# Module-level singleton + decorator. Detectors register their *instance* so the
# service can call them directly; config (guardrails.yaml) can override mode/weight
# at startup, and the control-plane API can override them live.
REGISTRY = DetectorRegistry()

# Pending registrations captured at import time; applied by build_registry() so
# startup config can set the initial mode/weight deterministically.
_PENDING: list[Detector] = []


def register_detector(cls):
    """Class decorator: instantiate and queue the detector for registration.

    Fails fast on a plugin that doesn't satisfy the protocol OR declares an
    incompatible contract version — such a plugin never runs (blast-radius).
    """
    instance = cls()
    if not isinstance(instance, Detector):
        raise TypeError(f"{cls.__name__} does not satisfy the Detector protocol")
    if getattr(instance, "contract_version", None) != SUPPORTED_CONTRACT_VERSION:
        raise TypeError(
            f"{cls.__name__} contract_version={getattr(instance, 'contract_version', None)} "
            f"!= supported {SUPPORTED_CONTRACT_VERSION}"
        )
    _PENDING.append(instance)
    return cls


def build_registry(config: dict | None = None) -> DetectorRegistry:
    """Apply queued detectors to the singleton using startup config overrides.

    `config` shape: { detector_id: { mode, weight, enabled } }
    """
    config = config or {}
    for det in _PENDING:
        cfg = config.get(det.id, {})
        if cfg.get("enabled", True) is False:
            mode = Mode.OFF
        else:
            mode = Mode(cfg.get("mode", "enforce"))
        weight = float(cfg.get("weight", 1.0))
        if det.id not in REGISTRY._entries:  # idempotent across reloads
            REGISTRY.register(det, mode=mode, weight=weight)
    return REGISTRY
