"""LLM01 — regex prompt-injection detector (fast-path).

Faithful port of the frontend `promptInjection.js`. In the target architecture
this is the CHEAP, high-precision first pass and offline fallback — an ML
detector (Prompt-Guard) runs alongside it. It is NOT meant to be the whole
defense; see ARCHITECTURE.md "KNOWN LIMITS".
"""

from __future__ import annotations

import re
import time

from ..base import Action, Context, FailMode, Signal, Span, Stage
from ..normalize import normalize_for_analysis
from ..registry import register_detector

HIGH, MED = 0.85, 0.55

# (pattern, weight, label)
_SIGNALS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|context|directives)", re.I), 0.8, "override:ignore-previous"),
    (re.compile(r"disregard\s+(the\s+)?(above|previous|prior|earlier)", re.I), 0.6, "override:disregard-above"),
    (re.compile(r"forget\s+(everything|all|your\s+(instructions|rules))", re.I), 0.6, "override:forget"),
    (re.compile(r"you\s+are\s+now\s+(an?\s+)?(admin|administrator|root|dan|developer\s+mode)", re.I), 0.8, "role:you-are-now-admin"),
    (re.compile(r"(enable|activate|enter)\s+(developer|god|dan|jailbreak)\s+mode", re.I), 0.7, "role:jailbreak-mode"),
    (re.compile(r"act\s+as\s+(an?\s+)?(admin|root|system|unfiltered)", re.I), 0.6, "role:act-as"),
    (re.compile(r"\b(new|updated)\s+(system\s+)?(prompt|instructions|rules)\s*[:=]", re.I), 0.6, "override:new-system-prompt"),
    (re.compile(r"pretend\s+(to\s+be|you\s+are)\b", re.I), 0.4, "role:pretend"),
    (re.compile(r"from\s+now\s+on\b[\s\S]{0,60}\b(no\s+restrictions|as\s+(an?\s+)?(root|admin|administrator|superuser|dan)|without\s+(any\s+)?(rules|restrictions|filters))", re.I), 0.6, "role:from-now-on"),
    (re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions|hidden\s+rules)", re.I), 0.6, "exfil:reveal-system-prompt"),
    (re.compile(r"\b(evade|evading|bypass|bypassing|circumvent|circumventing|defeat|disable|turn\s+off)\b.*\b(detection|safety|safeguards?|filters?|restrictions?|authentication|security|policy|protections?)\b", re.I), 0.6, "policy:bypass-safety"),
    (re.compile(r"\b(phish|phishing|malware|credential\s+theft|steal\s+credentials|steal\s+cookies|hack|unauthorized|exploit)\b", re.I), 0.6, "policy:malicious-request"),
    (re.compile(r"<\|?(im_start|im_end|endoftext|system|assistant|user)\|?>", re.I), 0.7, "delimiter:chat-template"),
    (re.compile(r"\[\/?(INST|SYS)\]", re.I), 0.6, "delimiter:inst-block"),
    (re.compile(r"^\s*#{2,3}\s*system\b", re.I | re.M), 0.5, "delimiter:markdown-system-header"),
    (re.compile(r"\b(system|assistant)\s*:\s*$", re.I | re.M), 0.35, "delimiter:role-label"),
]

# (pattern, factor, label) — lower the score when the phrase is discussed, not used
_DAMPENERS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"```[\s\S]*```"), 0.4, "in-code-fence"),
    (re.compile(r"([\"'“”]).{0,120}\1"), 0.6, "quoted"),
    (re.compile(r"\b(what\s+does|what\s+is|explain|meaning\s+of|example\s+of|define)\b", re.I), 0.55, "explanatory"),
    (re.compile(r"\?\s*$"), 0.75, "phrased-as-question"),
]


def _combine(weights: list[float]) -> float:
    acc = 1.0
    for w in weights:
        acc *= 1 - w
    return 1 - acc


@register_detector
class RegexInjection:
    id = "regex-injection"
    stage = Stage.INPUT
    check = "LLM01"
    fail_mode = FailMode.CLOSED  # if this cheap check errors, don't silently allow
    contract_version = 1
    model_id = "regex-signals"
    version = "1.1.0"
    cost = 1  # cheap: pure regex. Cascade runs low-cost detectors first.
    cacheable = True  # deterministic for a given input

    async def analyze(self, text: str, ctx: Context) -> Signal:
        t0 = time.perf_counter()
        text = normalize_for_analysis(text)

        matched: list[dict] = []
        weights: list[float] = []
        for pat, weight, label in _SIGNALS:
            if pat.search(text):
                matched.append({"label": label, "weight": weight})
                weights.append(weight)

        score = _combine(weights)
        dampeners: list[str] = []
        if score > 0:
            for pat, factor, label in _DAMPENERS:
                if pat.search(text):
                    score *= factor
                    dampeners.append(label)
        score = max(0.0, min(1.0, score))

        if score >= HIGH:
            action = Action.BLOCK
        elif score >= MED:
            action = Action.SANITIZE
        else:
            action = Action.ALLOW

        transformed = None
        spans: list[Span] = []
        if action == Action.SANITIZE:
            # Emit spans (for the aggregator's cross-detector merge) AND a
            # standalone transformed_text (fallback when this is the sole rewriter).
            for pat, _w, label in _SIGNALS:
                for m in pat.finditer(text):
                    spans.append(Span(start=m.start(), end=m.end(), label=label, replacement="[removed-directive]"))
            transformed = text
            for pat, _w, _l in _SIGNALS:
                transformed = pat.sub("[removed-directive]", transformed)

        return Signal(
            detector_id=self.id,
            check=self.check,
            score=round(score, 3),
            action_hint=action,
            labels=[m["label"] for m in matched],
            spans=spans,
            transformed_text=transformed,
            model_id=self.model_id,
            version=self.version,
            latency_ms=(time.perf_counter() - t0) * 1000,
            meta={"dampeners": dampeners},
        )
