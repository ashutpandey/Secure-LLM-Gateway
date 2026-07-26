"""Real ML backend — Meta Prompt-Guard (injection) + Microsoft Presidio (PII).

Optional: needs the heavy deps in requirements-ml.txt (transformers, torch,
presidio-analyzer, spacy). Selected via USE_REAL_MODELS=true. It implements the
SAME ModelBackend contract as HeuristicBackend, so nothing else in the system
changes — this file IS the "swap the model" seam made concrete.

Each model is loaded lazily on first use; if a library or weight is missing, the
call raises and the sidecar logs it (the main backend then fails-open per the
detector's fail_mode, so a model outage degrades to regex, never an outage).
"""

from __future__ import annotations

from .base import Entity, InjectionResult, PIIResult

_PROMPT_GUARD_MODEL = "meta-llama/Prompt-Guard-86M"


class TransformersBackend:
    id = "transformers"

    def __init__(self) -> None:
        # Fail fast at selection time if the heavy deps aren't installed, so
        # select_backend() can cleanly fall back to the heuristic backend rather
        # than starting up and erroring on the first request.
        import torch  # noqa: F401
        import transformers  # noqa: F401

        self._pg = None  # (tokenizer, model)
        self._presidio = None

    # --- Prompt-Guard ----------------------------------------------------
    def _load_prompt_guard(self):
        if self._pg is None:
            import torch  # noqa: F401
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )

            tok = AutoTokenizer.from_pretrained(_PROMPT_GUARD_MODEL)
            model = AutoModelForSequenceClassification.from_pretrained(_PROMPT_GUARD_MODEL)
            model.eval()
            self._pg = (tok, model)
        return self._pg

    def score_injection(self, text: str) -> InjectionResult:
        import torch

        tok, model = self._load_prompt_guard()
        inputs = tok(text or "", return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)[0]
        # Prompt-Guard labels: 0=BENIGN, 1=INJECTION, 2=JAILBREAK. The score is the
        # probability the input is adversarial (non-benign).
        id2label = {int(k): v for k, v in model.config.id2label.items()}
        benign_idx = next((i for i, l in id2label.items() if l.upper().startswith("BENIGN")), 0)
        score = float(1.0 - probs[benign_idx].item())
        labels = [id2label[int(probs.argmax().item())]]
        return {
            "score": round(score, 4),
            "labels": labels,
            "model_id": _PROMPT_GUARD_MODEL,
            "version": "hf",
        }

    # --- Presidio --------------------------------------------------------
    def _load_presidio(self):
        if self._presidio is None:
            from presidio_analyzer import AnalyzerEngine

            self._presidio = AnalyzerEngine()
        return self._presidio

    def scan_pii(self, text: str) -> PIIResult:
        analyzer = self._load_presidio()
        results = analyzer.analyze(text=text or "", language="en")
        entities: list[Entity] = [
            {"type": r.entity_type, "start": r.start, "end": r.end, "score": float(r.score)}
            for r in results
        ]
        return {"entities": entities, "model_id": "presidio", "version": "hf"}
