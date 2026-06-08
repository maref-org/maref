"""HypothesisConverter — convert PERCV research findings into SelfOptimizer optimization hypotheses."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from maref.integration.percv.feedback_loop import (
    EvalToResearchFeedback,
    FeedbackPriority,
    ResearchDirection,
)
from maref.recursive.self_optimizer import OptimizationHypothesis


@dataclass
class ConversionResult:
    """Result of converting PERCV research directions to optimization hypotheses."""
    total_directions: int
    converted: int
    skipped: int
    hypotheses: list[OptimizationHypothesis] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)

    @property
    def conversion_rate(self) -> float:
        return self.converted / max(self.total_directions, 1)


class HypothesisConverter:
    """Converts high-confidence PERCV research findings into SelfOptimizer hypotheses.

    Rules:
    - CRITICAL priority directions → always convert
    - HIGH priority directions → convert if score_gap > 10
    - MEDIUM priority → convert if score_gap > 20
    - LOW priority → skip (not actionable enough)
    """

    # Minimum confidence score for conversion
    CONFIDENCE_THRESHOLD = 0.8

    # Score gap thresholds by priority
    GAP_THRESHOLDS = {
        FeedbackPriority.CRITICAL: 0.0,    # always convert
        FeedbackPriority.HIGH: 10.0,       # convert if gap > 10
        FeedbackPriority.MEDIUM: 20.0,     # convert if gap > 20
        FeedbackPriority.LOW: float("inf"), # skip
    }

    def convert_directions(
        self,
        directions: list[ResearchDirection],
        confidence: float = 1.0,
    ) -> ConversionResult:
        """Convert research directions to optimization hypotheses.

        Args:
            directions: PERCV research directions from feedback loop
            confidence: Confidence score for the research (0.0-1.0)
        """
        if confidence < self.CONFIDENCE_THRESHOLD:
            return ConversionResult(
                total_directions=len(directions),
                converted=0,
                skipped=len(directions),
                skipped_reasons=[f"Confidence {confidence} below threshold {self.CONFIDENCE_THRESHOLD}"],
            )

        hypotheses: list[OptimizationHypothesis] = []
        skipped_reasons: list[str] = []
        converted = 0

        for direction in directions:
            threshold = self.GAP_THRESHOLDS.get(direction.priority, float("inf"))

            if direction.score_gap < threshold:
                skipped_reasons.append(
                    f"{direction.topic}: score_gap={direction.score_gap:.1f} < threshold={threshold:.1f}"
                )
                continue

            hypothesis = self._direction_to_hypothesis(direction)
            hypotheses.append(hypothesis)
            converted += 1

        return ConversionResult(
            total_directions=len(directions),
            converted=converted,
            skipped=len(directions) - converted,
            hypotheses=hypotheses,
            skipped_reasons=skipped_reasons,
        )

    def convert_from_feedback_loop(
        self,
        feedback_loop: EvalToResearchFeedback,
        confidence: float = 1.0,
    ) -> ConversionResult:
        """Convert all directions from an EvalToResearchFeedback instance."""
        directions = feedback_loop.get_all_directions()
        return self.convert_directions(directions, confidence=confidence)

    def inject_to_optimizer(
        self,
        optimizer: Any,
        directions: list[ResearchDirection],
        confidence: float = 1.0,
    ) -> ConversionResult:
        """Convert and inject hypotheses directly into a SelfOptimizer instance."""
        result = self.convert_directions(directions, confidence=confidence)

        if hasattr(optimizer, "_hypotheses"):
            optimizer._hypotheses.extend(result.hypotheses)

        return result

    def _direction_to_hypothesis(self, direction: ResearchDirection) -> OptimizationHypothesis:
        """Convert a single ResearchDirection to OptimizationHypothesis."""
        priority_map = {
            FeedbackPriority.CRITICAL: "[CRITICAL] ",
            FeedbackPriority.HIGH: "[HIGH] ",
            FeedbackPriority.MEDIUM: "[MEDIUM] ",
            FeedbackPriority.LOW: "",
        }
        prefix = priority_map.get(direction.priority, "")

        return OptimizationHypothesis(
            hypothesis_id=str(uuid.uuid4())[:8],
            description=f"{prefix}{direction.topic} (source: {direction.source})",
            target_module=self._extract_target_module(direction),
            conclusion=f"PERCV research direction: {direction.rationale}",
        )

    @staticmethod
    def _extract_target_module(direction: ResearchDirection) -> str:
        """Extract target module from research direction topic."""
        topic = direction.topic.lower()
        source = direction.source.lower()

        if "layer 1" in source or "static" in topic:
            return "src/maref/recursive/"
        if "layer 2" in source or "reasoning" in topic:
            return "src/maref/integration/percv/"
        if "layer 3" in source or "action" in topic:
            return "src/maref/execution/"
        if "layer 4" in source or "e2e" in topic:
            return "src/maref/"
        if "layer 5" in source or "mas" in topic:
            return "src/maref/recursive/"
        if "evolution" in source:
            return "src/maref/evolution/"
        if "quality_gate" in source:
            return "src/maref/integration/test_platform/"

        return "src/maref/"
