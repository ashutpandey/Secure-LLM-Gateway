"""Zero-dependency heuristic backend — the default sidecar model.

This is a deliberate stand-in for the real models (Prompt-Guard / Presidio) so the
full stack runs anywhere with no multi-GB downloads. It is intentionally BROADER
than the main backend's regex detectors — it scores by intent CATEGORY rather than
exact phrasing — so in a shadow-vs-enforce demo it visibly catches paraphrased
injections and emails/phones the regex detectors miss. Swap it for the real
TransformersBackend via USE_REAL_MODELS with no contract change.
"""

from __future__ import annotations

import re

from .base import Entity, InjectionResult, PIIResult

# Intent categories (broad synonyms) — an attacker paraphrase still hits a category
# even when it dodges the regex detector's exact patterns.
_CATEGORIES = {
    "override": ["ignore", "disregard", "overlook", "forget", "skip", "bypass", "override", "set aside"],
    "previous": ["previous", "prior", "earlier", "above", "preceding", "the rules", "your guidance", "instructions"],
    "unrestricted": ["no restrictions", "without restrictions", "without rules", "without limits", "unrestricted", "unfiltered", "no limits", "no rules", "without your usual", "anything i say"],
    "roleplay": ["act as", "pretend", "roleplay", "role play", "you are now", "behave as", "from now on", "respond only as"],
    "exfil": ["system prompt", "your instructions", "hidden rules", "reveal your", "print your configuration", "repeat everything above"],
    "jailbreak": ["jailbreak", "developer mode", "dan mode", "god mode"],
}

_CATEGORY_WEIGHT = {
    "override": 0.35,
    "unrestricted": 0.6,
    "roleplay": 0.35,
    "exfil": 0.5,
    "jailbreak": 0.7,
}

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b")
# Light PERSON heuristic: honorific + capitalized name.
_PERSON = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")


def _combine(weights: list[float]) -> float:
    acc = 1.0
    for w in weights:
        acc *= 1 - w
    return round(1 - acc, 4)


class HeuristicBackend:
    id = "heuristic"

    def score_injection(self, text: str) -> InjectionResult:
        low = (text or "").lower()
        hits = {cat: any(t in low for t in terms) for cat, terms in _CATEGORIES.items()}
        weights: list[float] = []
        labels: list[str] = []
        # "override + previous" together is the classic 'ignore previous' intent.
        if hits["override"] and hits["previous"]:
            weights.append(0.7)
            labels.append("override:previous")
        elif hits["override"]:
            weights.append(_CATEGORY_WEIGHT["override"])
            labels.append("override")
        for cat in ("unrestricted", "roleplay", "exfil", "jailbreak"):
            if hits[cat]:
                weights.append(_CATEGORY_WEIGHT[cat])
                labels.append(cat)
        return {
            "score": _combine(weights),
            "labels": labels,
            "model_id": "heuristic-promptguard",
            "version": "0.1.0",
        }

    def scan_pii(self, text: str) -> PIIResult:
        text = text or ""
        entities: list[Entity] = []
        for typ, pat in (("EMAIL", _EMAIL), ("PHONE", _PHONE), ("PERSON", _PERSON)):
            for m in pat.finditer(text):
                entities.append({"type": typ, "start": m.start(), "end": m.end(), "score": 0.85})
        return {"entities": entities, "model_id": "heuristic-presidio", "version": "0.1.0"}
