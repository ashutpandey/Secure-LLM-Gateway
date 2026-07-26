// Small presentation helpers shared by the Inspector tiles and cards.

export function ms(v) {
  if (v == null || Number.isNaN(v)) return "—";
  if (v < 1) return "<1 ms";
  if (v < 1000) return `${Math.round(v)} ms`;
  return `${(v / 1000).toFixed(2)} s`;
}

export function num(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

export function rate(v) {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)} tok/s`;
}

// "2m ago" / "3h ago" — relativeMs is (now - then).
export function ago(then, now) {
  if (!then) return "";
  const d = Math.max(0, (now ?? Date.now()) - then);
  const s = Math.floor(d / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  return `${days}d ago`;
}

// Friendly provider label from the internal id.
export function providerLabel(name) {
  if (!name) return "—";
  if (name.startsWith("gpt")) return "GPT";
  if (name.startsWith("claude")) return "Claude";
  return name;
}
