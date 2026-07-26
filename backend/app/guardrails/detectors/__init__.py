"""Importing this package registers all built-in detectors (import side-effect).

To add a detector: create a module here, decorate the class with
`@register_detector`, and import it below. Nothing else in the pipeline changes.
"""

from . import (  # noqa: F401
    canary,
    known_attacks,
    multiturn,
    output_sanitizer,
    pii,
    presidio_pii,
    promptguard,
    regex_injection,
)

__all__ = [
    "canary",
    "known_attacks",
    "multiturn",
    "output_sanitizer",
    "pii",
    "presidio_pii",
    "promptguard",
    "regex_injection",
]
