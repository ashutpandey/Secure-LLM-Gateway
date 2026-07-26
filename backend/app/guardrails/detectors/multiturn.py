"""LLM01 (multi-turn) — session-level escalation detector.

The differentiator: a gradual jailbreak spreads mild probes across turns that
each pass single-message checks. This detector reads the conversation's recent
probe history (via Context.session_history, populated by the gateway) and
escalates when the SESSION shows accumulated injection intent — so the aggregate
LLM01 score can cross the block threshold even when the current turn alone is mild.

Reads only text + Context (narrow capability); the cross-turn state is provided
by SessionMemory through the gateway. Not cacheable (depends on session, not just
text). Ships `shadow` by default — enable to enforce.
"""

from __future__ import annotations

from ..base import Action, Context, FailMode, Signal, Stage
from ..registry import register_detector

_PROBE_THRESHOLD = 0.3  # a turn counts as a "probe" at/above this injection score
_SUSPICIOUS_LABELS = {
    "override",
    "override:previous",
    "override:ignore-previous",
    "role:from-now-on",
    "role:you-are-now-admin",
    "roleplay",
    "exfil",
    "jailbreak",
    "unrestricted",
}


def _is_probe(turn: dict) -> bool:
    if turn.get("score", 0.0) >= _PROBE_THRESHOLD:
        return True
    return any(lbl in _SUSPICIOUS_LABELS for lbl in turn.get("labels", []))


@register_detector
class MultiTurnDetector:
    id = "multiturn"
    stage = Stage.INPUT
    check = "LLM01"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    model_id = "session-escalation"
    version = "1.0.0"
    cost = 0  # cheap: reads a short history
    cacheable = False  # depends on session_history, not just the text
    egress = "internal"

    async def analyze(self, text: str, ctx: Context) -> Signal:
        probes = sum(1 for turn in ctx.session_history if _is_probe(turn))
        if probes < 2:
            return Signal(detector_id=self.id, check=self.check, score=0.0, action_hint=Action.ALLOW)
        # Escalate with the number of prior probes: 2 -> 0.6, 3 -> 0.9 (block).
        score = min(0.9, 0.3 * probes)
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=round(score, 3),
            action_hint=Action.ALLOW,  # policy decides from the aggregated score
            labels=["multi-turn-escalation", f"probes:{probes}"],
            model_id=self.model_id,
            version=self.version,
        )
