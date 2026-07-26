"""Request-scoped dependencies: tenant identity + admin gating.

Lightweight by design (not full user auth — that's fastapi-users in a later
sub-cycle). A tenant scopes rate limits, budgets, cache, and audit; an admin key
gates control-plane writes on top of the DEMO_MODE flag.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import HTTPException, Request

from ..config import get_settings


def get_tenant(request: Request) -> str:
    """Derive a tenant id for scoping limits/budgets/audit. X-Tenant wins; else a
    stable hash of the API key; else the client IP so ANONYMOUS traffic is still
    rate-limited per source. NOTE: headers are self-asserted without real auth —
    full identity is fastapi-users (deferred). Behind a proxy, honor
    X-Forwarded-For only if the proxy is trusted."""
    tenant = request.headers.get("X-Tenant")
    if tenant:
        return tenant[:64]
    key = request.headers.get("X-API-Key")
    if key:
        return "key:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return "ip:" + (request.client.host if request.client else "unknown")


def require_control_plane(request: Request) -> None:
    """Authorize a control-plane write. If an admin key is configured it MUST
    match (constant-time compare); otherwise fall back to the DEMO_MODE flag."""
    s = get_settings()
    if s.admin_api_key:
        provided = request.headers.get("X-Admin-Key", "")
        if not secrets.compare_digest(provided, s.admin_api_key):
            raise HTTPException(status_code=403, detail="admin key required")
        return
    if not s.allow_control_plane_writes:
        raise HTTPException(status_code=403, detail="control-plane writes disabled")
