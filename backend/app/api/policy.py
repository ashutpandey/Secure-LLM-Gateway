"""Policy API — inspect, hot-reload, and dry-run (what-if) the policy.

GET  /api/policy            current policy config + sim buffer size
POST /api/policy/reload     re-read policy.yaml (control-plane-gated)
POST /api/policy/simulate   run partial overrides against recent evaluations and
                            report how many decisions would change — the payoff of
                            keeping the Policy Engine a pure, simulatable function.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.state import get_policy_store, get_service
from ..guardrails import PolicyConfig, simulate
from ..schemas.http import PolicySimulate
from .deps import require_control_plane

router = APIRouter()


@router.get("/policy")
async def get_policy():
    store = get_policy_store()
    return {"policy": store.get().to_dict(), "sim_buffer": get_service().health()["sim_buffer"]}


@router.post("/policy/reload")
async def reload_policy(request: Request):
    require_control_plane(request)
    return {"policy": get_policy_store().reload().to_dict()}


def _merge(base: dict, overrides: dict) -> dict:
    out = dict(base)
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


@router.post("/policy/simulate")
async def simulate_policy(body: PolicySimulate):
    """Dry-run: recompute recent decisions under `current + overrides`. Read-only —
    never mutates the live policy."""
    store, service = get_policy_store(), get_service()
    current = store.get()
    try:
        alt = PolicyConfig.from_dict(_merge(current.to_dict(), body.overrides))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid overrides: {exc}")

    records = service.recent_records()
    before = simulate(records, current)
    after = simulate(records, alt)

    changes = []
    for b, a in zip(before, after):
        if b.action != a.action:
            changes.append({"before": b.action.value, "after": a.action.value, "reason": a.reason})

    return {
        "sample_size": len(records),
        "changed": len(changes),
        "changes": changes[:50],
        "candidate_policy": alt.to_dict(),
    }
