"""POST /api/chat — SSE stream through the gateway (guardrails + routing).

Applies per-tenant rate limiting + token budgeting before streaming, and accounts
the streamed tokens against the budget on completion.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..core.limits import estimate_tokens
from ..core.sse import sse_event
from ..core.state import get_budget, get_gateway, get_rate_limiter
from ..guardrails import Context, Stage
from ..schemas.http import ChatRequest
from .deps import get_tenant

router = APIRouter()


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    gateway = get_gateway()
    settings = get_settings()
    tenant = get_tenant(request)

    # --- per-tenant limits (429 with Retry-After) ------------------------
    allowed, retry_after = get_rate_limiter().allow(tenant)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )
    budget = get_budget()
    if not budget.available(tenant):
        raise HTTPException(status_code=429, detail="token budget exhausted for today")

    # SECURITY: req.opts fault-injection knobs + demo role override are honored
    # ONLY in DEMO_MODE (attacker-controllable otherwise).
    opts = req.opts if settings.demo_mode else {}
    ctx = Context(
        stage=Stage.INPUT,
        conversation_id=req.conversation_id,
        user_role=str(opts.get("role", "user")),
        tenant=tenant,
    )

    async def event_stream():
        out_chars = 0
        async for event in gateway.stream(req.prompt, ctx, opts):
            if event.get("type") == "token":
                out_chars = len(event.get("raw", ""))  # accumulated; last = total
            yield sse_event(event)
        # Account tokens used (prompt + output estimate) against the budget.
        budget.spend(tenant, estimate_tokens(req.prompt) + out_chars // 4)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
