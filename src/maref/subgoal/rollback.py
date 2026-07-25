"""P5.2: Subgoal cascade rollback support.

Provides snapshot-based rollback for subgoal side effects.  When a subgoal
is blocked/halted, the SubgoalRollbackManager propagates the failure up the
parent chain (GoalDAG edges) and restores ancestor governance state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maref.subgoal.goal_inferencer import GoalDAG


@dataclass
class SubgoalSnapshot:
    """Captured governance side-effects of a subgoal for later restoration."""

    node_id: str
    parent_id: str | None
    cb_failure_count: int
    sm_state: str
    timestamp: float


@dataclass
class RollbackResult:
    """Outcome of a cascade rollback operation."""

    rolled_back: list[str] = field(default_factory=list)
    success: bool = False
    reason: str = ""


class SubgoalRollbackManager:
    """Manages subgoal snapshots and cascade rollback along the parent chain.

    The parent chain is derived from ``GoalDAG.edges`` (directed parent ->
    child).  ``cascade_rollback`` walks from the failed node up to the root,
    restoring each ancestor's governance side-effects in reverse order.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, SubgoalSnapshot] = {}
        self._parent_map: dict[str, str | None] = {}

    def register_dag(self, dag: GoalDAG) -> None:
        """Build the parent map from a GoalDAG's edges."""
        self._parent_map.clear()
        self._snapshots.clear()
        for node_id in dag.nodes:
            parents = [src for src, dst in dag.edges if dst == node_id]
            self._parent_map[node_id] = parents[0] if parents else None

    def snapshot(
        self,
        node_id: str,
        circuit_breaker: Any | None = None,
        state_machine: Any | None = None,
    ) -> None:
        """Capture governance side-effects for a subgoal node."""
        cb_failures = 0
        if circuit_breaker is not None:
            cb_failures = int(getattr(circuit_breaker, "_failure_count", 0))
        sm_state = "unknown"
        if state_machine is not None:
            raw = getattr(state_machine, "_current_state", "unknown")
            sm_state = raw.value if hasattr(raw, "value") else str(raw)
        self._snapshots[node_id] = SubgoalSnapshot(
            node_id=node_id,
            parent_id=self._parent_map.get(node_id),
            cb_failure_count=cb_failures,
            sm_state=sm_state,
            timestamp=time.time(),
        )

    def get_ancestors(self, node_id: str) -> list[str]:
        """Return the ancestor chain from parent up to root (exclusive of node)."""
        chain: list[str] = []
        current = self._parent_map.get(node_id)
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            chain.append(current)
            current = self._parent_map.get(current)
        return chain

    def cascade_rollback(
        self,
        failed_node_id: str,
        circuit_breaker: Any | None = None,
        state_machine: Any | None = None,
    ) -> RollbackResult:
        """Roll back the failed node and all ancestors with snapshots.

        Walks from the failed node up to the root, restoring each snapshot's
        circuit-breaker failure count.  State-machine restoration is
        best-effort (recorded but not force-reverted, as transitions are
        rule-governed).
        """
        if failed_node_id not in self._snapshots:
            return RollbackResult(
                success=False, reason=f"no snapshot for node {failed_node_id}"
            )

        # Build the full chain: failed node -> parent -> ... -> root
        chain = [failed_node_id] + self.get_ancestors(failed_node_id)

        rolled_back: list[str] = []
        for node_id in chain:
            snap = self._snapshots.get(node_id)
            if snap is None:
                continue
            self._restore(snap, circuit_breaker)
            rolled_back.append(node_id)

        return RollbackResult(
            rolled_back=rolled_back,
            success=True,
            reason=f"cascaded {len(rolled_back)} nodes",
        )

    def _restore(
        self,
        snapshot: SubgoalSnapshot,
        circuit_breaker: Any | None,
    ) -> None:
        """Restore governance side-effects from a snapshot (best-effort)."""
        if circuit_breaker is not None and hasattr(
            circuit_breaker, "_failure_count"
        ):
            lock = getattr(circuit_breaker, "_lock", None)
            if lock is not None:
                with lock:
                    circuit_breaker._failure_count = snapshot.cb_failure_count
            else:
                circuit_breaker._failure_count = snapshot.cb_failure_count

    def get_latest_snapshot_id(self) -> str | None:
        """Return the node_id of the most recently snapshotted node."""
        if not self._snapshots:
            return None
        return list(self._snapshots.keys())[-1]

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)
