"""Guardrail Service — the cross-cutting seam between the gateway and detectors.

The gateway calls exactly one thing: `await service.evaluate(text, ctx)`. This
layer owns everything the gateway must NOT: concurrency, per-detector timeouts,
circuit breaking, signal caching, fail-open/closed handling, mode application,
health accounting — and it wires detection -> aggregation -> policy.

Pipeline per stage:  detectors (concurrent) -> aggregate() -> decide()

Execution strategy:
  * parallel (default) — all detectors run under asyncio.gather; every signal is
    produced, so SHADOW attribution and comparison are complete.
  * cascade — cheapest detectors first; stop once the enforced signals already
    BLOCK, skipping remaining (more expensive) detectors.

Resilience per detector: timeout, circuit breaker, and fail-open/closed.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from .aggregator import aggregate
from .base import (
    MAX_LABELS_PER_SIGNAL,
    MAX_SPANS_PER_SIGNAL,
    MAX_TRANSFORMED_CHARS,
    Action,
    Context,
    FailMode,
    Signal,
    Stage,
    Verdict,
)
from .cache import SignalCache
from .circuit import CircuitBreaker
from .normalize import normalize_for_analysis
from .policy import PolicyConfig, decide
from .registry import DetectorRegistry


class GuardrailService:
    def __init__(
        self,
        registry: DetectorRegistry,
        policy: PolicyConfig | None = None,
        *,
        per_detector_timeout_s: float = 2.0,
        strategy: str = "parallel",
        cache: SignalCache | None = None,
        circuit_config: dict | None = None,
        policy_provider=None,  # optional callable -> PolicyConfig (hot-reload)
        sim_buffer_size: int = 200,
        max_input_chars: int = 16000,
        allow_external_egress: bool = True,
    ) -> None:
        self.registry = registry
        self._policy = policy or PolicyConfig()
        self._policy_provider = policy_provider
        self.timeout_s = per_detector_timeout_s
        self.strategy = strategy
        self.cache = cache
        self._cc = circuit_config or {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self.max_input_chars = max_input_chars
        self.allow_external_egress = allow_external_egress
        # Recent INPUT evaluations for policy what-if simulation. Stores signals +
        # context only (no prompt text at all) — see evaluate().
        self._records: deque[tuple[str, list[Signal], Context]] = deque(maxlen=sim_buffer_size)

    @property
    def policy(self) -> PolicyConfig:
        return self._policy_provider() if self._policy_provider else self._policy

    # --- helpers ----------------------------------------------------------
    def _breaker(self, detector_id: str) -> CircuitBreaker:
        b = self._breakers.get(detector_id)
        if b is None:
            b = CircuitBreaker(
                failure_threshold=self._cc.get("failure_threshold", 5),
                reset_timeout_s=self._cc.get("reset_timeout_s", 30.0),
            )
            self._breakers[detector_id] = b
        return b

    @staticmethod
    def _validate_signal(sig, det, entry):
        """Contain a buggy/hostile plugin's output at the boundary.

        A structurally-broken Signal (wrong type, non-numeric score, bad action)
        can't be trusted to make a decision -> treat as a detector error
        (fail-mode). A structurally-valid but out-of-bounds Signal is clamped/
        capped so a plugin can't inject an absurd score or exhaust memory.
        """
        if (
            not isinstance(sig, Signal)
            or not isinstance(sig.action_hint, Action)
            or not isinstance(sig.score, (int, float))
        ):
            return GuardrailService._fail_signal(det, "invalid-signal", entry), False
        sig.score = max(0.0, min(1.0, float(sig.score)))
        if len(sig.spans) > MAX_SPANS_PER_SIGNAL:
            sig.spans = sig.spans[:MAX_SPANS_PER_SIGNAL]
        if len(sig.labels) > MAX_LABELS_PER_SIGNAL:
            sig.labels = sig.labels[:MAX_LABELS_PER_SIGNAL]
        if sig.transformed_text and len(sig.transformed_text) > MAX_TRANSFORMED_CHARS:
            sig.transformed_text = sig.transformed_text[:MAX_TRANSFORMED_CHARS]
        return sig, True

    @staticmethod
    def _fail_signal(det, reason: str, entry) -> Signal:
        failed_closed = det.fail_mode == FailMode.CLOSED
        return Signal(
            detector_id=det.id,
            check=det.check,
            score=1.0 if failed_closed else 0.0,
            action_hint=Action.BLOCK if failed_closed else Action.ALLOW,
            labels=["detector-error"],
            error=reason,
            mode=entry.mode,
            meta={"weight": entry.weight},
        )

    async def _run_one(self, entry, text: str, ctx: Context) -> Signal:
        det = entry.detector
        breaker = self._breaker(det.id)

        if not breaker.allow():  # circuit OPEN -> short-circuit to fail-mode
            return self._fail_signal(det, "circuit-open", entry)

        cacheable = getattr(det, "cacheable", False)
        version = getattr(det, "version", None)
        if cacheable and self.cache is not None:
            cached = self.cache.get(det.id, version, ctx.tenant, text)
            if cached is not None:
                cached.mode = entry.mode
                cached.meta.setdefault("weight", entry.weight)
                return cached

        t0 = time.perf_counter()
        try:
            sig = await asyncio.wait_for(det.analyze(text, ctx), timeout=self.timeout_s)
            breaker.record_success()
        except Exception as exc:
            breaker.record_failure()
            entry.error_count += 1
            return self._fail_signal(det, f"{type(exc).__name__}: {exc}", entry)

        # Validate/sanitize the plugin's output at the boundary before trusting it.
        sig, ok = self._validate_signal(sig, det, entry)
        if not ok:
            entry.error_count += 1
            return sig  # fail-mode signal; do NOT cache an invalid result

        latency = (time.perf_counter() - t0) * 1000
        entry.last_latency_ms = latency
        if sig.latency_ms is None:
            sig.latency_ms = latency
        sig.mode = entry.mode
        sig.meta.setdefault("weight", entry.weight)

        if cacheable and self.cache is not None:
            self.cache.put(det.id, version, ctx.tenant, text, sig)
        return sig

    # --- evaluation -------------------------------------------------------
    async def evaluate(self, text: str, ctx: Context) -> Verdict:
        entries = self.registry.for_stage(ctx.stage)
        # Data-residency: drop detectors that would send data off-box when the
        # policy forbids external egress.
        if not self.allow_external_egress:
            entries = [e for e in entries if getattr(e.detector, "egress", "internal") != "external"]
        # Resource guard: bound the text every detector processes (ML/regex work).
        text = (text or "")[: self.max_input_chars]
        # Normalize INPUT ONCE at the boundary so every detector (and the span
        # merge in the policy) works in a single coordinate system — otherwise
        # per-detector normalization would shift offsets and break span merging.
        eval_text = normalize_for_analysis(text) if ctx.stage == Stage.INPUT else text
        if not entries:
            return Verdict(action=Action.ALLOW, reason="no detectors", text=eval_text, stage=ctx.stage)
        policy = self.policy
        if self.strategy == "cascade":
            verdict, signals = await self._eval_cascade(entries, eval_text, ctx, policy)
        else:
            verdict, signals = await self._eval_parallel(entries, eval_text, ctx, policy)
        # Record INPUT evaluations for what-if simulation. We store NO prompt text
        # (simulation compares actions, which depend only on signals + ctx + cfg),
        # so no prompt content — detected PII or not — is ever kept at rest.
        if ctx.stage == Stage.INPUT:
            self._records.append(("", signals, ctx))
        return verdict

    async def _eval_parallel(self, entries, text, ctx, policy):
        signals = list(await asyncio.gather(*(self._run_one(e, text, ctx) for e in entries)))
        signals.sort(key=lambda s: s.detector_id)
        return decide(text, aggregate(signals), ctx, policy), signals

    async def _eval_cascade(self, entries, text, ctx, policy):
        ordered = sorted(entries, key=lambda e: getattr(e.detector, "cost", 5))
        collected: list[Signal] = []
        for e in ordered:
            collected.append(await self._run_one(e, text, ctx))
            ordered_sigs = sorted(collected, key=lambda s: s.detector_id)
            interim = decide(text, aggregate(ordered_sigs), ctx, policy)
            if interim.action == Action.BLOCK:
                return interim, ordered_sigs
        ordered_sigs = sorted(collected, key=lambda s: s.detector_id)
        return decide(text, aggregate(ordered_sigs), ctx, policy), ordered_sigs

    # --- what-if simulation ----------------------------------------------
    def recent_records(self) -> list[tuple[str, list[Signal], Context]]:
        return list(self._records)

    # --- health (surfaced by the control-plane API) ----------------------
    def circuit_state(self, detector_id: str) -> str | None:
        b = self._breakers.get(detector_id)
        return b.state.value if b else None

    def health(self) -> dict:
        return {
            "strategy": self.strategy,
            "circuits": {did: b.state.value for did, b in self._breakers.items()},
            "circuit_trips": {did: b.trips for did, b in self._breakers.items()},
            "cache": self.cache.stats if self.cache else None,
            "sim_buffer": len(self._records),
        }
