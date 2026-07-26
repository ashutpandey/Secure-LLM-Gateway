// Application state — managed ONLY with useReducer (no Redux / Zustand).
//
// One reducer owns: the message list, the in-flight streaming state, loading &
// error flags, the active provider, a per-request record (metrics + guardrail
// posture, consumed by the Inspector), and an append-only audit history log.
//
// PURITY NOTE — the reducer MUST be a pure function of (state, action). React
// StrictMode double-invokes reducers in development to surface impurity, so any
// module-level counter mutated *inside* the reducer (e.g. an incrementing
// timestamp) would advance twice per dispatch and the audit trail would read
// "#2, #4, #6…". The audit sequence number is therefore DERIVED from state
// (history.length + 1) rather than pulled from a mutable module counter.

/**
 * @typedef {"user"|"assistant"} Role
 * @typedef {Object} Message
 * @property {string} id
 * @property {Role} role
 * @property {string} content
 * @property {Object} meta            streaming/blocked/error flags, removed[], raw, redacted[]
 *
 * @typedef {Object} RequestRecord    one per send, keyed by the assistant message id
 * @property {string} id
 * @property {string} prompt
 * @property {?string} provider
 * @property {?string} model
 * @property {number} retries
 * @property {number} fallbacks
 * @property {?("done"|"blocked"|"canary"|"error")} completion
 * @property {?Object} verdict        input-guardrail verdict (LLM01 + LLM06)
 * @property {string[]} outputRemoved LLM02 neutralizations
 * @property {?number} ttftMs @property {?number} durationMs @property {?number} streamMs
 * @property {?number} tokenCount @property {?number} tokensPerSec @property {?number} avgChunkSize
 *
 * @typedef {"idle"|"validating"|"routing"|"streaming"|"done"|"blocked"|"error"} Stage
 * @typedef {Object} ChatState
 * @property {?string} convId         which conversation this live state belongs to
 * @property {Message[]} messages
 * @property {boolean} isLoading
 * @property {?string} error
 * @property {Stage} stage
 * @property {RequestRecord[]} requests
 * @property {{at:string,kind:string,detail:Object}[]} history
 */

let idSeq = 0;
// A short random suffix keeps ids unique even after a page reload rehydrates
// prior conversations (whose ids were minted before idSeq reset to 0), so a
// freshly minted id can never collide with a restored one.
export const newId = () =>
  `m${++idSeq}-${Math.random().toString(36).slice(2, 7)}`;

/** @type {ChatState} */
export const initialState = {
  convId: null, // set by HYDRATE; ties this state to a persisted conversation
  messages: [], // Message[]
  isLoading: false,
  error: null,
  stage: "idle", // drives the header status + StreamStatusPill (non-per-token)
  // NOTE: the active provider is NOT stored here — it's derived from the latest
  // request record (single source of truth) in ChatProvider's status context.
  requests: [], // RequestRecord[] (Inspector)
  history: [], // audit trail: { at, kind, detail }
};

export const ACTIONS = {
  SEND_START: "SEND_START",
  PROVIDER: "PROVIDER",
  PROVIDER_RETRY: "PROVIDER_RETRY",
  PROVIDER_SWITCH: "PROVIDER_SWITCH",
  INPUT_SANITIZED: "INPUT_SANITIZED",
  STREAM_TOKEN: "STREAM_TOKEN",
  STREAM_DONE: "STREAM_DONE",
  GUARDRAIL_BLOCKED: "GUARDRAIL_BLOCKED",
  OUTPUT_BLOCKED: "OUTPUT_BLOCKED",
  STREAM_ERROR: "STREAM_ERROR",
  HYDRATE: "HYDRATE",
  RESET: "RESET",
};

// Pure: the audit sequence number is a function of how many entries exist.
function log(state, kind, detail) {
  const at = `#${state.history.length + 1}`;
  return [...state.history, { at, kind, detail }];
}

// Immutably patch the one request record matching `id`.
function patchRequest(requests, id, patch) {
  return requests.map((r) =>
    r.id === id ? { ...r, ...(typeof patch === "function" ? patch(r) : patch) } : r
  );
}

export function chatReducer(state, action) {
  switch (action.type) {
    case ACTIONS.SEND_START: {
      const userMsg = {
        id: action.userId,
        role: "user",
        content: action.prompt,
        meta: {},
      };
      // Pre-create the assistant bubble so tokens can stream into it.
      const assistantMsg = {
        id: action.assistantId,
        role: "assistant",
        content: "",
        meta: { streaming: true, removed: [] },
      };
      // Open a request record keyed by the assistant message id — that's how the
      // Inspector correlates a request with the bubble it streamed into.
      const request = {
        id: action.assistantId,
        prompt: action.prompt,
        provider: null,
        model: null,
        retries: 0,
        fallbacks: 0,
        completion: null, // 'done' | 'blocked' | 'canary' | 'error' | null
        verdict: null, // input-guardrail verdict (LLM01 + LLM06)
        outputRemoved: [], // LLM02 neutralizations
        // metrics (filled in on STREAM_DONE)
        ttftMs: null,
        durationMs: null,
        streamMs: null,
        tokenCount: null,
        tokensPerSec: null,
        avgChunkSize: null,
      };
      return {
        ...state,
        isLoading: true,
        error: null,
        stage: "validating",
        messages: [...state.messages, userMsg, assistantMsg],
        requests: [...state.requests, request],
        history: log(state, "prompt", { text: action.prompt }),
      };
    }

    case ACTIONS.INPUT_SANITIZED: {
      const { verdict } = action;
      const redactions = verdict.redactions || [];
      // The verdict is stored on the request for EVERY prompt (so the Security
      // tab always has data), but only appended to the audit trail when the
      // guardrail actually did something.
      const meaningful =
        redactions.length > 0 || verdict.injection.action === "SANITIZE";
      const detail = {
        reason: verdict.reason,
        injectionScore: verdict.injection.score,
        // Surface per-hit confidence so the audit trail shows how sure the
        // scanner was, e.g. "CREDIT_CARD·0.832".
        redactions: redactions.map((r) => `${r.type}·${r.confidence}`),
      };

      // LLM06 at rest: when PII/secrets were found, replace the stored + displayed
      // USER message with the redacted text so sensitive data never persists to
      // localStorage or lingers in the DOM. (The gateway already sent only the
      // redacted prompt to the provider.)
      let messages = state.messages;
      if (redactions.length > 0 && action.userId) {
        messages = state.messages.map((m) =>
          m.id === action.userId
            ? {
                ...m,
                content: verdict.sanitizedText,
                meta: { ...m.meta, redacted: redactions.map((r) => r.type) },
              }
            : m
        );
      }

      return {
        ...state,
        messages,
        requests: patchRequest(state.requests, action.id, { verdict }),
        history: meaningful
          ? log(state, "input-guardrail", detail)
          : state.history,
      };
    }

    case ACTIONS.PROVIDER:
      return {
        ...state,
        stage: "routing",
        requests: patchRequest(state.requests, action.id, {
          provider: action.name,
          model: action.model ?? null,
        }),
      };

    case ACTIONS.PROVIDER_RETRY:
      return {
        ...state,
        stage: "routing",
        requests: patchRequest(state.requests, action.id, (r) => ({
          retries: r.retries + 1,
        })),
        history: log(state, "retry", {
          provider: action.provider,
          attempt: action.attempt,
          status: action.status,
          waitMs: action.waitMs,
        }),
      };

    case ACTIONS.PROVIDER_SWITCH:
      return {
        ...state,
        stage: "routing",
        requests: patchRequest(state.requests, action.id, (r) => ({
          fallbacks: r.fallbacks + 1,
          provider: action.to,
        })),
        history: log(state, "failover", {
          from: action.from,
          to: action.to,
          status: action.status,
        }),
      };

    case ACTIONS.STREAM_TOKEN: {
      const messages = state.messages.map((m) =>
        m.id === action.id
          ? {
              ...m,
              content: action.text,
              meta: { ...m.meta, removed: action.removed, raw: action.raw },
            }
          : m
      );
      return { ...state, stage: "streaming", messages };
    }

    case ACTIONS.STREAM_DONE: {
      const messages = state.messages.map((m) =>
        m.id === action.id
          ? {
              ...m,
              meta: {
                ...m.meta,
                streaming: false,
                raw: action.raw ?? m.meta.raw,
              },
            }
          : m
      );
      const metrics = action.metrics || {};
      return {
        ...state,
        isLoading: false,
        stage: "done",
        messages,
        requests: patchRequest(state.requests, action.id, {
          completion: "done",
          provider: action.provider,
          outputRemoved: action.removed || [],
          ttftMs: metrics.ttftMs ?? null,
          durationMs: metrics.durationMs ?? null,
          streamMs: metrics.streamMs ?? null,
          tokenCount: metrics.tokenCount ?? null,
          tokensPerSec: metrics.tokensPerSec ?? null,
          avgChunkSize: metrics.avgChunkSize ?? null,
        }),
        history: log(state, "response", {
          provider: action.provider,
          sanitized: (action.removed || []).length > 0,
          removed: action.removed || [],
        }),
      };
    }

    case ACTIONS.GUARDRAIL_BLOCKED: {
      const { verdict } = action;
      // Replace the empty assistant bubble with a block notice.
      const messages = state.messages.map((m) =>
        m.id === action.id
          ? {
              ...m,
              content: `⛔ Request blocked by guardrail (${verdict.injection.check}): ${verdict.reason}.`,
              meta: { streaming: false, blocked: true, verdict },
            }
          : m
      );
      return {
        ...state,
        isLoading: false,
        stage: "blocked",
        messages,
        requests: patchRequest(state.requests, action.id, {
          completion: "blocked",
          verdict,
        }),
        history: log(state, "blocked", {
          reason: verdict.reason,
          score: verdict.injection.score,
          signals: verdict.injection.signals.map((s) => s.label),
        }),
      };
    }

    case ACTIONS.OUTPUT_BLOCKED: {
      // Egress guardrail tripped (e.g. canary leak). Replace whatever streamed
      // so far with a block notice — we never show a partially-leaked response.
      const messages = state.messages.map((m) =>
        m.id === action.id
          ? {
              ...m,
              content: `⛔ ${action.message}`,
              meta: { streaming: false, blocked: true },
            }
          : m
      );
      return {
        ...state,
        isLoading: false,
        stage: "blocked",
        messages,
        requests: patchRequest(state.requests, action.id, {
          completion: "canary",
          provider: action.provider,
        }),
        history: log(state, "canary", { provider: action.provider }),
      };
    }

    case ACTIONS.STREAM_ERROR: {
      const messages = state.messages.map((m) =>
        m.id === action.id
          ? {
              ...m,
              content: `⚠️ ${action.message}`,
              meta: { streaming: false, error: true },
            }
          : m
      );
      return {
        ...state,
        isLoading: false,
        stage: "error",
        error: action.message,
        messages,
        requests: patchRequest(state.requests, action.id, {
          completion: "error",
        }),
        history: log(state, "error", { message: action.message }),
      };
    }

    case ACTIONS.HYDRATE: {
      // Load a persisted conversation snapshot into the live chat state when the
      // user switches conversations. convId + messages are set atomically here,
      // so the persistence effect always sees a consistent (convId, data) pair.
      const snap = action.snapshot || {};
      return {
        ...initialState,
        convId: snap.id ?? null,
        messages: snap.messages || [],
        history: snap.history || [],
        requests: snap.requests || [],
      };
    }

    case ACTIONS.RESET:
      // "Clear this conversation": wipe the live state but KEEP convId so the
      // persistence effect writes the now-empty conversation back to storage
      // (otherwise the sidebar card would keep showing stale counts).
      return { ...initialState, convId: state.convId };

    default:
      return state;
  }
}
