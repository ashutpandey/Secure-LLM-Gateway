import React from "react";
import ConversationList from "../history/ConversationList";

export default function Sidebar() {
  return (
    <aside className="console-sidebar">
      <ConversationList />
    </aside>
  );
}
