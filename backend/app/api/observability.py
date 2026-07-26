"""Observability API — metrics snapshot + tamper-evident audit trail.

GET /api/metrics   counters + latency histograms (bounded cardinality)
GET /api/audit     recent security-decision audit entries + chain integrity

The audit records decision METADATA only (kind/action/check/provider/conversation),
never prompt text — safe to expose for the demo. In production the audit read
would sit behind admin-RBAC like the rest of the control plane.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..core.state import get_bus

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return get_bus().metrics.snapshot()


@router.get("/audit")
async def audit(limit: int = 50):
    sink = get_bus().audit
    return {
        "entries": sink.recent(max(1, min(limit, 500))),
        "integrity_ok": sink.verify(),
    }
