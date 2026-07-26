"""Event sinks — where domain events land.

  AuditSink   — durable, append-only, TAMPER-EVIDENT (hash chain) record of
                security decisions. Written synchronously before the response.
  MetricsSink — bounded-cardinality counters + latency histograms.
  LogSink     — structured logs (one JSON-ish line per event).

All three sit behind small methods so a DB-backed audit sink or an OpenTelemetry
metrics/log exporter can replace them without touching the emitters.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict, deque

from .events import Event

_GENESIS = "0" * 64
_logger = logging.getLogger("guardrail.events")


def _entry_payload(seq: int, ev: Event) -> str:
    # Only decision-relevant, non-sensitive fields — never the prompt text.
    return "|".join(
        str(x)
        for x in (seq, ev.kind, ev.conversation_id, ev.action, ev.check, ev.provider)
    )


class AuditSink:
    """Append-only, hash-chained audit of security decisions.

    Each entry's hash = sha256(prev_hash + payload). Any edit/reorder/deletion
    within the retained window breaks `verify()`.

    This is tamper-EVIDENT, not tamper-PROOF: with a plain sha256 chain, an actor
    who can run code could recompute the whole chain. Production hardening =
    HMAC the chain with a server-held secret (so it can't be recomputed) and/or
    append to a WORM/append-only store. The DB-backed durable sink is the other
    production upgrade; the interface here stays the same. Bounded (deque).
    """

    def __init__(self, max_entries: int = 1000, store=None) -> None:
        self._entries: deque[dict] = deque(maxlen=max_entries)
        self._store = store
        if store is not None:
            # Resume the chain across restarts: pick up seq + last hash, and warm
            # the in-memory window from the durable store.
            self._seq, self._last_hash = store.last()
            for e in store.recent(max_entries):
                self._entries.append(e)
        else:
            self._seq = 0
            self._last_hash = _GENESIS

    def append(self, ev: Event) -> dict:
        self._seq += 1
        payload = _entry_payload(self._seq, ev)
        h = hashlib.sha256((self._last_hash + payload).encode("utf-8")).hexdigest()
        entry = {
            "seq": self._seq,
            "kind": ev.kind,
            "conversation_id": ev.conversation_id,
            "action": ev.action,
            "check": ev.check,
            "provider": ev.provider,
            "prev": self._last_hash,
            "hash": h,
        }
        self._last_hash = h
        self._entries.append(entry)
        if self._store is not None:
            self._store.append(entry)  # durable, synchronous
        return entry

    def recent(self, n: int = 50) -> list[dict]:
        items = list(self._entries)
        return items[-n:]

    def verify(self) -> bool:
        """Recompute the chain over the retained window; True if intact."""
        prev = None
        for e in self._entries:
            payload = _entry_payload(e["seq"], Event(kind=e["kind"], conversation_id=e["conversation_id"], action=e["action"], check=e["check"], provider=e["provider"]))
            expected = hashlib.sha256((e["prev"] + payload).encode("utf-8")).hexdigest()
            if expected != e["hash"]:
                return False
            if prev is not None and e["prev"] != prev["hash"]:
                return False
            prev = e
        return True


class MetricsSink:
    """Counters + latency histograms. Cardinality is bounded on purpose: keys use
    only fixed dimensions (kind, action, provider) — never per-user/conversation
    ids, which would explode cardinality and become a memory-DoS vector."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self._hist: dict[str, dict] = {}

    def record(self, ev: Event) -> None:
        self.counters[f"events.{ev.kind}"] += 1
        if ev.action:
            self.counters[f"action.{ev.action}"] += 1
        if ev.provider and ev.kind == "response_completed":
            self.counters[f"provider.{ev.provider}.completed"] += 1
        if ev.latency_ms is not None:
            self._observe("request_latency_ms", ev.latency_ms)

    def _observe(self, name: str, value: float) -> None:
        h = self._hist.get(name)
        if h is None:
            self._hist[name] = {"count": 1, "sum": value, "min": value, "max": value}
        else:
            h["count"] += 1
            h["sum"] += value
            h["min"] = min(h["min"], value)
            h["max"] = max(h["max"], value)

    def snapshot(self) -> dict:
        hist = {
            n: {**h, "avg": round(h["sum"] / h["count"], 2) if h["count"] else None}
            for n, h in self._hist.items()
        }
        return {"counters": dict(self.counters), "histograms": hist}


class LogSink:
    def write(self, ev: Event) -> None:
        _logger.info(
            json.dumps(
                {
                    "kind": ev.kind,
                    "stage": ev.stage,
                    "action": ev.action,
                    "check": ev.check,
                    "provider": ev.provider,
                    "status": ev.status,
                    "latency_ms": ev.latency_ms,
                },
                ensure_ascii=False,
            )
        )
