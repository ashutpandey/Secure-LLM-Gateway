"""Adapter to the ML sidecar (the stable, model-agnostic HTTP contract).

The ML detector plugins call these helpers; the sidecar's model (heuristic vs
real Prompt-Guard/Presidio) is invisible here. Swapping local↔hosted inference is
a change to the sidecar, not to this adapter or the detectors above it.

Errors (no URL configured, sidecar down, timeout) propagate — the Guardrail
Service wraps every detector in a timeout + circuit breaker + fail-mode, and the
ML detectors are fail-OPEN, so a sidecar outage degrades to the regex baseline
rather than blocking chat.
"""

from __future__ import annotations

import httpx

from ...config import get_settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=get_settings().ml_timeout_s)
    return _client


async def _post(path: str, text: str) -> dict:
    base = get_settings().ml_service_url
    if not base:
        raise RuntimeError("ML sidecar not configured (ML_SERVICE_URL empty)")
    res = await _get_client().post(f"{base}{path}", json={"text": text})
    res.raise_for_status()
    return res.json()


async def score_injection(text: str) -> dict:
    return await _post("/score/injection", text)


async def scan_pii(text: str) -> dict:
    return await _post("/scan/pii", text)
