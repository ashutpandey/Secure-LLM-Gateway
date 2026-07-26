"""Conversation trust tracker — session reputation feeding the policy Context.

A conversation that has produced blocks/leaks becomes LESS trusted, and the
policy engine tightens its thresholds for that session (a caller who just tried
an injection gets more scrutiny on their next borderline prompt). Clean turns
slowly restore trust.

In-memory + bounded (per replica). Correct as a heuristic input — it's not a
security boundary on its own. For multi-replica coherence it would move to a
shared store (Redis); the get/record surface is small enough to swap.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

_START_TRUST = 0.7  # neutral-ish; not fully trusted, not hostile
_BLOCK_DECAY = 0.5  # trust *= this on a block/canary
_REDACT_DECAY = 0.85  # a redaction is milder than a block
_RECOVER = 0.05  # additive recovery on a clean turn
_MIN, _MAX = 0.0, 1.0


@dataclass
class TrustState:
    trust: float = _START_TRUST
    turns: int = 0
    blocks: int = 0


class ConversationTracker:
    def __init__(self, *, max_conversations: int = 5000) -> None:
        self._by_id: "OrderedDict[str, TrustState]" = OrderedDict()
        self.max_conversations = max_conversations

    def _get(self, conversation_id: str) -> TrustState:
        st = self._by_id.get(conversation_id)
        if st is None:
            st = TrustState()
            self._by_id[conversation_id] = st
            # Bound memory: evict the least-recently-used conversation.
            while len(self._by_id) > self.max_conversations:
                self._by_id.popitem(last=False)
        else:
            self._by_id.move_to_end(conversation_id)
        return st

    def snapshot(self, conversation_id: str | None) -> TrustState:
        """Read current trust/turn for building a Context (no mutation of turns)."""
        if not conversation_id:
            return TrustState()
        return self._get(conversation_id)

    def begin_turn(self, conversation_id: str | None) -> TrustState:
        if not conversation_id:
            return TrustState()
        st = self._get(conversation_id)
        st.turns += 1
        return st

    def record(self, conversation_id: str | None, action: str) -> None:
        """Update trust from a terminal outcome: 'block'|'canary'|'redact'|'clean'."""
        if not conversation_id:
            return
        st = self._get(conversation_id)
        if action in ("block", "canary"):
            st.trust = max(_MIN, st.trust * _BLOCK_DECAY)
            st.blocks += 1
        elif action == "redact":
            st.trust = max(_MIN, st.trust * _REDACT_DECAY)
        else:  # clean
            st.trust = min(_MAX, st.trust + _RECOVER)
