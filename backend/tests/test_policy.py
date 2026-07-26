"""Cycle 3 tests: aggregation, context-aware policy, simulation, trust tracker."""

from __future__ import annotations

import pytest

from app.core.conversations import ConversationTracker
from app.guardrails import (
    Action,
    Context,
    Mode,
    PolicyConfig,
    Signal,
    Stage,
    aggregate,
    decide,
    simulate,
)


def sig(check, score, action=Action.ALLOW, mode=Mode.ENFORCE, weight=1.0):
    return Signal(
        detector_id=f"{check}-{score}-{mode.value}",
        check=check,
        score=score,
        action_hint=action,
        mode=mode,
        meta={"weight": weight},
    )


def _verdict(score, trust, role="user", cfg=None):
    ctx = Context(stage=Stage.INPUT, conversation_trust=trust, user_role=role)
    return decide("prompt", aggregate([sig("LLM01", score)]), ctx, cfg or PolicyConfig())


# --- aggregator -------------------------------------------------------------
def test_aggregate_combines_two_signals():
    agg = aggregate([sig("LLM01", 0.4), sig("LLM01", 0.9)])
    # 1 - (1-0.4)*(1-0.9) = 0.94
    assert agg.by_check["LLM01"].score == pytest.approx(0.94, abs=0.01)
    assert len(agg.by_check["LLM01"].contributors) == 2


def test_shadow_signals_excluded_from_decision():
    agg = aggregate([sig("LLM01", 0.99, action=Action.BLOCK, mode=Mode.SHADOW)])
    assert "LLM01" not in agg.by_check  # shadow doesn't enter enforced groups
    assert len(agg.shadow) == 1
    verdict = decide("p", agg, Context(stage=Stage.INPUT), PolicyConfig())
    assert verdict.action == Action.ALLOW  # observed, not enforced
    assert "_shadow" in verdict.breakdown  # but still attributed


# --- context-aware policy ---------------------------------------------------
def test_low_trust_tightens_threshold():
    # Same score, different trust -> different decision.
    assert _verdict(0.75, trust=1.0).action == Action.SANITIZE
    assert _verdict(0.75, trust=0.0).action == Action.BLOCK


def test_admin_role_relaxes_threshold():
    assert _verdict(0.9, trust=1.0, role="user").action == Action.BLOCK
    assert _verdict(0.9, trust=1.0, role="admin").action == Action.SANITIZE


def test_breakdown_is_attributed():
    v = _verdict(0.9, trust=1.0)
    assert "LLM01" in v.breakdown
    assert v.breakdown["LLM01"]["action"] == "BLOCK"
    assert v.breakdown["LLM01"]["contributors"]


# --- simulation (what-if) ---------------------------------------------------
def test_simulate_reports_action_changes():
    records = [("prompt", [sig("LLM01", 0.75)], Context(stage=Stage.INPUT, conversation_trust=1.0))]
    lenient = PolicyConfig()  # block at 0.85 -> 0.75 not blocked
    strict = PolicyConfig(block_thresholds={"LLM01": 0.70})  # 0.75 -> blocked
    before = simulate(records, lenient)
    after = simulate(records, strict)
    assert before[0].action != Action.BLOCK
    assert after[0].action == Action.BLOCK


# --- conversation trust tracker --------------------------------------------
def test_trust_decays_on_block_and_recovers_on_clean():
    t = ConversationTracker()
    t.begin_turn("c1")
    start = t.snapshot("c1").trust
    t.record("c1", "block")
    after_block = t.snapshot("c1").trust
    assert after_block < start
    t.record("c1", "clean")
    assert t.snapshot("c1").trust > after_block


def test_config_roundtrip():
    cfg = PolicyConfig(block_thresholds={"LLM01": 0.7}, trust_sensitivity=0.3)
    restored = PolicyConfig.from_dict(cfg.to_dict())
    assert restored.block_thresholds["LLM01"] == 0.7
    assert restored.trust_sensitivity == 0.3
