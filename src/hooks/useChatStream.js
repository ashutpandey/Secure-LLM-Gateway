// Thin convenience hook for components that send prompts.
//
// The streaming/reader loop now lives in ChatProvider (so `send` is stable and
// rAF-coalesces tokens). This hook just composes the two slices a sender needs:
//   • send      — from the STABLE actions context (never triggers a re-render)
//   • isLoading — from the status context (flips only twice per request)
// Because it does NOT read the full state, Composer/SecurityPanel stop
// re-rendering on every streamed token.

import { useChatActions, useChatStatus } from "../context/ChatContext";

export function useChatStream() {
  const { send } = useChatActions();
  const { isLoading } = useChatStatus();
  return { send, isLoading };
}
