"""Per-tenant rate limiting + token budgets.

  RateLimiter  — token bucket per tenant: smooth request throttling with a
                 Retry-After hint. Uses time.monotonic (immune to clock jumps).
  BudgetTracker — per-tenant daily token allowance (cost control).

Both are in-memory + bounded (per replica). For multi-replica coherence they'd
move to Redis; the allow/spend surface is small enough to swap.
"""

from __future__ import annotations

import time
from collections import OrderedDict

_MAX_TENANTS = 10000  # bound memory against tenant-id churn


class RateLimiter:
    def __init__(self, capacity: int, refill_per_s: float) -> None:
        self.capacity = float(capacity)
        self.refill = refill_per_s
        self._buckets: "OrderedDict[str, tuple[float, float]]" = OrderedDict()

    def allow(self, tenant: str, cost: float = 1.0) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        tokens, last = self._buckets.get(tenant, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens >= cost:
            self._buckets[tenant] = (tokens - cost, now)
            self._touch(tenant)
            return True, 0.0
        retry = (cost - tokens) / self.refill if self.refill > 0 else 60.0
        self._buckets[tenant] = (tokens, now)
        self._touch(tenant)
        return False, retry

    def _touch(self, tenant: str) -> None:
        self._buckets.move_to_end(tenant)
        while len(self._buckets) > _MAX_TENANTS:
            self._buckets.popitem(last=False)


class BudgetTracker:
    def __init__(self, per_day: int) -> None:
        self.per_day = per_day
        self._spent: dict[tuple[str, int], int] = {}

    @staticmethod
    def _day() -> int:
        return int(time.time() // 86400)

    def available(self, tenant: str) -> bool:
        return self._spent.get((tenant, self._day()), 0) < self.per_day

    def remaining(self, tenant: str) -> int:
        return max(0, self.per_day - self._spent.get((tenant, self._day()), 0))

    def spend(self, tenant: str, tokens: int) -> None:
        day = self._day()
        self._spent[(tenant, day)] = self._spent.get((tenant, day), 0) + max(0, tokens)
        # Prune stale days if the map grows.
        if len(self._spent) > _MAX_TENANTS:
            self._spent = {k: v for k, v in self._spent.items() if k[1] == day}


def estimate_tokens(text: str) -> int:
    # Rough heuristic (~4 chars/token) — good enough for budgeting/accounting.
    return max(1, len(text or "") // 4)
