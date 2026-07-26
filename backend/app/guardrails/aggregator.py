"""Signal Aggregator — turns raw detector signals into a per-check summary.

This is the step BETWEEN detection and decision (your architecture note #2):
detectors only score; the aggregator combines multiple signals of the same check
(e.g. regex + Prompt-Guard both scoring LLM01) into one weighted score with
attribution; the policy engine then decides purely from this summary.

Keeping this separate means adding a second LLM01 detector in Cycle 6 changes
NOTHING in the policy engine — the aggregator folds it into the LLM01 score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Action, Mode, Signal

# Action precedence for picking the strongest hint among contributors.
_RANK = {Action.ALLOW: 0, Action.SANITIZE: 1, Action.REDACT: 1, Action.BLOCK: 2}


@dataclass(slots=True)
class CheckAggregate:
    check: str
    score: float  # weighted-combined score across enforced contributors
    action_hint: Action  # strongest enforced hint for this check
    contributors: list[Signal] = field(default_factory=list)  # enforced only
    transformed_text: str | None = None  # chosen transform (REDACT preferred)


@dataclass(slots=True)
class Aggregation:
    by_check: dict[str, CheckAggregate]  # enforced, grouped by check
    all_signals: list[Signal]  # everything, incl shadow (attribution)
    shadow: list[Signal]  # shadow-only, for side-by-side comparison


def _weight_of(sig: Signal) -> float:
    w = sig.meta.get("weight", 1.0)
    try:
        return float(w)
    except (TypeError, ValueError):
        return 1.0


def _combine(pairs: list[tuple[float, float]]) -> float:
    """Diminishing-returns combine of (weight, score) pairs: 1 - Π(1 - w*s).

    Two detectors agreeing pushes the score up without any single one dominating;
    a lone weak signal stays weak. Weights let the control plane tune influence.
    """
    acc = 1.0
    for w, s in pairs:
        acc *= 1 - min(1.0, max(0.0, w * s))
    return round(1 - acc, 4)


def aggregate(signals: list[Signal]) -> Aggregation:
    enforced = [s for s in signals if s.mode == Mode.ENFORCE]
    shadow = [s for s in signals if s.mode == Mode.SHADOW]

    groups: dict[str, list[Signal]] = {}
    for s in enforced:
        groups.setdefault(s.check, []).append(s)

    by_check: dict[str, CheckAggregate] = {}
    for check, sigs in groups.items():
        score = _combine([(_weight_of(s), s.score) for s in sigs])
        # Strongest enforced hint wins.
        hint = max((s.action_hint for s in sigs), key=lambda a: _RANK[a])
        # Prefer a REDACT transform (PII must never leak), else SANITIZE.
        redact = next((s for s in sigs if s.action_hint == Action.REDACT and s.transformed_text is not None), None)
        san = next((s for s in sigs if s.transformed_text is not None), None)
        transform = (redact or san).transformed_text if (redact or san) else None
        by_check[check] = CheckAggregate(
            check=check,
            score=score,
            action_hint=hint,
            contributors=sigs,
            transformed_text=transform,
        )

    return Aggregation(by_check=by_check, all_signals=list(signals), shadow=shadow)
