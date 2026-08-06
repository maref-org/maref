"""DecisionExplainer: structured reasoning chains (v0.51 W4-S1 / D1).

Replaces free-text rationales with a validated schema: premises, reasoning
steps (each with confidence + basis), final confidence, alternate options,
and uncertainty sources.  Enforcement is governed by an explicit mode:

- MANDATORY: every decision MUST carry a chain (raises ExplainerRequiredError)
- LAZY:     a default chain is auto-generated
- SKIPPED:  no chain required (returns None)

The mode must always be passed explicitly so a misconfiguration cannot
silently weaken explainability requirements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExplainerMode(Enum):
    """How strictly reasoning chains are enforced."""

    MANDATORY = "mandatory"
    LAZY = "lazy"
    SKIPPED = "skipped"


class ExplainerRequiredError(Exception):
    """Raised when a MANDATORY decision has no reasoning chain."""


@dataclass(frozen=True)
class ReasoningStep:
    """One step in a reasoning chain."""

    description: str
    confidence: float
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "confidence": self.confidence,
            "basis": self.basis,
        }


@dataclass
class ReasoningChain:
    """Structured, validated explanation of a decision."""

    decision_id: str
    conclusion: str
    premises: list[str] = field(default_factory=list)
    steps: list[ReasoningStep] = field(default_factory=list)
    confidence: float = 0.0
    alternatives: list[str] = field(default_factory=list)
    uncertainty_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "conclusion": self.conclusion,
            "premises": list(self.premises),
            "steps": [s.to_dict() for s in self.steps],
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
            "uncertainty_sources": list(self.uncertainty_sources),
        }


class DecisionExplainer:
    """Enforces and produces structured reasoning chains for decisions."""

    def __init__(self, mode: ExplainerMode | None = None) -> None:
        if mode is None:
            raise ValueError(
                "DecisionExplainer mode must be explicit "
                "(mandatory|lazy|skipped) — refusing to weaken explainability by default"
            )
        self.mode = mode

    def require_explanation(
        self,
        decision_id: str,
        conclusion: str,
        chain: ReasoningChain | None = None,
    ) -> ReasoningChain | None:
        """Return the reasoning chain for a decision, enforcing the mode."""
        if self.mode is ExplainerMode.MANDATORY:
            if chain is None:
                raise ExplainerRequiredError(
                    f"decision {decision_id!r} requires a reasoning chain in MANDATORY mode"
                )
            return chain
        if self.mode is ExplainerMode.LAZY:
            if chain is not None:
                return chain
            return ReasoningChain(
                decision_id=decision_id,
                conclusion=conclusion,
                steps=[
                    ReasoningStep(
                        description="auto-generated default",
                        confidence=0.0,
                        basis="lazy-generated: no explicit chain provided",
                    )
                ],
            )
        return None
