"""The Policy Engine — a PURE FUNCTION: (aggregation, context, config) -> Verdict.

No I/O, no globals. Purity is what makes it (a) trivially testable, (b)
hot-reloadable (swap the config, nothing else), and (c) SIMULATABLE — you can
dry-run an alternate config against recorded aggregations for a what-if, which is
exactly `simulate()` below.

Detection (detectors) is separated from aggregation (aggregator) is separated
from decision (this module). The engine decides only from the per-check summary,
adjusting thresholds by the caller's role and the conversation's trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .aggregator import Aggregation, aggregate
from .base import Action, Context, Signal, Stage, Verdict

_RANK = {Action.ALLOW: 0, Action.SANITIZE: 1, Action.REDACT: 1, Action.BLOCK: 2}


@dataclass
class PolicyConfig:
    """Declarative policy. A rules backend (OPA) can replace this later without
    changing callers — decide() only reads these fields."""

    block_thresholds: dict[str, float] = field(default_factory=lambda: {"LLM01": 0.85})
    sanitize_thresholds: dict[str, float] = field(default_factory=lambda: {"LLM01": 0.55})
    admin_relaxation: float = 0.10  # trusted admins get slightly higher thresholds
    trust_sensitivity: float = 0.20  # how hard low trust tightens thresholds
    min_threshold: float = 0.30  # clamp so trust can't drive thresholds absurdly low
    max_threshold: float = 0.99

    def to_dict(self) -> dict:
        return {
            "block_thresholds": dict(self.block_thresholds),
            "sanitize_thresholds": dict(self.sanitize_thresholds),
            "admin_relaxation": self.admin_relaxation,
            "trust_sensitivity": self.trust_sensitivity,
            "min_threshold": self.min_threshold,
            "max_threshold": self.max_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyConfig":
        base = cls()
        return cls(
            block_thresholds={**base.block_thresholds, **(data.get("block_thresholds") or {})},
            sanitize_thresholds={**base.sanitize_thresholds, **(data.get("sanitize_thresholds") or {})},
            admin_relaxation=float(data.get("admin_relaxation", base.admin_relaxation)),
            trust_sensitivity=float(data.get("trust_sensitivity", base.trust_sensitivity)),
            min_threshold=float(data.get("min_threshold", base.min_threshold)),
            max_threshold=float(data.get("max_threshold", base.max_threshold)),
        )


def _adjust(base: float, ctx: Context, cfg: PolicyConfig) -> float:
    """Role relaxes (raises) the threshold; low trust tightens (lowers) it."""
    relax = cfg.admin_relaxation if ctx.user_role == "admin" else 0.0
    penalty = (1.0 - ctx.conversation_trust) * cfg.trust_sensitivity
    return max(cfg.min_threshold, min(cfg.max_threshold, base + relax - penalty))


def decide(text: str, agg: Aggregation, ctx: Context, cfg: PolicyConfig) -> Verdict:
    """Pure decision from the aggregated per-check summary."""
    decision = Action.ALLOW
    reason_bits: list[str] = []
    breakdown: dict = {}

    # Egress leak (canary) is an absolute block; all signals here share ctx.stage.
    if ctx.stage == Stage.EGRESS:
        for agg_check in agg.by_check.values():
            if agg_check.action_hint == Action.BLOCK:
                return Verdict(
                    action=Action.BLOCK,
                    reason=f"egress leak ({agg_check.check})",
                    text=text,
                    signals=agg.all_signals,
                    stage=ctx.stage,
                    breakdown={agg_check.check: {"score": agg_check.score, "action": "BLOCK"}},
                )

    for check, ac in agg.by_check.items():
        block_at = cfg.block_thresholds.get(check)
        san_at = cfg.sanitize_thresholds.get(check)
        hint = ac.action_hint

        eff_block = _adjust(block_at, ctx, cfg) if block_at is not None else None
        eff_san = _adjust(san_at, ctx, cfg) if san_at is not None else None

        if eff_block is not None and ac.score >= eff_block:
            hint = Action.BLOCK
        elif eff_san is not None and ac.score >= eff_san and hint == Action.ALLOW:
            hint = Action.SANITIZE

        breakdown[check] = {
            "score": ac.score,
            "action": hint.value,
            "threshold": eff_block,
            "contributors": [
                {"id": s.detector_id, "score": s.score, "mode": s.mode.value} for s in ac.contributors
            ],
        }
        if _RANK[hint] > _RANK[decision]:
            decision = hint
        if hint != Action.ALLOW:
            reason_bits.append(f"{check}={ac.score:.2f}->{hint.value}")

    # Also surface shadow signals in the breakdown (observed, not enforced).
    if agg.shadow:
        breakdown["_shadow"] = [
            {"id": s.detector_id, "check": s.check, "score": s.score, "action": s.action_hint.value}
            for s in agg.shadow
        ]

    final_text = _apply_transform(text, agg)
    reason = "; ".join(reason_bits) or ("clean" if decision == Action.ALLOW else decision.value.lower())
    return Verdict(
        action=decision,
        reason=reason,
        text=final_text,
        signals=agg.all_signals,
        stage=ctx.stage,
        breakdown=breakdown,
    )


def _apply_transform(base_text: str, agg: Aggregation) -> str:
    """Compose all enforced rewrites via SPAN MERGE.

    Every rewriting detector emits spans on the SAME (boundary-normalized) text,
    so we merge spans from ALL enforced contributors (across checks), drop
    overlaps, and apply them together — regex-PII + Presidio + injection-sanitize
    all compose without any one dropping another's redactions. Falls back to a
    single transformed_text only when no spans are present.
    """
    spans = []
    for ac in agg.by_check.values():
        for sig in ac.contributors:
            for sp in sig.spans or []:
                if 0 <= sp.start < sp.end <= len(base_text):
                    spans.append(sp)

    if spans:
        # Sort by start (longer first on ties); keep non-overlapping.
        spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
        merged = []
        last_end = -1
        for sp in spans:
            if sp.start >= last_end:
                merged.append(sp)
                last_end = sp.end
        # Apply right-to-left so earlier offsets stay valid.
        text = base_text
        for sp in sorted(merged, key=lambda s: s.start, reverse=True):
            rep = sp.replacement if sp.replacement is not None else "[REDACTED]"
            text = text[: sp.start] + rep + text[sp.end :]
        return text

    # Fallback: single-detector transform (REDACT preferred, then SANITIZE).
    redact = next((a for a in agg.by_check.values() if a.action_hint == Action.REDACT and a.transformed_text), None)
    if redact is not None:
        return redact.transformed_text
    san = next((a for a in agg.by_check.values() if a.transformed_text), None)
    return san.transformed_text if san is not None else base_text


def simulate(records: list[tuple[str, list[Signal], Context]], cfg: PolicyConfig) -> list[Verdict]:
    """Dry-run a policy config against recorded (text, signals, ctx) tuples.

    Pure: recomputes aggregation + decision with `cfg` without touching live
    state — the engine of the control-plane "what-if".
    """
    return [decide(text, aggregate(signals), ctx, cfg) for text, signals, ctx in records]
