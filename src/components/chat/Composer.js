import React, { useRef, useState } from "react";
import { useChatStream } from "../../hooks/useChatStream";
import { Send } from "../../icons";

export default function Composer() {
  const { send, isLoading } = useChatStream();
  const [text, setText] = useState("");
  const taRef = useRef(null);

  const submit = (e) => {
    e?.preventDefault();
    const prompt = text.trim();
    if (!prompt || isLoading) return;
    setText("");
    // Reset the textarea height after clearing.
    if (taRef.current) taRef.current.style.height = "auto";
    send(prompt);
  };

  // Enter sends; Shift+Enter inserts a newline.
  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  // Auto-grow the textarea up to a cap.
  const onInput = (e) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        ref={taRef}
        className="composer-input"
        value={text}
        rows={1}
        placeholder="Send a message…  (Enter to send, Shift+Enter for newline)"
        onChange={onInput}
        onKeyDown={onKeyDown}
        disabled={isLoading}
      />
      <button
        className="composer-send"
        type="submit"
        disabled={isLoading || !text.trim()}
        title="Send"
        aria-label="Send"
      >
        <Send size={16} strokeWidth={2} />
      </button>
    </form>
  );
}
