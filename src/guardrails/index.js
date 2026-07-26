// Client-side guardrail surface — RENDER-TIME ONLY.
//
// Input guardrails (LLM01/LLM06) and provider routing are ENFORCED on the
// backend (the single source of truth). The only guardrail the client legitimately
// runs is LLM02 output sanitization at the render boundary — parsing the model
// stream before it reaches the DOM — which happens in ChatContext's commit.
export { sanitizeOutput } from "./outputSanitizer";
