"""Per-detector circuit breaker.

When a detector (or the ML sidecar behind it) starts failing, we stop calling it
for a cool-down window instead of eating the full timeout on every request. This
is what keeps a flaky dependency from turning into latency for every user.

States:
  CLOSED    — normal; calls flow through.
  OPEN      — too many recent failures; calls short-circuit to the fail-mode
              WITHOUT invoking the detector, until the cool-down elapses.
  HALF_OPEN — cool-down elapsed; allow probe call(s). Success -> CLOSED,
              failure -> OPEN again.

Uses time.monotonic() (immune to wall-clock jumps). Not a reducer, so time is fine.
"""

from __future__ import annotations

import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, reset_timeout_s: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self.trips = 0  # total times this breaker has opened (for health surfacing)

    @property
    def state(self) -> CircuitState:
        # Lazily transition OPEN -> HALF_OPEN once the cool-down has passed.
        if self._state == CircuitState.OPEN and (time.monotonic() - self._opened_at) >= self.reset_timeout_s:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def allow(self) -> bool:
        """Whether a call should be attempted now."""
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        # A failed probe in HALF_OPEN, or crossing the threshold, opens the circuit.
        if self._state == CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                self.trips += 1
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
