// UI-chrome state: theme, which Inspector tab is open, sidebar/inspector
// visibility, and transient toast notifications.
//
// Kept separate from chat/conversation data so toggling a panel or firing a
// toast never touches the streaming state (and vice-versa). Native Context +
// useState/useReducer only.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const THEME_KEY = "console.theme";
const UIStateContext = createContext(null);
const UIActionsContext = createContext(null);

function loadTheme() {
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t === "light" || t === "dark") return t;
  } catch {}
  return "dark"; // dark by default, per the design plan
}

let toastSeq = 0;

export function UIProvider({ children }) {
  const [theme, setTheme] = useState(loadTheme);
  const [inspectorTab, setInspectorTab] = useState("audit");
  const [inspectId, setInspectId] = useState(null); // which request the Inspector shows (null = latest)
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [sandboxOpen, setSandboxOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  // Reflect the theme onto <html data-theme> and persist it.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {}
  }, [theme]);

  const dismissToast = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback((toast) => {
    const id = ++toastSeq;
    const entry = {
      id,
      tone: toast.tone || "info", // info | success | warn | danger
      title: toast.title || "",
      message: toast.message || "",
    };
    setToasts((list) => [...list, entry]);
    return id;
  }, []);

  const toggleTheme = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    []
  );
  const toggleSidebar = useCallback(() => setSidebarOpen((v) => !v), []);
  const toggleInspector = useCallback(() => setInspectorOpen((v) => !v), []);
  const toggleSandbox = useCallback(() => setSandboxOpen((v) => !v), []);

  // Open the inspector on a specific tab (used by a message's "Inspect" action).
  const openInspectorTab = useCallback((tab) => {
    setInspectorTab(tab);
    setInspectorOpen(true);
  }, []);

  // Point the Inspector at a specific request (a specific assistant reply) and,
  // optionally, jump to a tab. Passing null falls back to the latest request.
  const inspectRequest = useCallback((id, tab) => {
    setInspectId(id ?? null);
    if (tab) setInspectorTab(tab);
    setInspectorOpen(true);
  }, []);

  const state = useMemo(
    () => ({
      theme,
      inspectorTab,
      inspectId,
      sidebarOpen,
      inspectorOpen,
      sandboxOpen,
      toasts,
    }),
    [
      theme,
      inspectorTab,
      inspectId,
      sidebarOpen,
      inspectorOpen,
      sandboxOpen,
      toasts,
    ]
  );

  const actions = useMemo(
    () => ({
      toggleTheme,
      setInspectorTab,
      openInspectorTab,
      inspectRequest,
      toggleSidebar,
      toggleInspector,
      toggleSandbox,
      pushToast,
      dismissToast,
    }),
    [
      toggleTheme,
      openInspectorTab,
      inspectRequest,
      toggleSidebar,
      toggleInspector,
      toggleSandbox,
      pushToast,
      dismissToast,
    ]
  );

  return (
    <UIActionsContext.Provider value={actions}>
      <UIStateContext.Provider value={state}>
        {children}
      </UIStateContext.Provider>
    </UIActionsContext.Provider>
  );
}

export function useUIState() {
  const ctx = useContext(UIStateContext);
  if (ctx === null)
    throw new Error("useUIState must be used within <UIProvider>");
  return ctx;
}

export function useUIActions() {
  const ctx = useContext(UIActionsContext);
  if (ctx === null)
    throw new Error("useUIActions must be used within <UIProvider>");
  return ctx;
}
