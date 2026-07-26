// Client-side guardrail tests — RENDER-TIME ONLY.
// Input guardrails + red-team now live on the backend (see backend/tests). The
// client keeps just LLM02 output sanitization at the render boundary, tested here.

import { sanitizeOutput } from "../outputSanitizer";
import { normalizeForAnalysis, stripInvisible } from "../normalize";

const ZWSP = String.fromCharCode(0x200b);

describe("normalize", () => {
  test("strips zero-width / invisible characters", () => {
    expect(stripInvisible(`sc${ZWSP}ript`)).toBe("script");
  });
  test("NFKC folds fullwidth homoglyphs to ASCII", () => {
    expect(normalizeForAnalysis("ｓｃｒｉｐｔ")).toBe("script");
  });
});

describe("LLM02 output sanitizer (render boundary)", () => {
  test("neutralizes script + event handler + javascript: link", () => {
    const { sanitizedText, removed } = sanitizeOutput(
      "<script>steal()</script> <img src=x onerror=alert(1)> [x](javascript:alert(1))"
    );
    expect(/<script/i.test(sanitizedText)).toBe(false);
    expect(/onerror\s*=/i.test(sanitizedText)).toBe(false);
    expect(/javascript:/i.test(sanitizedText)).toBe(false);
    expect(removed.length).toBeGreaterThan(0);
  });

  test("catches slash-delimited svg handler", () => {
    const { removed } = sanitizeOutput("<svg/onload=alert(1)>");
    expect(removed).toContain("event-handler");
  });

  test("leaves benign prose and code untouched", () => {
    const { sanitizedText, removed } = sanitizeOutput(
      "Use the map() function; 3 > 2 is true."
    );
    expect(removed.length).toBe(0);
    expect(sanitizedText).toContain("map()");
  });
});
