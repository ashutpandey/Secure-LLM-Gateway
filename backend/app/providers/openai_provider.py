"""OpenAI provider plugin — real streaming via the OpenAI SDK.

Lazy-imported and key-gated: it's only added to the failover chain when
OPENAI_API_KEY is set and the SDK is installed (see registry.build_providers), so
the backend runs keyless on the mock by default. Errors are mapped to
ProviderError(status=...) so the gateway's retry/failover policy stays
provider-agnostic.
"""

from __future__ import annotations

from typing import AsyncIterator

from .base import ProviderError


class OpenAIProvider:
    def __init__(self, api_key: str, model: str) -> None:
        self.name = "openai"
        self.model = model
        self._api_key = api_key

    async def stream(self, prompt: str, opts: dict) -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI
        except Exception as exc:  # SDK missing despite being configured
            raise ProviderError(500, self.name, f"openai SDK unavailable: {exc}")

        client = AsyncOpenAI(api_key=self._api_key)
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:  # normalize SDK errors to a retry/failover status
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None) or 500
            raise ProviderError(int(status), self.name, str(exc))
        finally:
            await client.close()
