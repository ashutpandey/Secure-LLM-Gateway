import React, { useMemo, useState } from "react";
import {
  useConversations,
  useConversationActions,
} from "../../context/ConversationsContext";
import HistoryCard from "./HistoryCard";
import { Plus, Search } from "../../icons";

export default function ConversationList() {
  const { list, activeId } = useConversations();
  const { newConversation, selectConversation, deleteConversation } =
    useConversationActions();
  const [query, setQuery] = useState("");

  // Stamp "now" once per render so every card's relative time is consistent.
  const now = Date.now();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((c) => (c.title || "").toLowerCase().includes(q));
  }, [list, query]);

  return (
    <div className="conv-list">
      <button className="new-conv-btn" onClick={newConversation}>
        <Plus size={16} strokeWidth={2} />
        <span>New conversation</span>
      </button>

      <div className="conv-search">
        <Search size={14} strokeWidth={1.75} />
        <input
          value={query}
          placeholder="Search"
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="conv-scroll">
        {filtered.length === 0 ? (
          <div className="conv-empty muted">
            {query ? "No matches." : "No conversations yet."}
          </div>
        ) : (
          filtered.map((c) => (
            <HistoryCard
              key={c.id}
              conv={c}
              active={c.id === activeId}
              onSelect={selectConversation}
              onDelete={deleteConversation}
              now={now}
            />
          ))
        )}
      </div>
    </div>
  );
}
