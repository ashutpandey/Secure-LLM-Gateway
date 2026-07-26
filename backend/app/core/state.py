"""Wiring — builds the singletons the API depends on.

Importing `app.guardrails.detectors` triggers each detector's `@register_detector`
side-effect; `build_registry` then applies the startup config (modes/weights).
This is the composition root: everything swappable is assembled here.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from ..gateway import Gateway
from ..guardrails import GuardrailService, PolicyStore, SignalCache, build_registry
from ..guardrails import detectors as _detectors  # noqa: F401  (registration side-effect)
from ..observability import EventBus
from .conversations import ConversationTracker
from .limits import BudgetTracker, RateLimiter
from .sessions import SessionMemory


@lru_cache
def get_registry():
    settings = get_settings()
    return build_registry(settings.load_guardrails_config())


@lru_cache
def get_bus() -> EventBus:
    settings = get_settings()
    if settings.audit_db:
        # Durable, restart-surviving audit backed by sqlite (stdlib).
        from ..observability import AuditSink, SqliteAuditStore

        return EventBus(audit=AuditSink(store=SqliteAuditStore(settings.audit_db)))
    return EventBus()


@lru_cache
def get_rate_limiter() -> RateLimiter:
    s = get_settings()
    return RateLimiter(s.rate_capacity, s.rate_refill_per_s)


@lru_cache
def get_budget() -> BudgetTracker:
    return BudgetTracker(get_settings().token_budget_per_day)


@lru_cache
def get_policy_store() -> PolicyStore:
    return PolicyStore(get_settings().policy_config_path)


@lru_cache
def get_tracker() -> ConversationTracker:
    return ConversationTracker()


@lru_cache
def get_session_memory() -> SessionMemory:
    return SessionMemory()


@lru_cache
def get_service() -> GuardrailService:
    settings = get_settings()
    cache = (
        SignalCache(max_entries=settings.cache_max_entries, ttl_s=settings.cache_ttl_s)
        if settings.cache_enabled
        else None
    )
    return GuardrailService(
        get_registry(),
        per_detector_timeout_s=settings.per_detector_timeout_s,
        strategy=settings.guardrail_strategy,
        cache=cache,
        circuit_config={
            "failure_threshold": settings.circuit_failure_threshold,
            "reset_timeout_s": settings.circuit_reset_timeout_s,
        },
        # Hot-reload: the service reads the current policy per request via the store.
        policy_provider=get_policy_store().get,
        max_input_chars=settings.max_input_chars,
        allow_external_egress=settings.allow_external_egress,
    )


@lru_cache
def get_gateway() -> Gateway:
    settings = get_settings()
    return Gateway(
        get_service(),
        provider_timeout_s=settings.provider_timeout_s,
        tracker=get_tracker(),
        bus=get_bus(),
        session=get_session_memory(),
    )
