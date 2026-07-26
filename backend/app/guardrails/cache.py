"""Signal cache — bounded LRU + TTL.

We cache DETECTOR SIGNALS, never final verdicts (per ARCHITECTURE.md §2.6): a
signal is a pure function of (detector, model version, input text), whereas a
verdict also depends on policy/context that can change. Keying includes the
tenant so one tenant's cached signal can never serve another's request.

Only deterministic, `cacheable` detectors are cached (the service decides). The
canary detector, for example, depends on the per-request canary and is not cached.

Scaling: this cache is in-process (per replica), which is correct — it's a pure
latency/cost optimization, so replicas needn't share it. The get/put/stats
surface is intentionally small so it can be backed by Redis (shared across
replicas) later without touching the service. Concurrent identical requests may
each miss-and-compute (a cache stampede); harmless for microsecond regex, so
single-flight coalescing is deferred to Cycle 6 when ML detectors make it worth it.

Security note: errored signals are NEVER cached (see `put`), so a transient
failure can't get frozen in as a permanent ALLOW.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import replace

from .base import Signal


def _key(detector_id: str, version: str | None, tenant: str, text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{detector_id}|{version or '-'}|{tenant}|{h}"


class SignalCache:
    def __init__(self, *, max_entries: int = 2048, ttl_s: float = 300.0) -> None:
        self.max_entries = max_entries
        self.ttl_s = ttl_s
        self._store: "OrderedDict[str, tuple[float, Signal]]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, detector_id: str, version: str | None, tenant: str, text: str) -> Signal | None:
        key = _key(detector_id, version, tenant, text)
        item = self._store.get(key)
        if item is None:
            self.misses += 1
            return None
        stored_at, sig = item
        if (time.monotonic() - stored_at) > self.ttl_s:
            # expired
            self._store.pop(key, None)
            self.misses += 1
            return None
        self._store.move_to_end(key)  # LRU touch
        self.hits += 1
        # Return a copy so callers can re-stamp per-call fields (mode/latency)
        # without mutating the cached original.
        return replace(sig, latency_ms=0.0, meta={**sig.meta, "cache": "hit"})

    def put(self, detector_id: str, version: str | None, tenant: str, text: str, sig: Signal) -> None:
        # Never cache an errored signal — the failure may be transient.
        if sig.error is not None:
            return
        key = _key(detector_id, version, tenant, text)
        self._store[key] = (time.monotonic(), sig)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)  # evict oldest

    @property
    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else None,
        }
