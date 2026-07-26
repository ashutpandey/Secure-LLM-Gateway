"""Anthropic provider plugin — real streaming via the Anthropic SDK.

Lazy-imported + key-gated like the OpenAI plugin. Same Provider contract, so the
gateway treats it identically for retry/failover.
"""

from __future__ import annotations

from typing import AsyncIterator

from .base import ProviderError


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024) -> None:
        self.name = "anthropic"
        self.model = model
        self._api_key = api_key
        self._max_tokens = max_tokens

    async def stream(self, prompt: str, opts: dict) -> AsyncIterator[str]:
        try:
            from anthropic import AsyncAnthropic
        except Exception as exc:
            raise ProviderError(500, self.name, f"anthropic SDK unavailable: {exc}")

        client = AsyncAnthropic(api_key=self._api_key)
        try:
            async with client.messages.stream(
                model=self.model,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None) or 500
            raise ProviderError(int(status), self.name, str(exc))
        finally:
            await client.close()
