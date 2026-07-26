"""Backend selection for the sidecar.

USE_REAL_MODELS=true tries the TransformersBackend (Prompt-Guard + Presidio) and
falls back to the heuristic backend if the heavy deps aren't installed — so the
service always starts.
"""

from __future__ import annotations

import logging
import os

from .heuristic import HeuristicBackend

_logger = logging.getLogger("ml_service")


def select_backend():
    if os.getenv("USE_REAL_MODELS", "false").lower() == "true":
        try:
            from .transformers_backend import TransformersBackend

            backend = TransformersBackend()
            _logger.info("ml_service: using TransformersBackend (real models)")
            return backend
        except Exception as exc:  # missing deps / load failure
            _logger.warning("ml_service: real models unavailable (%s); using heuristic", exc)
    return HeuristicBackend()
