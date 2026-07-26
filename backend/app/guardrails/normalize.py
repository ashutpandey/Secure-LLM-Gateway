"""Text normalization — the first step every detector runs.

Mirrors the frontend `normalize.js`: NFKC folding + invisible/zero-width
stripping, so homoglyph ("ｉgnore") and zero-width ("ig<ZWSP>nore") evasions fold
to plain ASCII before any pattern matches. Kept in sync with the client so the
optimistic UX pre-check and the authoritative server check agree.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible / format code points that render to nothing but split trigger tokens.
# Built from code points so this source file stays pure ASCII.
#   00AD soft hyphen · 200B-200F zero-width + bidi · 202A-202E bidi embeds
#   2060-2064 word-joiner/invisible ops · 206A-206F deprecated format · FEFF BOM
_INVISIBLE_SINGLES = [0x00AD, 0xFEFF]
_INVISIBLE_RANGES = [(0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x206A, 0x206F)]
_INVISIBLE = re.compile(
    "["
    + "".join(chr(c) for c in _INVISIBLE_SINGLES)
    + "".join(f"{chr(a)}-{chr(b)}" for a, b in _INVISIBLE_RANGES)
    + "]"
)


def strip_invisible(text: str) -> str:
    """Remove zero-width / invisible characters (preserves visible glyphs)."""
    return _INVISIBLE.sub("", text or "")


def normalize_for_analysis(text: str) -> str:
    """Canonical form for INPUT analysis: NFKC fold, then strip invisibles.

    NFKC is idempotent, so repeated normalization down the pipeline is safe.
    """
    if not text:
        return ""
    return strip_invisible(unicodedata.normalize("NFKC", text))
