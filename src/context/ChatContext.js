// The ONLY state container — native Context + useReducer, no external library.
//
// SCALE NOTE — why THREE contexts instead of one:
// Token streaming dispatches state on (almost) every frame. If state, dispatch,
// and the gateway all lived in one context value, EVERY consumer would re-render
// on every token — StatusBar, the composer, the security panel, all of it. React
// Context has no selector, so the fix is to separate concerns into contexts that
// change at different rates:
//   • ChatStateContext   — the full state (messages/history). Changes per commit.
//   • ChatStatusContext  — just { isLoading }. Changes twice per request.
//   • ChatActionsContext — { dispatch, gateway, send }. STABLE — never changes.
// Components subscribe only to the slice they need, so dispatch-only components
// (e.g. ChatWindow) and status-only components (Composer, SecurityPanel) do NOT
// re-render while tokens stream.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { chatReducer, initialState, ACTIONS, newId } from "./chatReducer";
import { createBackendGateway } from "../services/backendGateway";
import { sanitizeOutput } from "../guardrails";
import { DEMO_MODE } from "../config";
import {
  useConversations,
  useConversationActions,
} from "./ConversationsContext";

// Contexts are split by RATE OF CHANGE so consumers only re-render for the slice
// they use:
//   ChatStateContext    — full state; changes per frame (messages). Message list.
//   ChatStatusContext   — { isLoading, stage, activeProvider }; a few × / request.
//   ChatRequestsContext — requests[]; changes on lifecycle events, NOT per token.
//   ChatHistoryContext  — history[]; changes on audit-log events, NOT per token.
//   ChatActionsContext  — { dispatch, gateway, send }; STABLE.
// The requests/history contexts are handed the array reference straight from
// state, which the reducer only replaces when that slice actually changes — so
// the Inspector and Audit tabs stay quiet while tokens stream.
const ChatStateContext = createContext(null);
const ChatStatusContext = createContext(null);
const ChatRequestsContext = createContext(null);
const ChatHistoryContext = createContext(null);
const ChatActionsContext = createContext(null);

// performance.now() when available (monotonic), else Date.now(). Used only in
// the async send loop — never inside the reducer, which must stay pure.
const now = () =>
  typeof performance !== "undefined" && performance.now
    ? performance.now()
    : Date.now();

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  // One gateway per app; components talk to this, never to a provider directly.
  // The backend (FastAPI guardrail pipeline) is the single source of truth for
  // enforcement — the client only streams from it (SSE) and sanitizes output at
  // the render boundary (LLM02). Requires REACT_APP_API_BASE to be set.
  const gateway = useMemo(() => createBackendGateway(), []);

  // --- Bridge to the ConversationsContext -------------------------------
  // ChatProvider owns the LIVE chat state; ConversationsContext owns the
  // persisted per-conversation snapshots. We hydrate on switch and persist on
  // settle so the sidebar/history reflects real message counts & metrics.
  const { activeId } = useConversations();
  const { getSnapshot, persistActive } = useConversationActions();

  // Hydrate live chat state from the snapshot whenever the active conversation
  // changes (including first mount). HYDRATE sets state.convId + data atomically,
  // so downstream persistence never sees a mismatched (convId, data) pair.
  useEffect(() => {
    if (state.convId === activeId) return;
    dispatch({ type: ACTIONS.HYDRATE, snapshot: getSnapshot(activeId) });
  }, [activeId, getSnapshot, state.convId]);

  // Persist the conversation whenever its data changes AND no request is in
  // flight. The isLoading guard skips per-token writes during streaming; the
  // write lands once the stream settles — and on RESET, which deliberately keeps
  // convId so the cleared conversation is written back (fixing the stale-card
  // desync). Data + convId always change together (atomic HYDRATE), so a write
  // can never store one conversation's messages under another's id.
  useEffect(() => {
    if (state.isLoading || !state.convId) return;
    persistActive(state.convId, {
      messages: state.messages,
      history: state.history,
      requests: state.requests,
    });
  }, [
    state.isLoading,
    state.convId,
    state.messages,
    state.history,
    state.requests,
    persistActive,
  ]);

  // In-flight guard lives in a ref, not in state, so `send` never has to read
  // (and therefore subscribe to) state — that keeps `send` referentially stable.
  const inFlightRef = useRef(false);
  // Current conversation id, read by `send` without subscribing to state (so the
  // backend can attribute the request to a conversation for trust tracking).
  const convIdRef = useRef(null);
  convIdRef.current = state.convId;

  const send = useCallback(
    async (prompt, opts = {}) => {
      if (!prompt.trim() || inFlightRef.current) return;
      inFlightRef.current = true;

      // Ids are minted here so we always know which bubble to stream into.
      const userId = newId();
      const assistantId = newId();
      dispatch({ type: ACTIONS.SEND_START, prompt, userId, assistantId });

      // --- rAF token coalescing ------------------------------------------
      // Each token event carries the FULL accumulated text (replace-on-render),
      // so we only need to commit the LATEST one per animation frame. This
      // turns N token dispatches into at most ~1 render per frame (~60fps),
      // instead of one full re-render per token.
      let pendingRaw = null; // latest full UNsanitized text awaiting a frame
      let lastRemoved = []; // neutralizations from the most recent commit (L0.2)
      let rafId = 0;
      const commit = () => {
        rafId = 0;
        if (pendingRaw == null) return;
        // LLM02 at the render boundary: sanitize the accumulated raw text once
        // per animation frame, immediately before it enters React's tree.
        const { sanitizedText, removed } = sanitizeOutput(pendingRaw);
        lastRemoved = removed;
        dispatch({
          type: ACTIONS.STREAM_TOKEN,
          id: assistantId,
          text: sanitizedText,
          // Persist/expose the raw original only in DEMO_MODE (S1): keeps the
          // before/after reveal for demos, never stores dangerous output at rest.
          raw: DEMO_MODE ? pendingRaw : undefined,
          removed,
        });
        pendingRaw = null;
      };
      const schedule = () => {
        if (rafId === 0) rafId = requestAnimationFrame(commit);
      };
      const cancel = () => {
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = 0;
        }
      };

      const reader = gateway
        .stream(prompt, { ...opts, conversationId: convIdRef.current })
        .getReader();
      let lastRaw = null;

      // --- request metrics (measured here, NOT in the pure reducer) --------
      const startedAt = now();
      let firstTokenAt = null; // for time-to-first-token
      let tokenChunks = 0; // number of stream chunks received
      let finalTextLen = 0; // chars in the final raw text

      try {
        while (true) {
          const { value: ev, done } = await reader.read();
          if (done) break;

          switch (ev.type) {
            case "sanitized":
              dispatch({
                type: ACTIONS.INPUT_SANITIZED,
                id: assistantId,
                userId, // so the reducer can redact the stored user message
                verdict: ev.verdict,
              });
              break;
            case "blocked":
              dispatch({
                type: ACTIONS.GUARDRAIL_BLOCKED,
                id: assistantId,
                verdict: ev.verdict,
              });
              break;
            case "provider":
              dispatch({
                type: ACTIONS.PROVIDER,
                id: assistantId,
                name: ev.name,
                model: ev.model,
              });
              break;
            case "retry":
              dispatch({
                type: ACTIONS.PROVIDER_RETRY,
                id: assistantId,
                provider: ev.provider,
                attempt: ev.attempt,
                status: ev.status,
                waitMs: ev.waitMs,
              });
              break;
            case "fallback":
              dispatch({
                type: ACTIONS.PROVIDER_SWITCH,
                id: assistantId,
                from: ev.from,
                to: ev.to,
                status: ev.status,
              });
              break;
            case "canary":
              // Egress leak: drop any buffered tokens and withhold the response.
              cancel();
              dispatch({
                type: ACTIONS.OUTPUT_BLOCKED,
                id: assistantId,
                provider: ev.provider,
                message:
                  "Response withheld: system-prompt canary detected in model output (possible prompt-injection exfiltration).",
              });
              break;
            case "token":
              if (firstTokenAt == null) firstTokenAt = now();
              tokenChunks += 1;
              lastRaw = ev.raw;
              finalTextLen = (ev.raw || "").length;
              pendingRaw = ev.raw; // latest full raw; sanitized at commit time
              schedule();
              break;
            case "done": {
              cancel();
              commit(); // flush the final buffered text before marking done
              const endedAt = now();
              const streamMs =
                firstTokenAt != null ? endedAt - firstTokenAt : null;
              const metrics = {
                ttftMs: firstTokenAt != null ? firstTokenAt - startedAt : null,
                durationMs: endedAt - startedAt,
                streamMs,
                tokenCount: tokenChunks,
                tokensPerSec:
                  streamMs && streamMs > 0
                    ? tokenChunks / (streamMs / 1000)
                    : null,
                avgChunkSize:
                  tokenChunks > 0 ? finalTextLen / tokenChunks : null,
              };
              // Reuse the last commit's neutralizations — the final frame already
              // sanitized this exact text, so re-running it would be redundant (L0.2).
              dispatch({
                type: ACTIONS.STREAM_DONE,
                id: assistantId,
                provider: ev.provider,
                removed: lastRemoved,
                raw: DEMO_MODE ? lastRaw : undefined,
                metrics,
              });
              break;
            }
            case "error":
              cancel();
              dispatch({
                type: ACTIONS.STREAM_ERROR,
                id: assistantId,
                message: ev.message,
              });
              break;
            default:
              break;
          }
        }
      } finally {
        reader.releaseLock();
        cancel();
        commit(); // safety: commit anything still buffered
        inFlightRef.current = false;
      }
    },
    [gateway] // dispatch is stable across renders
  );

  // STABLE — this object identity never changes, so action/dispatch-only
  // consumers never re-render due to streaming.
  const actions = useMemo(() => ({ dispatch, gateway, send }), [gateway, send]);

  // Single source of truth for the active provider: the most recent request that
  // has been routed. Derived (not stored) so it can't drift from the requests.
  const activeProvider = useMemo(() => {
    for (let i = state.requests.length - 1; i >= 0; i--) {
      if (state.requests[i].provider) return state.requests[i].provider;
    }
    return null;
  }, [state.requests]);

  // Changes a few times per request (loading flag + stage + provider), never per
  // token — so the header and status pill don't re-render while streaming.
  const status = useMemo(
    () => ({
      isLoading: state.isLoading,
      stage: state.stage,
      activeProvider,
    }),
    [state.isLoading, state.stage, activeProvider]
  );

  return (
    <ChatActionsContext.Provider value={actions}>
      <ChatStatusContext.Provider value={status}>
        <ChatRequestsContext.Provider value={state.requests}>
          <ChatHistoryContext.Provider value={state.history}>
            <ChatStateContext.Provider value={state}>
              {children}
            </ChatStateContext.Provider>
          </ChatHistoryContext.Provider>
        </ChatRequestsContext.Provider>
      </ChatStatusContext.Provider>
    </ChatActionsContext.Provider>
  );
}

export function useChatState() {
  const ctx = useContext(ChatStateContext);
  if (ctx === null)
    throw new Error("useChatState must be used within <ChatProvider>");
  return ctx;
}

export function useChatStatus() {
  const ctx = useContext(ChatStatusContext);
  if (ctx === null)
    throw new Error("useChatStatus must be used within <ChatProvider>");
  return ctx;
}

// requests[] — changes only on request-lifecycle events, not per token.
export function useChatRequests() {
  const ctx = useContext(ChatRequestsContext);
  if (ctx === null)
    throw new Error("useChatRequests must be used within <ChatProvider>");
  return ctx;
}

// history[] — changes only when an audit entry is appended, not per token.
export function useChatHistory() {
  const ctx = useContext(ChatHistoryContext);
  if (ctx === null)
    throw new Error("useChatHistory must be used within <ChatProvider>");
  return ctx;
}

export function useChatActions() {
  const ctx = useContext(ChatActionsContext);
  if (ctx === null)
    throw new Error("useChatActions must be used within <ChatProvider>");
  return ctx;
}
