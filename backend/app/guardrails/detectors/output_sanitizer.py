"""LLM02 — output handling (server-side defense-in-depth).

Port of the frontend `outputSanitizer.js`. The client still sanitizes at the
render boundary (that's where XSS is actually prevented); this server-side pass
is defense-in-depth and produces the audit `removed[]`. Escape-over-delete: we
defang executable vectors while keeping benign content readable.
"""

from __future__ import annotations

import re
import time

from ..base import Action, Context, FailMode, Signal, Stage
from ..normalize import strip_invisible
from ..registry import register_detector

_DANGEROUS_URI = re.compile(r"^\s*(javascript|vbscript|data)\s*:", re.I)
_SCRIPT_BLOCK = re.compile(r"<script\b[\s\S]*?</script\s*>", re.I)
_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>?", re.I)
_EVENT_HANDLER = re.compile(r"[\s/]on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_ATTR_URI = re.compile(r"\b(href|src)\s*=\s*(\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
_MD_URI = re.compile(r"\]\(\s*([^)]+?)\s*\)")
_EMBED = re.compile(r"<\s*(iframe|object|embed)\b[^>]*>?", re.I)


def _encode(s: str) -> str:
    return s.replace("<", "‹").replace(">", "›")


@register_detector
class OutputSanitizer:
    id = "output-sanitizer"
    stage = Stage.OUTPUT
    check = "LLM02"
    fail_mode = FailMode.CLOSED
    contract_version = 1
    model_id = "regex-sanitizer"
    version = "1.1.0"
    cost = 1
    cacheable = True

    async def analyze(self, text: str, ctx: Context) -> Signal:
        t0 = time.perf_counter()
        removed: list[str] = []
        out = strip_invisible(text)

        def _sub(pat, repl_label, replacement):
            nonlocal out

            def _r(m):
                removed.append(repl_label)
                return replacement(m) if callable(replacement) else replacement

            out = pat.sub(_r, out)

        _sub(_SCRIPT_BLOCK, "script-block", lambda m: _encode(m.group()))
        _sub(_SCRIPT_OPEN, "script-open", lambda m: _encode(m.group()))
        _sub(_EVENT_HANDLER, "event-handler", " data-blocked-handler")

        def _attr(m):
            attr = m.group(1)
            val = m.group(3) or m.group(4) or m.group(5) or ""
            if _DANGEROUS_URI.search(val):
                removed.append(f"{attr}:dangerous-uri")
                return f'{attr}="#blocked"'
            return m.group(0)

        out = _ATTR_URI.sub(_attr, out)

        def _md(m):
            if _DANGEROUS_URI.search(m.group(1)):
                removed.append("markdown-uri")
                return "](#blocked)"
            return m.group(0)

        out = _MD_URI.sub(_md, out)
        _sub(_EMBED, "embed-tag", lambda m: _encode(m.group()))

        modified = len(removed) > 0
        return Signal(
            detector_id=self.id,
            check=self.check,
            score=1.0 if modified else 0.0,
            action_hint=Action.SANITIZE if modified else Action.ALLOW,
            labels=removed,
            transformed_text=out if modified else None,
            model_id=self.model_id,
            version=self.version,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
