"""Provider registry + failover chain builder.

The chain and its ORDER come from config (PROVIDER_CHAIN). With no config set,
the default is the two-mock chain (keyless demo + tests). Real providers are
opt-in and key-gated: a name is only added if its API key is present, and a mock
fallback is always appended so the chain can never be empty.

Per-request fault-injection knobs (`opts`) apply ONLY to mock providers — real
providers surface real errors.
"""

from __future__ import annotations

from ..config import get_settings
from .base import Provider
from .mock import MockProvider


def _default_mock_chain(opts: dict) -> list[Provider]:
    primary = MockProvider(
        name="gpt-primary",
        model="mock-gpt-4o",
        delay_ms=opts.get("delay_ms", 120),
        fail_with=opts.get("force_primary_error"),
        fail_times=opts.get("force_primary_fail_times", float("inf")),
        retry_after_ms=opts.get("force_primary_retry_after"),
        stall=opts.get("force_primary_stall", False),
        fail_after_tokens=opts.get("force_primary_fail_after"),
    )
    secondary = MockProvider(
        name="claude-secondary",
        model="mock-claude-sonnet",
        delay_ms=opts.get("delay_ms", 120),
        fail_with=opts.get("force_secondary_error"),
        stall=opts.get("force_secondary_stall", False),
        fail_after_tokens=opts.get("force_secondary_fail_after"),
    )
    return [primary, secondary]


def _make(name: str, opts: dict, s) -> Provider | None:
    if name in ("mock", "gpt-primary", "mock-primary"):
        return _default_mock_chain(opts)[0]
    if name in ("mock-secondary", "claude-secondary"):
        return _default_mock_chain(opts)[1]
    if name == "openai" and s.openai_api_key:
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(s.openai_api_key, s.openai_model)
    if name == "anthropic" and s.anthropic_api_key:
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    return None  # unknown name, or real provider without its key


def build_providers(opts: dict | None = None) -> list[Provider]:
    opts = opts or {}
    s = get_settings()
    if not s.provider_chain:
        return _default_mock_chain(opts)

    chain: list[Provider] = []
    for name in s.provider_chain:
        p = _make(name, opts, s)
        if p is not None:
            chain.append(p)
    if not chain:
        return _default_mock_chain(opts)
    # Guarantee a working last resort so the chain never dead-ends on a real outage.
    if not any(isinstance(p, MockProvider) for p in chain):
        chain.append(_default_mock_chain(opts)[1])
    return chain
