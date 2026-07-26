"""Cycle 8 tests: plugin blast-radius containment.

contract-version rejection, malformed-Signal containment, egress gating,
input-size cap.
"""

from __future__ import annotations

import pytest

from app.guardrails import (
    Action,
    Context,
    DetectorRegistry,
    FailMode,
    GuardrailService,
    Mode,
    PolicyConfig,
    Signal,
    Stage,
    register_detector,
)
from app.guardrails.service import GuardrailService as GS

INPUT = Context(stage=Stage.INPUT)


class _D:
    stage = Stage.INPUT
    check = "LLM01"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    version = "1"
    cost = 1
    cacheable = False


def _svc(detectors, **kw):
    reg = DetectorRegistry()
    for d in detectors:
        reg.register(d)
    return GuardrailService(reg, PolicyConfig(), **kw)


# --- contract versioning ----------------------------------------------------
def test_register_rejects_incompatible_contract_version():
    class Bad:
        id = "bad"
        stage = Stage.INPUT
        check = "LLM01"
        fail_mode = FailMode.CLOSED
        contract_version = 99

        async def analyze(self, text, ctx):
            return None

    with pytest.raises(TypeError):
        register_detector(Bad)


# --- Signal validation (blast radius) --------------------------------------
def test_validate_rejects_non_signal_fails_closed():
    class _Det:
        id = "x"
        check = "LLM01"
        fail_mode = FailMode.CLOSED

    class _Entry:
        mode = Mode.ENFORCE
        weight = 1.0

    sig, ok = GS._validate_signal({"not": "a signal"}, _Det(), _Entry())
    assert ok is False
    assert sig.action_hint == Action.BLOCK  # fail-closed, not trusted


def test_validate_clamps_out_of_range_score():
    class _Det:
        id = "x"
        check = "LLM01"
        fail_mode = FailMode.CLOSED

    class _Entry:
        mode = Mode.ENFORCE
        weight = 1.0

    good = Signal(detector_id="x", check="LLM01", score=5.0, action_hint=Action.ALLOW)
    sig, ok = GS._validate_signal(good, _Det(), _Entry())
    assert ok and sig.score == 1.0


async def test_malformed_plugin_output_is_contained():
    class Rogue(_D):
        id = "rogue"

        async def analyze(self, text, ctx):
            return "totally not a Signal"  # hostile/buggy output

    v = await _svc([Rogue()]).evaluate("hello", INPUT)
    # Contained: treated as a fail-closed error, never crashes or is trusted.
    assert v.action == Action.BLOCK


# --- egress capability gating ----------------------------------------------
class _ExternalBlocker(_D):
    id = "ext"
    egress = "external"

    async def analyze(self, text, ctx):
        return Signal(detector_id=self.id, check="LLM01", score=0.99, action_hint=Action.BLOCK)


async def test_external_egress_skipped_when_forbidden():
    v = await _svc([_ExternalBlocker()], allow_external_egress=False).evaluate("hi", INPUT)
    assert v.action == Action.ALLOW  # external detector not run (data residency)


async def test_external_egress_runs_when_allowed():
    v = await _svc([_ExternalBlocker()], allow_external_egress=True).evaluate("hi", INPUT)
    assert v.action == Action.BLOCK


# --- input size cap ---------------------------------------------------------
async def test_input_is_capped():
    class LenCapture(_D):
        id = "len"

        def __init__(self):
            self.received = None

        async def analyze(self, text, ctx):
            self.received = len(text)
            return Signal(detector_id=self.id, check="LLM01", score=0.0, action_hint=Action.ALLOW)

    d = LenCapture()
    await _svc([d], max_input_chars=10).evaluate("x" * 500, INPUT)
    assert d.received is not None and d.received <= 10
