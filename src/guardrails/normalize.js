// Text normalization — the FIRST step every guardrail runs before pattern
// matching. Attackers defeat naive regex filters by breaking up trigger words
// with characters that are invisible or look identical to ASCII:
//
//   • Zero-width joiners/spaces:   "ig<U+200B>nore previous instructions"
//   • Fullwidth / homoglyph forms: fullwidth "i" -> "i"
//   • Bidi overrides & BOM:        used to reorder or hide text
//   • Soft hyphen (U+00AD):        renders invisibly, splits words
//
// None of these survive Unicode NFKC folding + invisible-character stripping,
// so we canonicalize once here and let the detectors match plain ASCII. This is
// a recall win with essentially no false-positive cost: NFKC is a no-op on
// ordinary text, and legitimate content almost never carries zero-width control
// characters.

// Invisible / format code points that render to nothing but can split a trigger
// token. Built from numeric code points so this source file stays 100% ASCII
// (embedding the literal characters would make the file unreadable and easy to
// corrupt silently).
//   00AD soft hyphen · 200B-200F zero-width + bidi marks · 202A-202E bidi embeds
//   2060-2064 word-joiner/invisible math ops · 206A-206F deprecated format ·
//   FEFF BOM / zero-width no-break space
const INVISIBLE_SINGLES = [0x00ad, 0xfeff];
const INVISIBLE_RANGES = [
  [0x200b, 0x200f],
  [0x202a, 0x202e],
  [0x2060, 0x2064],
  [0x206a, 0x206f],
];

const hex = (c) => "\\u" + c.toString(16).padStart(4, "0");
const INVISIBLE = new RegExp(
  "[" +
    INVISIBLE_SINGLES.map(hex).join("") +
    INVISIBLE_RANGES.map(([a, b]) => `${hex(a)}-${hex(b)}`).join("") +
    "]",
  "g"
);

// Strip characters that render to nothing but break up patterns. Kept separate
// from full NFKC so callers that must preserve legitimate glyphs (e.g. model
// OUTPUT, where a "fi" ligature folding would be undesirable) can defang without
// folding.
export function stripInvisible(text = "") {
  const s = typeof text === "string" ? text : String(text ?? "");
  return s.replace(INVISIBLE, "");
}

// Canonical form: NFKC folds compatibility/fullwidth/homoglyph forms to their
// ASCII equivalents, then invisibles are removed. NFKC is idempotent, so
// re-normalizing already-normalized text is safe.
export function normalizeForAnalysis(text = "") {
  let s = typeof text === "string" ? text : String(text ?? "");
  try {
    s = s.normalize("NFKC");
  } catch {
    // Extremely old runtimes without String.prototype.normalize — fall back to
    // invisible-stripping alone rather than throwing inside a guardrail.
  }
  return stripInvisible(s);
}
