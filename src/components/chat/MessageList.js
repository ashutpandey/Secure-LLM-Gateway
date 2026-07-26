import React, { useEffect, useRef } from "react";
import { useChatState } from "../../context/ChatContext";
import { useChatStream } from "../../hooks/useChatStream";
import MessageBubble from "./MessageBubble";
import { Sparkles } from "../../icons";

const SUGGESTIONS = [
  "Summarize the key risks in the OWASP LLM Top 10.",
  "Draft a friendly onboarding message for a new teammate.",
  "Explain token streaming to a product manager.",
];

function EmptyState() {
  const { send, isLoading } = useChatStream();
  return (
    <div className="chat-empty">
      <div className="empty-mark">
        <Sparkles size={22} strokeWidth={1.5} />
      </div>
      <h2>Start a secure conversation</h2>
      <p className="muted">
        Every prompt runs through input guardrails, streams token-by-token, and
        is sanitized before it reaches the screen.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="suggestion"
            disabled={isLoading}
            onClick={() => send(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function MessageList() {
  const state = useChatState();
  const endRef = useRef(null);

  // Jump instantly while tokens stream (smooth-scrolling every frame fights
  // itself and looks janky); use a smooth glide only when the stream settles.
  useEffect(() => {
    endRef.current?.scrollIntoView({
      behavior: state.isLoading ? "auto" : "smooth",
    });
  }, [state.messages, state.isLoading]);

  if (state.messages.length === 0) return <EmptyState />;

  return (
    <div className="messages">
      {state.messages.map((m) => (
        <MessageBubble key={m.id} msg={m} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
