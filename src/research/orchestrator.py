import random
import time
from dataclasses import dataclass
from typing import Any

from research.experiment_registry import ExperimentRegistry
from research.vector_store import VectorStore  # type: ignore[attr-defined]


@dataclass
class StoppingCriteria:
    max_experiments: int = 100
    max_time_seconds: float = 3600.0
    improvement_threshold: float = 0.01
    patience: int = 10

class ExperimentOrchestrator:

    def __init__(self, registry: ExperimentRegistry, vector_store: VectorStore, stopping_criteria: StoppingCriteria | None=None) -> None:
        self.registry = registry
        self.vector_store = vector_store
        self.stopping_criteria = stopping_criteria or StoppingCriteria()
        self._start_time: float = time.time()
        self._no_improvement_count: int = 0
        self._best_score: float = float('-inf')
        self._batch_results: list[dict[str, Any]] = []

    def select_next_experiment(self) -> str | None:
        try:
            candidates = self.registry.get_pending_experiments()  # type: ignore[attr-defined]
            if not candidates:
                return None
            scored = [(self._compute_score(c), c) for c in candidates]
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1]
        except Exception:
            return None

    def _compute_score(self, experiment_id: str) -> float:
        try:
            base_score = random.random()
            similar = self.vector_store.query_similar(experiment_id, top_k=5)
            if similar:
                avg_similarity = sum(s[1] for s in similar) / len(similar)
                base_score += avg_similarity * 0.5
            return base_score
        except Exception:
            return 0.0

    def should_stop(self) -> bool:
        try:
            elapsed = time.time() - self._start_time
            if elapsed >= self.stopping_criteria.max_time_seconds:
                return True
            total = self.registry.get_total_experiments()  # type: ignore[attr-defined]
            if total >= self.stopping_criteria.max_experiments:
                return True
            if self._no_improvement_count >= self.stopping_criteria.patience:
                return True
            return False
        except Exception:
            return True

    def record_result(self, experiment_id: str, score: float, metadata: dict[str, Any] | None=None) -> None:
        try:
            self.registry.record_result(experiment_id, score, metadata)  # type: ignore[attr-defined]
            if score > self._best_score:
                self._best_score = score
                self._no_improvement_count = 0
            else:
                self._no_improvement_count += 1
            self._batch_results.append({'experiment_id': experiment_id, 'score': score, 'metadata': metadata})
        except Exception:
            pass

    def reset_batch(self) -> None:
        try:
            self._batch_results.clear()
        except Exception:
            pass

    def get_stats(self) -> dict[str, Any]:
        try:
            return {'total_experiments': self.registry.get_total_experiments(), 'best_score': self._best_score, 'no_improvement_count': self._no_improvement_count, 'elapsed_time': time.time() - self._start_time, 'batch_size': len(self._batch_results)}  # type: ignore[attr-defined]
        except Exception:
            return {}
