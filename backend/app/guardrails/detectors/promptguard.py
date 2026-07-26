"""LLM01 — ML injection detector (calls the sidecar's /score/injection).

The headline of the plugin architecture: this detector adds ML-based injection
scoring alongside the regex fast-path WITHOUT any change to the gateway, policy,
or aggregator. Run it in `shadow` to observe it next to regex, then flip it to
`enforce` — same pipeline, different brain.

fail-OPEN: if the sidecar is unreachable, this degrades to a benign signal so the
regex detector remains the enforced baseline (availability over a hard block for
an enrichment model). It emits a SCORE; the policy engine decides the action from
the aggregated LLM01 score, exactly like the regex detector.
"""

from __future__ import annotations

import time

from ..base import Action, Context, FailMode, Signal, Stage
from ..registry import register_detector
from .sidecar import score_injection


@register_detector
class PromptGuardDetector:
    id = "promptguard"
    stage = Stage.INPUT
    check = "LLM01"
    fail_mode = FailMode.OPEN  # sidecar outage must not block chat
    contract_version = 1
    model_id = "sidecar:promptguard"
    version = "1.0.0"
    cost = 10  # expensive relative to regex — cascade runs it last
    cacheable = True  # deterministic for the process's fixed model

    async def analyze(self, text: str, ctx: Context) -> Signal:
        t0 = time.perf_counter()
        res = await score_injection(text)
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=float(res.get("score", 0.0)),
            action_hint=Action.ALLOW,  # policy decides from the aggregated score
            labels=list(res.get("labels", [])),
            model_id=res.get("model_id", self.model_id),
            version=res.get("version", self.version),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
