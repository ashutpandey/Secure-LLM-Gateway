import "./styles.css";
import { UIProvider, useUIState } from "./context/UIContext";
import { ConversationsProvider } from "./context/ConversationsContext";
import { ChatProvider } from "./context/ChatContext";

import Header from "./components/layout/Header";
import Sidebar from "./components/layout/Sidebar";
import Footer from "./components/layout/Footer";
import ChatWorkspace from "./components/chat/ChatWorkspace";
import Inspector from "./components/inspector/Inspector";
import Toaster from "./components/shared/Toaster";
import SandboxPanel from "./components/sandbox/SandboxPanel";
import ErrorBoundary from "./components/shared/ErrorBoundary";

// The layout shell reads only the two visibility flags, so toggling a panel
// re-renders the shell frame — not the chat, inspector, or sidebar internals
// (those subscribe to their own contexts).
function AppShell() {
  const { sidebarOpen, inspectorOpen } = useUIState();

  const cls = [
    "console-shell",
    sidebarOpen ? "with-sidebar" : "no-sidebar",
    inspectorOpen ? "with-inspector" : "no-inspector",
  ].join(" ");

  return (
    <div className={cls}>
      <Header />
      {sidebarOpen && <Sidebar />}
      <ChatWorkspace />
      {inspectorOpen && <Inspector />}
      <Footer />
      <SandboxPanel />
      <Toaster />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <UIProvider>
        <ConversationsProvider>
          <ChatProvider>
            <AppShell />
          </ChatProvider>
        </ConversationsProvider>
      </UIProvider>
    </ErrorBoundary>
  );
}
