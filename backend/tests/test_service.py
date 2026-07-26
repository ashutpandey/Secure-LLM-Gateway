"""Guardrail Service hardening tests (Cycle 2): circuit breaker, cache, cascade.

Uses isolated fake detectors + a fresh DetectorRegistry so we exercise the
service machinery without touching the real detectors or the global registry.
"""

from __future__ import annotations

from app.guardrails import (
    Action,
    Context,
    DetectorRegistry,
    FailMode,
    GuardrailService,
    PolicyConfig,
    Signal,
    SignalCache,
    Stage,
)

INPUT = Context(stage=Stage.INPUT)


class _Base:
    stage = Stage.INPUT
    check = "LLM01"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    version = "1"
    cost = 1
    cacheable = False

    def __init__(self):
        self.calls = 0


class Flaky(_Base):
    id = "flaky"
    fail_mode = FailMode.OPEN  # failure -> benign, so it doesn't itself block

    async def analyze(self, text, ctx):
        self.calls += 1
        raise RuntimeError("boom")


class Counting(_Base):
    id = "count"
    cacheable = True

    async def analyze(self, text, ctx):
        self.calls += 1
        return Signal(detector_id=self.id, check=self.check, score=0.0, action_hint=Action.ALLOW)


class CheapBlocker(_Base):
    id = "cheap-block"
    cost = 0

    async def analyze(self, text, ctx):
        self.calls += 1
        return Signal(detector_id=self.id, check="LLM01", score=0.99, action_hint=Action.BLOCK)


class Expensive(_Base):
    id = "expensive"
    cost = 10

    async def analyze(self, text, ctx):
        self.calls += 1
        return Signal(detector_id=self.id, check="LLM01", score=0.0, action_hint=Action.ALLOW)


def _svc(detectors, **kw):
    reg = DetectorRegistry()
    for d in detectors:
        reg.register(d)
    return GuardrailService(reg, PolicyConfig(), **kw)


async def test_circuit_breaker_opens_and_short_circuits():
    flaky = Flaky()
    svc = _svc([flaky], circuit_config={"failure_threshold": 3, "reset_timeout_s": 100})
    for _ in range(5):
        await svc.evaluate("hello", INPUT)
    # 3 failures trip the breaker; calls 4 and 5 short-circuit without invoking it.
    assert flaky.calls == 3
    assert svc.circuit_state("flaky") == "open"


async def test_fail_closed_error_blocks():
    class Boom(_Base):
        id = "boom"

        async def analyze(self, text, ctx):
            raise RuntimeError("down")

    svc = _svc([Boom()])
    verdict = await svc.evaluate("hello", INPUT)
    assert verdict.action == Action.BLOCK  # CLOSED detector fails safe


async def test_signal_cache_hit():
    counting = Counting()
    cache = SignalCache()
    svc = _svc([counting], cache=cache)
    await svc.evaluate("same input", INPUT)
    await svc.evaluate("same input", INPUT)
    assert counting.calls == 1  # second served from cache
    assert cache.hits == 1


async def test_cascade_short_circuits_expensive():
    cheap, expensive = CheapBlocker(), Expensive()
    svc = _svc([expensive, cheap], strategy="cascade")
    verdict = await svc.evaluate("hello", INPUT)
    assert verdict.action == Action.BLOCK
    assert cheap.calls == 1
    assert expensive.calls == 0  # never reached — cheap block short-circuited


async def test_parallel_runs_all():
    cheap, expensive = CheapBlocker(), Expensive()
    svc = _svc([expensive, cheap], strategy="parallel")
    await svc.evaluate("hello", INPUT)
    assert cheap.calls == 1 and expensive.calls == 1  # full attribution
