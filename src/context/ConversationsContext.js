// Conversation list + activeId, persisted to localStorage.
//
// Split into two contexts so consumers subscribe to the minimum:
//   • ConvStateContext   — { list, activeId }. Changes only on new/select/
//                          delete/rename and once-per-request persistence.
//                          NEVER changes while tokens stream (persistence is
//                          gated on the request settling), so the sidebar stays
//                          quiet during streaming.
//   • ConvActionsContext — stable callbacks: new/select/delete/rename +
//                          getSnapshot / persistActive (the bridge to the live
//                          ChatProvider). Identity never changes.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
// NOTE: the reducer + snapshot helpers are inlined here (rather than imported
// from ./conversationsReducer) so this provider is fully self-contained and
// can't break if that module is stale/out of sync in the sandbox.

const STORE_KEY = "console.v1";

// Storage caps — localStorage is ~5 MB and a failed write is silently swallowed,
// so we bound growth rather than let a long session eventually exceed quota.
const MAX_CONVERSATIONS = 40; // keep the most-recent N conversations
const MAX_MESSAGES = 100; // per conversation
const MAX_HISTORY = 200; // audit entries per conversation
const MAX_REQUESTS = 100; // request records per conversation
const MAX_RAW_LEN = 2000; // trim the (demo-only) raw model output before storage

const CONV = {
  HYDRATE_STORE: "HYDRATE_STORE",
  NEW: "NEW",
  SELECT: "SELECT",
  DELETE: "DELETE",
  RENAME: "RENAME",
  PERSIST: "PERSIST",
};

function makeSnapshot(id, createdAt) {
  return {
    id,
    title: "",
    createdAt,
    updatedAt: createdAt,
    messages: [],
    history: [],
    requests: [],
  };
}

function deriveTitle(messages = []) {
  const u = messages.find((m) => m.role === "user");
  if (!u) return "";
  return u.content.replace(/\s+/g, " ").trim().slice(0, 40) || "";
}

// Keep only the last `n` items of an array (returns the same ref if already
// within bounds, so unchanged conversations don't churn identity).
function tail(arr = [], n) {
  return arr.length > n ? arr.slice(arr.length - n) : arr;
}

// Cap message count and trim the oversized (demo-only) raw payload before it's
// persisted — the raw model output is only needed for the live before/after
// reveal, not at rest.
function capMessages(messages = []) {
  const capped = tail(messages, MAX_MESSAGES);
  let changed = capped !== messages;
  const trimmed = capped.map((m) => {
    const raw = m.meta?.raw;
    if (typeof raw === "string" && raw.length > MAX_RAW_LEN) {
      changed = true;
      return {
        ...m,
        meta: { ...m.meta, raw: raw.slice(0, MAX_RAW_LEN) + "…" },
      };
    }
    return m;
  });
  return changed ? trimmed : capped;
}

function conversationsReducer(state, action) {
  switch (action.type) {
    case CONV.HYDRATE_STORE:
      return action.store;

    case CONV.NEW: {
      const s = action.snapshot;
      let order = [s.id, ...state.order];
      let byId = { ...state.byId, [s.id]: s };
      // Evict the oldest conversations past the cap so the store stays bounded.
      if (order.length > MAX_CONVERSATIONS) {
        const dropped = order.slice(MAX_CONVERSATIONS);
        order = order.slice(0, MAX_CONVERSATIONS);
        for (const id of dropped) delete byId[id];
      }
      return { order, byId, activeId: s.id };
    }

    case CONV.SELECT:
      return state.byId[action.id] ? { ...state, activeId: action.id } : state;

    case CONV.DELETE: {
      if (!state.byId[action.id]) return state;
      const order = state.order.filter((i) => i !== action.id);
      const byId = { ...state.byId };
      delete byId[action.id];
      let activeId = state.activeId;
      if (activeId === action.id) {
        if (order.length) {
          activeId = order[0];
        } else {
          // Deleted the last one — seed a fresh empty conversation.
          const s = action.fallback;
          order.push(s.id);
          byId[s.id] = s;
          activeId = s.id;
        }
      }
      return { order, byId, activeId };
    }

    case CONV.RENAME: {
      const s = state.byId[action.id];
      if (!s) return state;
      return {
        ...state,
        byId: { ...state.byId, [action.id]: { ...s, title: action.title } },
      };
    }

    case CONV.PERSIST: {
      const s = state.byId[action.id];
      if (!s) return state;
      const patch = action.patch || {};
      const title = s.title || deriveTitle(patch.messages ?? s.messages);
      // Bound every stored array and trim the demo-only raw payload so a long
      // conversation can't blow the localStorage quota.
      const messages = capMessages(patch.messages ?? s.messages);
      const history = tail(patch.history ?? s.history, MAX_HISTORY);
      const requests = tail(patch.requests ?? s.requests, MAX_REQUESTS);
      const merged = {
        ...s,
        ...patch,
        messages,
        history,
        requests,
        title,
        updatedAt: action.updatedAt,
      };
      return { ...state, byId: { ...state.byId, [action.id]: merged } };
    }

    default:
      return state;
  }
}

// Derived stats for a conversation card (computed, never stored).
function conversationStats(snapshot) {
  const messages = snapshot.messages || [];
  const history = snapshot.history || [];
  const requests = snapshot.requests || [];

  const messageCount = messages.filter(
    (m) => m.role === "user" || m.role === "assistant"
  ).length;

  const threatCount = history.filter(
    (h) =>
      h.kind === "blocked" ||
      h.kind === "canary" ||
      (h.kind === "input-guardrail" && (h.detail?.redactions?.length || 0) > 0)
  ).length;

  const latencies = requests
    .map((r) => r.durationMs)
    .filter((n) => typeof n === "number");
  const avgLatencyMs = latencies.length
    ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
    : null;

  const lastProvider =
    [...requests].reverse().find((r) => r.provider)?.provider || null;

  return { messageCount, threatCount, avgLatencyMs, lastProvider };
}

const ConvStateContext = createContext(null);
const ConvActionsContext = createContext(null);

const nowMs = () => Date.now();
function genId() {
  try {
    if (typeof crypto !== "undefined" && crypto.randomUUID)
      return `c-${crypto.randomUUID()}`;
  } catch {}
  return `c-${nowMs()}-${Math.floor(Math.random() * 1e6)}`;
}

function loadInitial() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if (p && Array.isArray(p.order) && p.order.length && p.byId && p.activeId)
        return p;
    }
  } catch {}
  const id = genId();
  const s = makeSnapshot(id, nowMs());
  return { order: [id], byId: { [id]: s }, activeId: id };
}

export function ConversationsProvider({ children }) {
  const [state, dispatch] = useReducer(
    conversationsReducer,
    undefined,
    loadInitial
  );

  // Latest byId, read by getSnapshot without making it depend on renders.
  const byIdRef = useRef(state.byId);
  byIdRef.current = state.byId;

  // Persist the whole store on every change (debounced to the next frame so a
  // burst of updates writes once). Quota-safe: if the write is rejected
  // (QuotaExceededError), progressively drop the oldest conversations and retry
  // rather than losing the whole store to a silent failure.
  useEffect(() => {
    let raf = 0;
    raf = requestAnimationFrame(() => {
      const writeReduced = (keep) => {
        const order = state.order.slice(0, keep);
        const byId = {};
        for (const id of order) if (state.byId[id]) byId[id] = state.byId[id];
        localStorage.setItem(
          STORE_KEY,
          JSON.stringify({ order, byId, activeId: state.activeId })
        );
      };
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify(state));
      } catch {
        for (const keep of [10, 3, 1]) {
          try {
            writeReduced(keep);
            return;
          } catch {
            /* try an even smaller store */
          }
        }
      }
    });
    return () => cancelAnimationFrame(raf);
  }, [state]);

  const newConversation = useCallback(() => {
    dispatch({ type: CONV.NEW, snapshot: makeSnapshot(genId(), nowMs()) });
  }, []);
  const selectConversation = useCallback(
    (id) => dispatch({ type: CONV.SELECT, id }),
    []
  );
  const deleteConversation = useCallback(
    (id) =>
      dispatch({
        type: CONV.DELETE,
        id,
        fallback: makeSnapshot(genId(), nowMs()),
      }),
    []
  );
  const renameConversation = useCallback(
    (id, title) => dispatch({ type: CONV.RENAME, id, title }),
    []
  );
  const getSnapshot = useCallback(
    (id) => byIdRef.current[id] || makeSnapshot(id, nowMs()),
    []
  );
  // Called by ChatProvider when the active conversation settles (not per token).
  const persistActive = useCallback(
    (id, patch) =>
      dispatch({ type: CONV.PERSIST, id, patch, updatedAt: nowMs() }),
    []
  );

  const actions = useMemo(
    () => ({
      newConversation,
      selectConversation,
      deleteConversation,
      renameConversation,
      getSnapshot,
      persistActive,
    }),
    [
      newConversation,
      selectConversation,
      deleteConversation,
      renameConversation,
      getSnapshot,
      persistActive,
    ]
  );

  // Lightweight list projection for the sidebar (no raw message bodies).
  const list = useMemo(
    () =>
      state.order
        .map((id) => state.byId[id])
        .filter(Boolean)
        .map((s) => ({
          id: s.id,
          title: s.title,
          createdAt: s.createdAt,
          updatedAt: s.updatedAt,
          stats: conversationStats(s),
        })),
    [state.order, state.byId]
  );

  const value = useMemo(
    () => ({ list, activeId: state.activeId }),
    [list, state.activeId]
  );

  return (
    <ConvActionsContext.Provider value={actions}>
      <ConvStateContext.Provider value={value}>
        {children}
      </ConvStateContext.Provider>
    </ConvActionsContext.Provider>
  );
}

export function useConversations() {
  const ctx = useContext(ConvStateContext);
  if (ctx === null)
    throw new Error(
      "useConversations must be used within <ConversationsProvider>"
    );
  return ctx;
}

export function useConversationActions() {
  const ctx = useContext(ConvActionsContext);
  if (ctx === null)
    throw new Error(
      "useConversationActions must be used within <ConversationsProvider>"
    );
  return ctx;
}
