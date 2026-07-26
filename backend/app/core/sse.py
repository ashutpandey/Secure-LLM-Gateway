"""Server-Sent Events formatting.

The event contract matches the frontend's existing stream reader, so swapping the
client from its in-process mock gateway to this endpoint is a one-file change.
"""

from __future__ import annotations

import json
from typing import Any


def sse_event(data: dict[str, Any]) -> str:
    """One SSE frame. The client parses `data:` as JSON and switches on `type`."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
