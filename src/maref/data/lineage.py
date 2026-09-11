"""LineageTracker: data lineage graph for enterprise assets (v0.51 W1-S2 / A2).

Tracks data flow between registered data assets as a directed acyclic graph:
- trace_downstream(asset): spread / blast-radius analysis (which assets are
  affected if this source changes)
- trace_upstream(asset): root-cause chain (which sources feed this asset)

Used by DataQualityScorer and SensitiveDataLineage to quantify impact of a
source change or a classification upgrade.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from maref.data.catalog import DataSource


class LineageTracker:
    """Directed graph of data dependencies between data assets."""

    def __init__(self) -> None:
        # parent → children
        self._downstream: dict[str, set[str]] = defaultdict(set)
        # child → parents
        self._upstream: dict[str, set[str]] = defaultdict(set)
        self._transforms: dict[tuple[str, str], str] = {}

    def add_edge(self, upstream: str, downstream: str, transform: str = "identity") -> None:
        """Record that ``downstream`` is derived from ``upstream``."""
        self._downstream[upstream].add(downstream)
        self._upstream[downstream].add(upstream)
        self._transforms[(upstream, downstream)] = transform

    def nodes(self) -> set[str]:
        return set(self._downstream) | set(self._upstream)

    def upstream_of(self, asset: str) -> set[str]:
        return set(self._upstream.get(asset, set()))

    def downstream_of(self, asset: str) -> set[str]:
        return set(self._downstream.get(asset, set()))

    def transform(self, upstream: str, downstream: str) -> str | None:
        return self._transforms.get((upstream, downstream))

    def trace_downstream(self, asset: str) -> set[str]:
        """Return the full downstream spread (blast radius) of ``asset``."""
        visited: set[str] = set()
        queue: deque[str] = deque(self._downstream.get(asset, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._downstream.get(node, set()))
        return visited

    def trace_upstream(self, asset: str) -> set[str]:
        """Return all upstream roots that ultimately feed ``asset``."""
        visited: set[str] = set()
        queue: deque[str] = deque(self._upstream.get(asset, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._upstream.get(node, set()))
        return visited

    def register_flow(
        self, upstream: DataSource, downstream: DataSource, transform: str = "identity"
    ) -> None:
        """Convenience wrapper accepting DataSource objects."""
        self.add_edge(upstream.dataset_id, downstream.dataset_id, transform=transform)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edges": [
                {"upstream": u, "downstream": d, "transform": t}
                for (u, d), t in self._transforms.items()
            ]
        }
