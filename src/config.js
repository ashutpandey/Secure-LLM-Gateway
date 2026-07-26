// Central build-time flags for the frontend.
//
// DEMO_MODE — when on (default), the UI keeps the "raw vs neutralized" reveal so
// the security story is visible during a demo. When OFF (a production build via
// REACT_APP_DEMO_MODE=false), the raw, un-sanitized model output is neither
// shown nor persisted — LLM02 still neutralizes it before render, but we never
// store the dangerous original at rest.
export const DEMO_MODE =
  String(process.env.REACT_APP_DEMO_MODE ?? "true").toLowerCase() !== "false";

// API_BASE — when set (e.g. http://localhost:8000 via docker-compose), the app
// talks to the FastAPI backend: chat streams over SSE and the control-plane
// panels manage the live registry/policy. When empty, the app runs fully
// self-contained on the in-browser mock gateway (codesandbox, no backend).
export const API_BASE = String(process.env.REACT_APP_API_BASE ?? "").replace(
  /\/+$/,
  ""
);
export const BACKEND_ENABLED = API_BASE.length > 0;
