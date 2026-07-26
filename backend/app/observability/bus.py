"""EventBus — the sync-audit / best-effort-telemetry split.

The senior distinction (ARCHITECTURE.md §2.3):
  * record(event)  — SECURITY decisions. The audit write is SYNCHRONOUS and its
    errors propagate (a durable sink that can't record a BLOCK should surface,
    not silently drop it). Metrics/log are best-effort on top.
  * observe(event) — operational TELEMETRY. Entirely best-effort: a failing
    metrics/log sink must NEVER break a request.
"""

from __future__ import annotations

import logging

from .events import SECURITY_KINDS, Event
from .sinks import AuditSink, LogSink, MetricsSink

_logger = logging.getLogger("guardrail.events")


class EventBus:
    def __init__(
        self,
        audit: AuditSink | None = None,
        metrics: MetricsSink | None = None,
        log: LogSink | None = None,
    ) -> None:
        self.audit = audit or AuditSink()
        self.metrics = metrics or MetricsSink()
        self.log = log or LogSink()

    @staticmethod
    def _safe(fn, ev: Event) -> None:
        try:
            fn(ev)
        except Exception:  # telemetry must never break a request
            _logger.exception("telemetry sink failed")

    def record(self, ev: Event) -> None:
        """Security decision: durable audit first (authoritative), then telemetry."""
        if ev.kind not in SECURITY_KINDS:
            # Guard against a telemetry event slipping into the audit log.
            return self.observe(ev)
        self.audit.append(ev)  # sync; errors intentionally propagate
        self._safe(self.metrics.record, ev)
        self._safe(self.log.write, ev)

    def observe(self, ev: Event) -> None:
        """Operational telemetry: best-effort only."""
        self._safe(self.metrics.record, ev)
        self._safe(self.log.write, ev)
