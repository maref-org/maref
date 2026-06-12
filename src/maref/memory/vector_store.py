"""Lightweight vector store with character n-gram embedding.

Zero external ML dependencies. Uses character n-gram overlap as a
surrogate for semantic similarity. Suitable for local development and
testing. In production, replace with a real embedding API + vector DB.

Embedding: character n-grams (n=2..4) → sparse binary vector
Similarity: cosine over n-gram frequency profile
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


def _ngrams(text: str, n_min: int = 2, n_max: int = 4) -> Counter[str]:
    """Compute character n-gram frequencies for a text string."""
    text = text.lower()
    result: Counter[str] = Counter()
    for n in range(n_min, n_max + 1):
        for i in range(len(text) - n + 1):
            result[text[i : i + n]] += 1
    return result


def _cosine_similarity(a: Counter[str], b: Counter[str]) -> float:
    """Cosine similarity between two n-gram frequency profiles."""
    dot = sum(a[g] * b[g] for g in a if g in b)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class VectorRecord:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: Counter[str] | None = None

    def __post_init__(self) -> None:
        if self.embedding is None:
            self.embedding = _ngrams(self.text)


class VectorStore:
    """In-memory vector store using n-gram embeddings.

    Supports insert, delete, and similarity search.
    Threshold-based filtering: only results above `min_score` returned.
    """

    def __init__(self, min_score: float = 0.15) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._min_score = min_score

    def insert(self, record: VectorRecord) -> None:
        self._records[record.id] = record

    def delete(self, record_id: str) -> bool:
        return self._records.pop(record_id, None) is not None

    def get(self, record_id: str) -> VectorRecord | None:
        return self._records.get(record_id)

    def similarity_search(
        self,
        query: str,
        k: int = 10,
        min_score: float | None = None,
    ) -> list[tuple[VectorRecord, float]]:
        """Return top-k records most similar to query text."""
        threshold = min_score if min_score is not None else self._min_score
        query_ng = _ngrams(query)
        scored: list[tuple[VectorRecord, float]] = []
        for record in self._records.values():
            emb = record.embedding
            if emb is None:
                continue
            score = _cosine_similarity(query_ng, emb)
            if score >= threshold:
                scored.append((record, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def __len__(self) -> int:
        return len(self._records)

    def clear(self) -> None:
        self._records.clear()
