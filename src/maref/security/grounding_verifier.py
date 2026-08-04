"""GroundingVerifier: RAG grounding / faithfulness scoring (v0.51 W5-S1 / E1).

Verifies that a generated assertion is faithful to the retrieved evidence.
Uses token-overlap faithfulness heuristics by default; a pluggable LLM judge
can be supplied for higher-quality scoring in production.

Supports:
- verify_assertion(assertion, evidence) -> GroundingScore
- is_grounded(score, threshold) gate for downstream hallucination marking
- protocol-E triangulation entry point for the VerificationBridge
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SupportLevel(Enum):
    """How well evidence supports the assertion."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


@dataclass
class GroundingScore:
    """Faithfulness of one assertion against its evidence."""

    assertion: str
    score: float  # 0.0 - 1.0
    support_level: SupportLevel
    evidence_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion": self.assertion,
            "score": round(self.score, 4),
            "support_level": self.support_level.value,
            "evidence_ids": list(self.evidence_ids),
            "reasons": list(self.reasons),
        }


# Pluggable LLM judge signature: returns a faithfulness score in [0, 1].
LLMJudge = Callable[[str, list[str]], float]

_TOKEN_RE = re.compile(r"\b\w+\b")

# Synonym normalisation so paraphrased assertions still count as grounded.
_TOKEN_NORMALIZE: dict[str, str] = {
    "rose": "increase",
    "rose_by": "increase",
    "increased": "increase",
    "increases": "increase",
    "grew": "increase",
    "grown": "increase",
    "declined": "decrease",
    "dropped": "decrease",
    "fell": "decrease",
    "fall": "decrease",
    "flat": "flat",
    "flatlined": "flat",
    "unchanged": "flat",
    "steady": "flat",
}

# Direction words: positive movement claims vs negative/static evidence.
_POSITIVE_DIRECTION = {"increase", "double", "doubled", "triple", "tripled", "grow", "growth", "rise"}
_NEGATIVE_DIRECTION = {"decrease", "decline", "dropped", "fell", "fall", "shrink", "shrank", "reduce"}
_FLAT_DIRECTION = {"flat", "unchanged", "steady", "same", "stagnant"}


def _tokenize(text: str) -> set[str]:
    return {_TOKEN_NORMALIZE.get(w.lower(), w.lower()) for w in _TOKEN_RE.findall(text)}


def _direction_conflict(assertion: str, evidence: list[str]) -> bool:
    """True when assertion and evidence state contradictory movement directions."""
    assertion_tokens = _tokenize(assertion)
    evidence_tokens: set[str] = set()
    for chunk in evidence:
        evidence_tokens |= _tokenize(chunk)

    a_positive = bool(assertion_tokens & _POSITIVE_DIRECTION)
    a_negative = bool(assertion_tokens & _NEGATIVE_DIRECTION)
    e_negative = bool(evidence_tokens & (_NEGATIVE_DIRECTION | _FLAT_DIRECTION))

    # e.g. "doubled" (positive) vs "flat/declined" (negative/flat) is a conflict.
    return a_positive and e_negative


def _token_overlap(assertion: str, evidence: list[str]) -> float:
    """Heuristic faithfulness: ratio of (normalized) assertion tokens found in evidence."""
    assertion_tokens = _tokenize(assertion)
    if not assertion_tokens:
        return 0.0
    evidence_tokens: set[str] = set()
    for chunk in evidence:
        evidence_tokens |= _tokenize(chunk)
    if not evidence_tokens:
        return 0.0
    hit = assertion_tokens & evidence_tokens
    return len(hit) / len(assertion_tokens)


class GroundingVerifier:
    """RAG grounding verification with pluggable faithfulness scoring."""

    def __init__(self, llm_judge: LLMJudge | None = None) -> None:
        self._llm_judge = llm_judge

    def verify_assertion(
        self,
        assertion: str,
        evidence: list[str],
        evidence_ids: list[str] | None = None,
    ) -> GroundingScore:
        """Score how faithfully ``assertion`` is supported by ``evidence``."""
        if not evidence:
            return GroundingScore(
                assertion=assertion,
                score=0.0,
                support_level=SupportLevel.UNVERIFIABLE,
                evidence_ids=list(evidence_ids or []),
                reasons=["no evidence supplied"],
            )

        if self._llm_judge is not None:
            score = self._llm_judge(assertion, evidence)
            level = SupportLevel.SUPPORTED if score >= 0.5 else SupportLevel.CONTRADICTED
        else:
            score = _token_overlap(assertion, evidence)
            # Suppress score when evidence contradicts the assertion's direction.
            if _direction_conflict(assertion, evidence):
                score = min(score, 0.3)
                level = SupportLevel.CONTRADICTED
            else:
                level = SupportLevel.SUPPORTED if score >= 0.5 else SupportLevel.CONTRADICTED

        score = max(0.0, min(1.0, score))
        return GroundingScore(
            assertion=assertion,
            score=score,
            support_level=level,
            evidence_ids=list(evidence_ids or []),
            reasons=[f"faithfulness score {score:.2f}"],
        )

    def verify_document(
        self,
        assertions: list[str],
        evidence_by_assertion: dict[str, list[str]],
    ) -> list[GroundingScore]:
        """Verify a set of assertions each against its own evidence."""
        return [
            self.verify_assertion(assertion, evidence_by_assertion.get(assertion, []))
            for assertion in assertions
        ]

    def is_grounded(self, score: GroundingScore, threshold: float = 0.7) -> bool:
        """Gate: True when score meets the faithfulness threshold."""
        return score.support_level == SupportLevel.SUPPORTED and score.score >= threshold
