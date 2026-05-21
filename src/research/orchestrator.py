"""
MAREF Experiment Orchestrator

Dynamic experiment selection and adaptive stopping for continuous autoresearch.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from research.experiment_registry import ExperimentMetadata, ExperimentRegistry
from research.vector_store import VectorKnowledgeStore


@dataclass
class StoppingCriteria:
    """Criteria for adaptive stopping."""

    max_consecutive_no_findings: int = 5
    min_novelty_threshold: float = 0.1
    max_experiments_per_batch: int = 100
    min_experiments_per_batch: int = 10


class ExperimentOrchestrator:
    """
    Dynamically selects experiments based on historical performance
    and implements adaptive stopping.
    """

    def __init__(
        self,
        registry: ExperimentRegistry | None = None,
        criteria: StoppingCriteria | None = None,
        vector_store: VectorKnowledgeStore | None = None,
    ) -> None:
        self._registry = registry or ExperimentRegistry()
        self._criteria = criteria or StoppingCriteria()
        self._consecutive_no_findings = 0
        self._batch_results: list[Any] = []
        self._vector_store = vector_store

    def select_next_experiment(self) -> tuple[str, Any]:
        """
        Select the next experiment to run based on information gain.

        Returns:
            Tuple of (experiment_name, experiment_function)
        """
        metadata = self._registry.get_all_metadata()

        if not metadata:
            return "random_walk", None

        # Calculate score for each experiment
        scores = {}
        for name, meta in metadata.items():
            score = self._compute_score(meta)
            scores[name] = score

        # Select with probability proportional to score (exploration vs exploitation)
        total_score = sum(scores.values())
        if total_score == 0:
            # Random selection if all scores are 0
            selected = random.choice(list(scores.keys()))
        else:
            # Weighted random selection
            r = random.uniform(0, total_score)
            cumulative = 0
            selected = list(scores.keys())[0]
            for name, score in scores.items():
                cumulative += score
                if cumulative >= r:
                    selected = name
                    break

        exp = self._registry.get_experiment(selected)
        if exp:
            return selected, exp[0]
        return selected, None

    def _compute_score(self, meta: ExperimentMetadata) -> float:
        """
        Compute selection score for an experiment.

        Factors:
        - Novelty: higher = more likely to produce new findings
        - Success rate: historical finding rate
        - Recency: experiments not run recently get bonus
        - Phase: higher phase experiments get slight bonus
        """
        # Base score from novelty
        score = meta.novelty_score * 2.0

        # Success rate bonus
        score += meta.success_rate * 1.5

        # Recency bonus (decay over time)
        time_since_last = time.time() - meta.last_run
        if time_since_last > 3600:  # Not run in last hour
            score += 0.5

        # Phase bonus (higher phases slightly preferred)
        score += meta.phase * 0.05

        # Penalize if run too frequently
        if meta.run_count > 50:
            score *= 0.8

        # Semantic novelty bonus: if VKS is available, check whether this
        # experiment's recent findings are semantically similar to existing
        # knowledge. High similarity = low novelty → lower score.
        if self._vector_store is not None and self._vector_store.count() > 5:
            similar = self._vector_store.search(meta.description, n_results=3)
            if similar:
                avg_distance = sum(r.score for r in similar) / len(similar)
                # avg_distance is cosine distance (0=identical, 2=opposite)
                # Normalise to a 0-1 novelty factor:
                #   distance 0.0 → novelty 0.0 (already covered)
                #   distance 1.0 → novelty 0.5
                #   distance 2.0 → novelty 1.0 (uncharted)
                novelty = min(avg_distance / 2.0, 1.0)
                score *= 0.5 + 0.5 * novelty  # At worst 0.5×, at best 1.0×

        return max(0.1, score)

    def should_stop(self) -> bool:
        """
        Determine if the current batch should stop.

        Stopping conditions:
        1. Too many consecutive experiments with no findings
        2. Batch size exceeds maximum
        3. Average novelty too low
        """
        # Check consecutive no findings
        if self._consecutive_no_findings >= self._criteria.max_consecutive_no_findings:
            return True

        # Check batch size
        if len(self._batch_results) >= self._criteria.max_experiments_per_batch:
            return True

        # Check minimum batch size
        if len(self._batch_results) < self._criteria.min_experiments_per_batch:
            return False

        # Check average novelty
        if self._batch_results:
            recent_novelty = [
                getattr(r, "novelty", 0.5)
                for r in self._batch_results[-10:]
            ]
            avg_novelty = sum(recent_novelty) / len(recent_novelty)
            if avg_novelty < self._criteria.min_novelty_threshold:
                return True

        return False

    def record_result(self, experiment_name: str, result: Any) -> None:
        """Record experiment result for stopping criteria."""
        self._batch_results.append(result)

        # Update registry metadata
        findings = len(getattr(result, "findings", []))
        duration = getattr(result, "duration_ms", 100.0)
        self._registry.update_metadata(experiment_name, findings, duration)

        # Update consecutive no findings counter
        if findings == 0:
            self._consecutive_no_findings += 1
        else:
            self._consecutive_no_findings = 0

    def reset_batch(self) -> None:
        """Reset batch state for new batch."""
        self._consecutive_no_findings = 0
        self._batch_results.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            "batch_size": len(self._batch_results),
            "consecutive_no_findings": self._consecutive_no_findings,
            "should_stop": self.should_stop(),
            "experiment_scores": {
                name: self._compute_score(meta)
                for name, meta in self._registry.get_all_metadata().items()
                if meta.run_count > 0
            },
        }
