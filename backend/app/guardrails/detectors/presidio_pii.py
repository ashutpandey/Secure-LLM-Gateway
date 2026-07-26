"""LLM06 — ML PII detector (calls the sidecar's /scan/pii).

Adds NER-based PII (emails, phones, names, …) that the structured regex detector
(cards/SSNs/keys) can't reach. It emits SPANS; the aggregator merges spans across
ALL enforced PII detectors and applies them together, so regex + Presidio compose
without either dropping the other's redactions.

fail-OPEN like PromptGuard — a sidecar outage degrades to the regex baseline.
"""

from __future__ import annotations

import time

from ..base import Action, Context, FailMode, Signal, Span, Stage
from ..registry import register_detector
from .sidecar import scan_pii

_PLACEHOLDER = "[REDACTED]"


@register_detector
class PresidioDetector:
    id = "presidio-pii"
    stage = Stage.INPUT
    check = "LLM06"
    fail_mode = FailMode.OPEN
    contract_version = 1
    model_id = "sidecar:presidio"
    version = "1.0.0"
    cost = 10
    cacheable = True

    async def analyze(self, text: str, ctx: Context) -> Signal:
        t0 = time.perf_counter()
        res = await scan_pii(text)
        entities = res.get("entities", [])

        spans: list[Span] = []
        for e in entities:
            try:
                start, end = int(e["start"]), int(e["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= start < end <= len(text):
                spans.append(Span(start=start, end=end, label=e.get("type", "PII"), replacement=_PLACEHOLDER))

        # Standalone transform (fallback when this is the only redactor); the
        # aggregator prefers merged spans when multiple redactors are present.
        transformed = None
        if spans:
            transformed = text
            for sp in sorted(spans, key=lambda s: s.start, reverse=True):
                transformed = transformed[: sp.start] + _PLACEHOLDER + transformed[sp.end :]

        hit = len(spans) > 0
        top = max((float(e.get("score", 0.0)) for e in entities), default=0.0)
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=top,
            action_hint=Action.REDACT if hit else Action.ALLOW,
            labels=[e.get("type", "PII") for e in entities],
            spans=spans,
            transformed_text=transformed,
            model_id=res.get("model_id", self.model_id),
            version=res.get("version", self.version),
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
