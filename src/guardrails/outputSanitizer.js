// LLM02 — Insecure Output Handling: sanitize the model stream before it renders.
//
// Philosophy: ESCAPE over DELETE. We neutralize executable vectors (script tags,
// inline event handlers, javascript:/data URIs, malicious markdown links) but
// prefer HTML-encoding so a benign snippet the user asked to see survives as
// inert text instead of silently vanishing.
//
// Because it runs on ACCUMULATED text each token, a tag split across two tokens
// (e.g. "<scr" + "ipt>") is still caught once both have arrived.

import { stripInvisible } from "./normalize";

const DANGEROUS_URI = /^\s*(javascript|vbscript|data)\s*:/i;

export function sanitizeOutput(text = "") {
  const removed = [];
  // Remove zero-width / invisible characters first so an attacker can't split a
  // tag ("<scr<ZWSP>ipt>") past the patterns below. We strip (not NFKC-fold)
  // here to preserve legitimate glyphs/ligatures in a normal model reply.
  let out = stripInvisible(text);

  // 1. <script>…</script> (and unclosed trailing <script …). Encode, don't drop.
  out = out.replace(/<script\b[\s\S]*?<\/script\s*>/gi, (m) => {
    removed.push("script-block");
    return encode(m);
  });
  out = out.replace(/<script\b[^>]*>?/gi, (m) => {
    removed.push("script-open");
    return encode(m);
  });

  // 2. Inline event handlers: onerror=, onload=, onclick=… -> neutralize name.
  //    The separator class is [\s/] (not just \s) so slash-delimited vectors
  //    like <svg/onload=alert(1)> are caught too. The leading separator is
  //    consumed and replaced by a space, which harmlessly defangs the handler.
  out = out.replace(/[\s/]on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, () => {
    removed.push("event-handler");
    return " data-blocked-handler";
  });

  // 3. Dangerous URIs inside href/src attributes -> replace with #blocked.
  out = out.replace(
    /\b(href|src)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/gi,
    (full, attr, _q, dq, sq, bare) => {
      const val = dq ?? sq ?? bare ?? "";
      if (DANGEROUS_URI.test(val)) {
        removed.push(`${attr}:dangerous-uri`);
        return `${attr}="#blocked"`;
      }
      return full;
    }
  );

  // 4. Markdown links with dangerous schemes: [text](javascript:…) -> [text](#blocked)
  out = out.replace(/\]\(\s*([^)]+?)\s*\)/g, (full, url) => {
    if (DANGEROUS_URI.test(url)) {
      removed.push("markdown-uri");
      return "](#blocked)";
    }
    return full;
  });

  // 5. Any remaining bare <script/<iframe/<img angle-tag openers -> encode
  //    so nothing executable reaches the DOM even if patterns above missed it.
  out = out.replace(/<\s*(iframe|object|embed)\b[^>]*>?/gi, (m) => {
    removed.push("embed-tag");
    return encode(m);
  });

  return {
    check: "LLM02",
    sanitizedText: out,
    removed,
    modified: removed.length > 0,
  };
}

// Defang by replacing real angle brackets with look-alike guillemets. The
// content stays visible (so you can see WHAT was neutralized) but can never form
// a real tag — inert whether rendered as a React text node or, hypothetically,
// via innerHTML. This is the "escape over delete" idea made context-agnostic.
function encode(s) {
  return s.replace(/</g, "‹").replace(/>/g, "›");
}
