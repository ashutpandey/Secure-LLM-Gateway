"""LLM06 — PII / secret detector (structured, validated).

Port of the frontend `piiScanner.js`: Luhn-validated cards, structural SSNs,
prefix-anchored API keys, and a context-gated fuzzy secret pass, each with a
confidence score and a floor for validated hits. In the target architecture this
is the fast/offline detector; Presidio (NER) is added as a second detector for
names/addresses/emails regex can't reach.
"""

from __future__ import annotations

import re
import time

from ..base import Action, Context, FailMode, Signal, Span, Stage
from ..normalize import normalize_for_analysis
from ..registry import register_detector

_THRESHOLD = 0.5
_CTX_RADIUS = 40
_PLACEHOLDER = "[REDACTED]"

_CC_CANDIDATE = re.compile(r"\b(?:\d[ .-]?){13,19}\b")
_SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_SECRETS = [
    re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
]
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_-]{24,}\b")

_BOOSTERS = [
    (re.compile(r"\b(card|credit|debit|cvv|cvc|visa|mastercard|amex)\b", re.I), 0.4, {"CREDIT_CARD"}),
    (re.compile(r"\b(ssn|social\s+security|taxpayer)\b", re.I), 0.4, {"US_SSN"}),
    (re.compile(r"\b(api[_\s-]?key|secret|token|password|passwd|bearer|auth|credential)\b", re.I), 0.5, {"API_KEY", "SECRET_TOKEN"}),
]
_DAMPENERS = [
    (re.compile(r"\b(example|sample|test|fake|dummy|placeholder|mock)\b", re.I), 0.4),
    (re.compile(r"\b(order|invoice|tracking|reference|ticket|case|sku)\b", re.I), 0.5),
]


def _luhn_valid(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return len(digits) >= 13 and total % 10 == 0


def _ctx_around(text: str, index: int, length: int) -> str:
    return text[max(0, index - _CTX_RADIUS): index + length + _CTX_RADIUS]


def _confidence(kind: str, base: float, ctx: str) -> float:
    acc = 1 - base
    for pat, w, applies in _BOOSTERS:
        if kind in applies and pat.search(ctx):
            acc *= 1 - w
    score = 1 - acc
    for pat, f in _DAMPENERS:
        if pat.search(ctx):
            score *= f
    return max(0.0, min(1.0, score))


def _mask(s: str) -> str:
    digits = re.sub(r"\D", "", s)
    return "•••• " + digits[-4:]


@register_detector
class PIIScanner:
    id = "regex-pii"
    stage = Stage.INPUT
    check = "LLM06"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    model_id = "regex+luhn"
    version = "1.1.0"
    cost = 1
    cacheable = True

    async def analyze(self, text: str, ctx: Context) -> Signal:
        t0 = time.perf_counter()
        text = normalize_for_analysis(text)
        redactions: list[dict] = []
        spans: list[Span] = []

        # We rebuild the redacted string via a running cursor so spans map to the
        # ORIGINAL text while the replacement collapses hits to the placeholder.
        out_parts: list[str] = []
        cursor = 0

        # Merge all validated + fuzzy matches into one ordered pass.
        events: list[tuple[int, int, str, float, float]] = []  # start,end,type,base,floor

        for m in _CC_CANDIDATE.finditer(text):
            digits = re.sub(r"[ .-]", "", m.group())
            if _luhn_valid(digits):
                events.append((m.start(), m.end(), "CREDIT_CARD", 0.75, 0.6))
        for m in _SSN.finditer(text):
            events.append((m.start(), m.end(), "US_SSN", 0.7, 0.6))
        for pat in _SECRETS:
            for m in pat.finditer(text):
                events.append((m.start(), m.end(), "API_KEY", 0.9, 0.7))

        # Fuzzy pass: only where not already covered and context promotes it.
        covered = [(s, e) for s, e, *_ in events]

        def _overlaps(s: int, e: int) -> bool:
            return any(s < ce and e > cs for cs, ce in covered)

        for m in _LONG_TOKEN.finditer(text):
            s, e = m.start(), m.end()
            if _overlaps(s, e):
                continue
            tok = m.group()
            looks_secret = any(c.isupper() for c in tok) and any(c.islower() for c in tok) and any(c.isdigit() for c in tok)
            if not looks_secret:
                continue
            raw = _confidence("SECRET_TOKEN", 0.25, _ctx_around(text, s, len(tok)))
            if raw >= _THRESHOLD:
                # store the BASE (0.25), not the computed confidence — the main
                # loop recomputes uniformly from base, so storing raw would apply
                # the context boost twice.
                events.append((s, e, "SECRET_TOKEN", 0.25, 0.0))

        events.sort(key=lambda ev: ev[0])
        for s, e, kind, base, floor in events:
            if s < cursor:  # overlap guard after sort
                continue
            conf = _confidence(kind, base, _ctx_around(text, s, e - s))
            conf = round(max(conf, floor), 3)
            if conf < _THRESHOLD:
                continue
            out_parts.append(text[cursor:s])
            out_parts.append(_PLACEHOLDER)
            cursor = e
            redactions.append({"type": kind, "confidence": conf, "sample": _mask(text[s:e])})
            spans.append(Span(start=s, end=e, label=kind, replacement=_PLACEHOLDER))
        out_parts.append(text[cursor:])
        redacted = "".join(out_parts)

        hit = len(redactions) > 0
        top = max((r["confidence"] for r in redactions), default=0.0)
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=top,
            action_hint=Action.REDACT if hit else Action.ALLOW,
            labels=[r["type"] for r in redactions],
            spans=spans,
            transformed_text=redacted if hit else None,
            model_id=self.model_id,
            version=self.version,
            latency_ms=(time.perf_counter() - t0) * 1000,
            meta={"redactions": redactions},
        )
