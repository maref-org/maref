from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PERCVHypothesis:
    hypothesis_id: str
    description: str
    source: str = "percv"
    confidence: float = 0.0
    card_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
            "card_id": self.card_id,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class PERCVHypothesisBridge:
    VERIFIED_STATUSES = {"verified", "validated", "accepted"}

    def __init__(self, min_confidence: float = 0.8) -> None:
        self._min_confidence = min_confidence

    def cards_to_hypotheses(self, cards: list[dict[str, Any]]) -> list[PERCVHypothesis]:
        hypotheses: list[PERCVHypothesis] = []
        for card in cards:
            hypothesis = self._card_to_hypothesis(card)
            if hypothesis is not None:
                hypotheses.append(hypothesis)
        return hypotheses

    def _card_to_hypothesis(self, card: dict[str, Any]) -> PERCVHypothesis | None:
        metadata = dict(card.get("metadata") or {})
        confidence = self._extract_confidence(card, metadata)
        status = str(metadata.get("verification_status", card.get("verification_status", ""))).lower()
        if confidence < self._min_confidence:
            return None
        if status and status not in self.VERIFIED_STATUSES:
            return None

        card_id = str(card.get("id", card.get("card_id", "unknown")))
        content = str(card.get("content", card.get("description", "")))
        if not content:
            return None

        return PERCVHypothesis(
            hypothesis_id=f"percv-{card_id}",
            description=content,
            confidence=confidence,
            card_id=card_id,
            metadata={"card_type": card.get("type", "unknown"), **metadata},
        )

    @staticmethod
    def _extract_confidence(card: dict[str, Any], metadata: dict[str, Any]) -> float:
        raw = metadata.get("confidence", card.get("confidence", 0.0))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0


__all__ = ["PERCVHypothesis", "PERCVHypothesisBridge"]
