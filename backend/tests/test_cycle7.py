"""Cycle 7 tests: provider chain, rate limit + budget, durable audit."""

from __future__ import annotations

from app.core.limits import BudgetTracker, RateLimiter, estimate_tokens
from app.observability import AuditSink, Event, EventKind, SqliteAuditStore
from app.providers.mock import MockProvider
from app.providers.registry import build_providers


def test_default_chain_is_two_mocks():
    chain = build_providers({})
    assert [p.name for p in chain] == ["gpt-primary", "claude-secondary"]


def test_provider_chain_drops_keyless_real_keeps_mock(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PROVIDER_CHAIN", "openai,mock")
    get_settings.cache_clear()
    try:
        chain = build_providers({})
        assert "openai" not in [p.name for p in chain]  # no key -> dropped
        assert any(isinstance(p, MockProvider) for p in chain)  # fallback present
    finally:
        get_settings.cache_clear()


def test_rate_limiter_blocks_after_capacity():
    rl = RateLimiter(capacity=2, refill_per_s=0.0)
    assert rl.allow("t")[0] is True
    assert rl.allow("t")[0] is True
    ok, retry = rl.allow("t")
    assert ok is False and retry > 0


def test_rate_limiter_is_per_tenant():
    rl = RateLimiter(capacity=1, refill_per_s=0.0)
    assert rl.allow("a")[0] is True
    assert rl.allow("b")[0] is True  # separate bucket
    assert rl.allow("a")[0] is False


def test_budget_exhausts_and_reports_remaining():
    b = BudgetTracker(per_day=10)
    assert b.available("t")
    b.spend("t", 7)
    assert b.remaining("t") == 3
    b.spend("t", 5)
    assert not b.available("t")


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 40) == 10


def test_durable_audit_resumes_chain_across_restart(tmp_path):
    db = str(tmp_path / "audit.db")

    a1 = AuditSink(store=SqliteAuditStore(db))
    a1.append(Event(kind=EventKind.INPUT_BLOCKED, action="BLOCK", check="LLM01"))
    a1.append(Event(kind=EventKind.CANARY_TRIPPED, action="BLOCK", provider="p"))
    assert a1.verify()

    # "restart": a fresh sink over the same durable store.
    a2 = AuditSink(store=SqliteAuditStore(db))
    assert len(a2.recent(10)) == 2
    assert a2.verify()  # chain intact after reload

    a2.append(Event(kind=EventKind.INPUT_REDACTED, action="REDACT", check="LLM06"))
    assert a2.verify()  # continued chain still intact
    assert a2.recent(10)[-1]["seq"] == 3  # seq continued, not reset
