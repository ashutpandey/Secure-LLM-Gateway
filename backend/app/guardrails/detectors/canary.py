"""LLM01 (defense-in-depth) — egress canary / honeytoken.

Port of the frontend `canary.js`. The gateway seeds a unique marker into the
model's system context per request; if it reappears in the OUTPUT stream, the
system prompt leaked and we withhold the response (fail closed). This runs as an
EGRESS-stage detector on accumulated output.
"""

from __future__ import annotations

import secrets

from ..base import Action, Context, FailMode, Signal, Stage
from ..registry import register_detector

_PREFIX = "CANARY"


def new_canary() -> str:
    # 96 bits: a tripwire, not a cryptographic secret (worst case = missed
    # detection, never a bypass of another control). secrets is used anyway.
    return f"{_PREFIX}-{secrets.token_hex(6)}{secrets.token_hex(6)}"


@register_detector
class CanaryEgress:
    id = "egress-canary"
    stage = Stage.EGRESS
    check = "LLM01"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    model_id = "canary"
    version = "1.0.0"
    cost = 0
    cacheable = False  # depends on the per-request canary in ctx, not just text

    async def analyze(self, text: str, ctx: Context) -> Signal:
        canary = ctx.canary or ""
        leaked = bool(canary) and canary in (text or "")
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=1.0 if leaked else 0.0,
            action_hint=Action.BLOCK if leaked else Action.ALLOW,
            labels=["system-prompt-leak"] if leaked else [],
            model_id=self.model_id,
            version=self.version,
        )
