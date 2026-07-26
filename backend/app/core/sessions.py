"""Session memory — per-conversation recent injection "probes" for multi-turn
detection.

Most guardrails score each message in isolation, so a *gradual* jailbreak — a
series of individually-benign turns that together steer the model — slips through.
This keeps a short rolling window of prior turns' probe scores + signal labels so
the MultiTurnDetector can spot the accumulation.

In-memory + bounded (per replica); Redis-swappable for multi-replica, same
history/record surface.
"""

from __future__ import annotations

from collections import OrderedDict, deque

_WINDOW = 8  # how many recent turns to remember per conversation
_MAX_CONVERSATIONS = 5000


class SessionMemory:
    def __init__(self, window: int = _WINDOW, max_conversations: int = _MAX_CONVERSATIONS) -> None:
        self.window = window
        self.max_conversations = max_conversations
        self._by_id: "OrderedDict[str, deque]" = OrderedDict()

    def history(self, conversation_id: str | None) -> list[dict]:
        if not conversation_id:
            return []
        dq = self._by_id.get(conversation_id)
        return list(dq) if dq else []

    def record(self, conversation_id: str | None, score: float, labels: list[str]) -> None:
        if not conversation_id:
            return
        dq = self._by_id.get(conversation_id)
        if dq is None:
            dq = deque(maxlen=self.window)
            self._by_id[conversation_id] = dq
            while len(self._by_id) > self.max_conversations:
                self._by_id.popitem(last=False)  # evict LRU conversation
        else:
            self._by_id.move_to_end(conversation_id)
        dq.append({"score": round(float(score), 4), "labels": list(labels)[:20]})
