"""Gateway orchestrator — routing, retry, failover, streaming.

Port of the frontend `gateway.js`, now server-side and delegating ALL guardrail
work to the Guardrail Service. The gateway stays about *movement* (which provider,
retry vs failover, streaming); the service owns *judgement*.

It is an async generator of event dicts, serialized to SSE by the API layer. The
event contract matches the frontend's existing reader so the client swap is a
one-file change.
"""

from __future__ import annotations

import asyncio
import dataclasses
import random
import time
from typing import AsyncIterator

from ..guardrails import Action, Context, GuardrailService, Stage
from ..guardrails.detectors.canary import new_canary
from ..observability import Event, EventKind
from ..providers.base import ProviderError
from ..providers.registry import build_providers

_RETRYABLE = {429, 500, 502, 503, 504}

# Egress canary is checked per token. Scanning the FULL accumulated output each
# time is O(n^2) over a stream; instead we scan a bounded sliding window
# (previous tail + new token). The overlap must exceed any egress marker length
# (canary is ~31 chars) so a marker split across the token boundary is still
# caught. This makes per-token egress O(1) amortized -> O(n) over the stream.
_EGRESS_OVERLAP = 128


def _ser(obj):
    """JSON-safe conversion for dataclasses/enums (Verdict, Signal)."""
    if dataclasses.is_dataclass(obj):
        return {k: _ser(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_ser(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return obj


class Gateway:
    def __init__(
        self,
        guardrails: GuardrailService,
        *,
        max_retries_per_provider: int = 2,
        backoff_base_s: float = 0.25,
        backoff_cap_s: float = 2.0,
        provider_timeout_s: float = 4.0,
        tracker=None,  # optional ConversationTracker (duck-typed)
        bus=None,  # optional EventBus (duck-typed)
        session=None,  # optional SessionMemory (duck-typed)
    ) -> None:
        self.guardrails = guardrails
        self.max_retries = max_retries_per_provider
        self.backoff_base = backoff_base_s
        self.backoff_cap = backoff_cap_s
        self.provider_timeout = provider_timeout_s
        self.tracker = tracker
        self.bus = bus
        self.session = session

    def _record(self, ctx, action: str) -> None:
        if self.tracker is not None and ctx.conversation_id:
            self.tracker.record(ctx.conversation_id, action)

    def _emit(self, security: bool, ev: Event) -> None:
        if self.bus is None:
            return
        (self.bus.record if security else self.bus.observe)(ev)

    def _backoff(self, attempt: int, retry_after_ms: int | None) -> float:
        if retry_after_ms is not None:
            return retry_after_ms / 1000
        exp = min(self.backoff_base * 2 ** (attempt - 1), self.backoff_cap)
        return exp / 2 + random.random() * exp / 2

    async def stream(self, prompt: str, ctx: Context, opts: dict | None = None) -> AsyncIterator[dict]:
        opts = dict(opts or {})
        started = time.perf_counter()
        cid = ctx.conversation_id

        # Conversation trust/turn from the tracker feed the policy Context.
        if self.tracker is not None and ctx.conversation_id:
            st = self.tracker.begin_turn(ctx.conversation_id)
            ctx = dataclasses.replace(ctx, conversation_trust=st.trust, turn_index=st.turns)
        # Prior-turn probe history feeds the multi-turn detector.
        if self.session is not None and ctx.conversation_id:
            ctx = dataclasses.replace(ctx, session_history=self.session.history(ctx.conversation_id))

        # --- INPUT GUARDRAILS (delegated) ---------------------------------
        in_ctx = dataclasses.replace(ctx, stage=Stage.INPUT)
        verdict = await self.guardrails.evaluate(prompt, in_ctx)
        primary_check = next((k for k in verdict.breakdown if k != "_shadow"), None)

        # Record THIS turn's probe (excluding the multi-turn detector's own score,
        # to avoid a self-reinforcing feedback loop).
        if self.session is not None and ctx.conversation_id:
            llm01 = [s for s in verdict.signals if s.check == "LLM01" and s.detector_id != "multiturn"]
            probe = max((s.score for s in llm01), default=0.0)
            labels = [l for s in llm01 for l in s.labels]
            self.session.record(ctx.conversation_id, probe, labels)
        if verdict.action == Action.BLOCK:
            self._record(ctx, "block")
            self._emit(True, Event(kind=EventKind.INPUT_BLOCKED, stage="input", conversation_id=cid, action="BLOCK", check=primary_check))
            yield {"type": "blocked", "verdict": _ser(verdict)}
            return
        # Always surface the verdict (even clean) so the client's Security tab has data.
        yield {"type": "sanitized", "verdict": _ser(verdict)}
        if verdict.action in (Action.SANITIZE, Action.REDACT):
            self._emit(True, Event(kind=EventKind.INPUT_REDACTED, stage="input", conversation_id=cid, action=verdict.action.value, check=primary_check))
        safe_prompt = verdict.text

        # Seed a per-request canary for egress leak detection.
        canary = new_canary()
        egress_ctx = dataclasses.replace(ctx, stage=Stage.EGRESS, canary=canary)

        # --- PROVIDER ROUTING: retry (same) then failover (next) ----------
        providers = build_providers(opts)
        last_error: Exception | None = None

        for i, provider in enumerate(providers):
            has_next = i < len(providers) - 1
            for attempt in range(1, self.max_retries + 2):
                self._emit(False, Event(kind=EventKind.PROVIDER_SELECTED, provider=provider.name, conversation_id=cid))
                yield {"type": "provider", "name": provider.name, "model": provider.model}
                gen = provider.stream(
                    safe_prompt,
                    {"poison": opts.get("poison"), "canary": canary, "leak_canary": opts.get("leak_canary")},
                )
                tokens_this_attempt = 0
                raw_acc = ""
                egress_tail = ""  # sliding window carry for O(n) egress checks
                try:
                    while True:
                        try:
                            token = await asyncio.wait_for(gen.__anext__(), timeout=self.provider_timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            raise ProviderError(504, provider.name, "provider deadline exceeded")

                        raw_acc += token

                        # EGRESS guardrail (canary) BEFORE forwarding the token —
                        # on a bounded window, not the full accumulation (see
                        # _EGRESS_OVERLAP), so a long stream stays O(n).
                        egress_window = egress_tail + token
                        egress = await self.guardrails.evaluate(egress_window, egress_ctx)
                        if egress.blocked:
                            self._record(ctx, "canary")
                            self._emit(True, Event(kind=EventKind.CANARY_TRIPPED, stage="egress", conversation_id=cid, provider=provider.name, action="BLOCK", check="LLM01"))
                            yield {"type": "canary", "provider": provider.name}
                            return
                        egress_tail = egress_window[-_EGRESS_OVERLAP:]

                        tokens_this_attempt += 1
                        # Forward RAW; the client sanitizes at the render boundary
                        # (LLM02). Server output-sanitize runs once at done below.
                        yield {"type": "token", "raw": raw_acc}

                    # OUTPUT guardrail (defense-in-depth) for the audit record.
                    out_ctx = dataclasses.replace(ctx, stage=Stage.OUTPUT)
                    out_verdict = await self.guardrails.evaluate(raw_acc, out_ctx)
                    # Update conversation trust from this turn's input outcome.
                    self._record(ctx, "clean" if verdict.action == Action.ALLOW else "redact")
                    self._emit(False, Event(kind=EventKind.RESPONSE_COMPLETED, conversation_id=cid, provider=provider.name, latency_ms=(time.perf_counter() - started) * 1000))
                    yield {
                        "type": "done",
                        "provider": provider.name,
                        "output": _ser(out_verdict),
                    }
                    return
                except ProviderError as err:
                    last_error = err
                    # Mid-stream failure: tokens already sent — surface, never retry.
                    if tokens_this_attempt > 0:
                        self._emit(False, Event(kind=EventKind.REQUEST_ERROR, conversation_id=cid, provider=provider.name, status=err.status, meta={"phase": "mid-stream"}))
                        yield {
                            "type": "error",
                            "message": f"{provider.name} failed mid-stream after {tokens_this_attempt} token(s) ({err.status}); not retrying",
                        }
                        return
                    # Before first token — retry the same provider if retryable.
                    if err.status in _RETRYABLE and attempt <= self.max_retries:
                        wait = self._backoff(attempt, err.retry_after_ms)
                        self._emit(False, Event(kind=EventKind.PROVIDER_RETRY, conversation_id=cid, provider=provider.name, status=err.status))
                        yield {"type": "retry", "provider": provider.name, "attempt": attempt, "status": err.status, "waitMs": round(wait * 1000)}
                        await asyncio.sleep(wait)
                        continue
                    # Retries exhausted — fail over to the next provider.
                    if err.status in _RETRYABLE and has_next:
                        self._emit(False, Event(kind=EventKind.PROVIDER_FAILOVER, conversation_id=cid, provider=provider.name, status=err.status, meta={"to": providers[i + 1].name}))
                        yield {"type": "fallback", "from": provider.name, "to": providers[i + 1].name, "status": err.status}
                        break
                    self._emit(False, Event(kind=EventKind.REQUEST_ERROR, conversation_id=cid, provider=provider.name, status=err.status))
                    yield {"type": "error", "message": str(err)}
                    return

        self._emit(False, Event(kind=EventKind.REQUEST_ERROR, conversation_id=cid))
        yield {"type": "error", "message": str(last_error) if last_error else "all providers failed"}
