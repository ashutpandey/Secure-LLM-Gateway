from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    """Readiness: the app can serve. Reports optional dependency status without
    failing readiness on them (the ML sidecar is optional — detectors fail-open),
    so a sidecar blip doesn't take the whole service out of rotation."""
    s = get_settings()
    return {
        "ready": True,
        "ml_sidecar_configured": bool(s.ml_service_url),
        "durable_audit": bool(s.audit_db),
        "provider_chain": s.provider_chain or ["mock", "mock"],
    }
