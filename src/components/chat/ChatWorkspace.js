import React from "react";
import { useConversations } from "../../context/ConversationsContext";
import { useChatActions } from "../../context/ChatContext";
import { ACTIONS } from "../../context/chatReducer";
import MessageList from "./MessageList";
import Composer from "./Composer";
import StreamStatusPill from "./StreamStatusPill";
import { Trash2 } from "../../icons";

export default function ChatWorkspace() {
  const { list, activeId } = useConversations();
  const { dispatch } = useChatActions();
  const active = list.find((c) => c.id === activeId);
  const title = active?.title || "New conversation";

  return (
    <main className="console-main">
      <div className="workspace-bar">
        <div className="workspace-title" title={title}>
          {title}
        </div>
        <button
          className="ghost-btn sm"
          onClick={() => dispatch({ type: ACTIONS.RESET })}
          title="Clear this conversation"
        >
          <Trash2 size={14} strokeWidth={1.75} />
          <span>Clear</span>
        </button>
      </div>

      <div className="workspace-scroll">
        <MessageList />
      </div>

      <div className="workspace-foot">
        <StreamStatusPill />
        <Composer />
      </div>
    </main>
  );
}
