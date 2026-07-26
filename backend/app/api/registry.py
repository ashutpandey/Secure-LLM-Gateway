"""Control-plane API — GET/PATCH the live plugin registry.

GET is safe to expose. PATCH changes what is ENFORCED, so in production it MUST be
admin-RBAC-gated + audited (see ARCHITECTURE.md §2.5). It is open here for the
demo; the guard is a dependency you swap per environment, not a code change.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.state import get_registry, get_service
from ..guardrails import Mode
from ..schemas.http import RegistryPatch
from .deps import require_control_plane

router = APIRouter()


@router.get("/registry")
async def list_registry():
    reg = get_registry()
    service = get_service()
    detectors = []
    for e in reg.all():
        d = e.describe()
        d["circuit"] = service.circuit_state(d["id"])  # None until first call
        detectors.append(d)
    return {"detectors": detectors, "service": service.health()}


@router.patch("/registry/{detector_id}")
async def patch_registry(detector_id: str, patch: RegistryPatch, request: Request):
    # Authorized by admin key (if configured) else the DEMO_MODE-gated flag.
    require_control_plane(request)
    reg = get_registry()
    try:
        entry = reg.get(detector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown detector: {detector_id}")
    if patch.mode is not None:
        entry = reg.set_mode(detector_id, Mode(patch.mode))
    if patch.weight is not None:
        entry = reg.set_weight(detector_id, patch.weight)
    return entry.describe()
