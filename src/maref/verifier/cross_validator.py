"""CrossValidator — run multiple verifiers and aggregate results."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from maref.verifier.collaboration_attribution import analyze, attach
from maref.verifier.protocol import (
    CrossValidationResult,
    EvaluationRequest,
    Verdict,
    Verifier,
)
from maref.verifier.registry import VerifierRegistry
from maref.verifier.tracker import VerifierTracker


class CrossValidator:
    """Run multiple verifiers on the same input and compute consensus.

    Supports:
    - Majority voting (simple consensus)
    - Weighted voting (by confidence or historical accuracy)
    - Divergence detection (when verifiers disagree strongly)
    """

    def __init__(
        self,
        registry: VerifierRegistry,
        tracker: VerifierTracker | None = None,
        consensus_threshold: float = 0.5,
    ) -> None:
        self._registry = registry
        self._tracker = tracker or VerifierTracker()
        self._consensus_threshold = consensus_threshold

    @property
    def tracker(self) -> VerifierTracker:
        return self._tracker

    async def evaluate(
        self,
        request: EvaluationRequest,
        verifiers: list[Verifier] | None = None,
        messages: Sequence[Mapping[str, Any]] | None = None,
    ) -> CrossValidationResult:
        """Run all (or specified) verifiers and compute consensus.

        When *messages* (agent-to-agent exchange records) are provided, a
        CooperBench-style collaboration report is attached to the result.
        """
        if verifiers is None:
            verifiers = self._registry.list_all()

        result = CrossValidationResult()

        for verifier in verifiers:
            start = time.time()
            try:
                verdict = await verifier.evaluate(request)
                verdict.verifier_name = verifier.name
            except Exception as exc:
                verdict = Verdict(
                    passed=False,
                    score=0.0,
                    confidence=0.0,
                    summary=f"Verifier error: {exc}",
                    verifier_name=verifier.name,
                )

            latency_ms = (time.time() - start) * 1000.0
            result.verdicts.append(verdict)

            if self._tracker:
                self._tracker.record(
                    verifier_name=verifier.name,
                    passed=verdict.passed,
                    score=verdict.score,
                    confidence=verdict.confidence,
                    latency_ms=latency_ms,
                )

        result.consensus_passed = self._compute_consensus(result.verdicts)
        result.consensus_score = self._compute_weighted_score(result.verdicts)
        result.consensus_confidence = self._compute_confidence(result.verdicts)
        result.agreement_ratio = self._compute_agreement(result.verdicts)
        result.divergences = self._detect_divergences(result.verdicts)

        if messages:
            attach(result, analyze(messages))

        return result

    def _compute_consensus(self, verdicts: list[Verdict]) -> bool:
        """Majority voting."""
        if not verdicts:
            return False
        passed = sum(1 for v in verdicts if v.passed)
        return passed / len(verdicts) >= self._consensus_threshold

    def _compute_weighted_score(self, verdicts: list[Verdict]) -> float:
        """Confidence-weighted average score."""
        if not verdicts:
            return 0.0
        total_weight = sum(v.confidence for v in verdicts)
        if total_weight == 0:
            return sum(v.score for v in verdicts) / len(verdicts)
        return sum(v.score * v.confidence for v in verdicts) / total_weight

    def _compute_confidence(self, verdicts: list[Verdict]) -> float:
        """Aggregate confidence — average of individual confidences."""
        if not verdicts:
            return 0.0
        return sum(v.confidence for v in verdicts) / len(verdicts)

    def _compute_agreement(self, verdicts: list[Verdict]) -> float:
        """What fraction of verifiers agree with the consensus."""
        if not verdicts:
            return 0.0
        consensus = self._compute_consensus(verdicts)
        agreeing = sum(1 for v in verdicts if v.passed == consensus)
        return agreeing / len(verdicts)

    def _detect_divergences(self, verdicts: list[Verdict]) -> list[dict[str, Any]]:
        """Find significant disagreements among verifiers."""
        divergences = []
        if len(verdicts) < 2:
            return divergences

        for i, a in enumerate(verdicts):
            for b in verdicts[i + 1:]:
                if a.passed != b.passed and a.confidence > 0.5 and b.confidence > 0.5:
                    divergences.append({
                        "verifier_a": a.verifier_name,
                        "verifier_b": b.verifier_name,
                        "a_passed": a.passed,
                        "b_passed": b.passed,
                        "a_score": round(a.score, 3),
                        "b_score": round(b.score, 3),
                        "a_confidence": round(a.confidence, 3),
                        "b_confidence": round(b.confidence, 3),
                    })
        return divergences
