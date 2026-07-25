"""P5.2 Subgoal cascade rollback tests.

Validates that SubgoalRollbackManager correctly:
- Builds parent chains from GoalDAG edges
- Snapshots governance side-effects (circuit breaker failure count)
- Cascades rollback from a failed node up to the root
- Handles missing snapshots gracefully
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.subgoal.goal_inferencer import GoalDAG, GoalNode
from maref.subgoal.rollback import SubgoalRollbackManager


def _make_linear_dag() -> GoalDAG:
    """Build a 3-node linear DAG: g_0 -> g_1 -> g_2."""
    dag = GoalDAG(root_goal="root")
    dag.nodes = {
        "g_0": GoalNode("g_0", "step 0", False, 0.1),
        "g_1": GoalNode("g_1", "step 1", False, 0.2),
        "g_2": GoalNode("g_2", "step 2", True, 0.9),
    }
    dag.edges = [("g_0", "g_1"), ("g_1", "g_2")]
    return dag


def _make_branching_dag() -> GoalDAG:
    """Build a branching DAG: g_0 -> g_1, g_0 -> g_2."""
    dag = GoalDAG(root_goal="root")
    dag.nodes = {
        "g_0": GoalNode("g_0", "root step", False, 0.1),
        "g_1": GoalNode("g_1", "branch A", False, 0.3),
        "g_2": GoalNode("g_2", "branch B", True, 0.85),
    }
    dag.edges = [("g_0", "g_1"), ("g_0", "g_2")]
    return dag


class TestRollbackManagerParentMap:
    def test_linear_parent_map(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        assert mgr._parent_map["g_0"] is None
        assert mgr._parent_map["g_1"] == "g_0"
        assert mgr._parent_map["g_2"] == "g_1"

    def test_branching_parent_map(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_branching_dag())
        assert mgr._parent_map["g_0"] is None
        assert mgr._parent_map["g_1"] == "g_0"
        assert mgr._parent_map["g_2"] == "g_0"

    def test_get_ancestors_linear(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        assert mgr.get_ancestors("g_2") == ["g_1", "g_0"]
        assert mgr.get_ancestors("g_1") == ["g_0"]
        assert mgr.get_ancestors("g_0") == []

    def test_get_ancestors_branching(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_branching_dag())
        assert mgr.get_ancestors("g_2") == ["g_0"]
        assert mgr.get_ancestors("g_1") == ["g_0"]


class TestRollbackSnapshot:
    def test_snapshot_captures_cb_failures(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        cb = MagicMock()
        cb._failure_count = 3
        mgr.snapshot("g_1", circuit_breaker=cb)
        assert mgr.snapshot_count == 1
        assert mgr._snapshots["g_1"].cb_failure_count == 3
        assert mgr._snapshots["g_1"].parent_id == "g_0"

    def test_snapshot_captures_sm_state(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        sm = MagicMock()
        sm._current_state = MagicMock()
        sm._current_state.value = "stable"
        mgr.snapshot("g_0", state_machine=sm)
        assert mgr._snapshots["g_0"].sm_state == "stable"

    def test_snapshot_no_components(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        mgr.snapshot("g_0")
        assert mgr._snapshots["g_0"].cb_failure_count == 0
        assert mgr._snapshots["g_0"].sm_state == "unknown"


class TestCascadeRollback:
    def test_cascade_restores_full_chain(self) -> None:
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        cb = MagicMock()
        cb._failure_count = 0
        for nid in ["g_0", "g_1", "g_2"]:
            mgr.snapshot(nid, circuit_breaker=cb)
        # Simulate failures accumulated after snapshots
        cb._failure_count = 5
        result = mgr.cascade_rollback("g_2", circuit_breaker=cb)
        assert result.success is True
        assert result.rolled_back == ["g_2", "g_1", "g_0"]
        # cb_failure_count restored to 0 (from snapshot)
        assert cb._failure_count == 0

    def test_cascade_partial_chain(self) -> None:
        """Only some nodes have snapshots - rollback those that do."""
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        cb = MagicMock()
        cb._failure_count = 2
        # Only snapshot g_2 and g_0 (skip g_1)
        mgr.snapshot("g_2", circuit_breaker=cb)
        mgr.snapshot("g_0", circuit_breaker=cb)
        cb._failure_count = 5
        result = mgr.cascade_rollback("g_2", circuit_breaker=cb)
        assert result.success is True
        assert "g_2" in result.rolled_back
        assert "g_0" in result.rolled_back
        assert "g_1" not in result.rolled_back

    def test_cascade_no_snapshot_fails(self) -> None:
        mgr = SubgoalRollbackManager()
        result = mgr.cascade_rollback("nonexistent")
        assert result.success is False
        assert "no snapshot" in result.reason

    def test_cascade_root_node(self) -> None:
        """Rolling back the root only rolls back itself."""
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_linear_dag())
        cb = MagicMock()
        cb._failure_count = 0
        mgr.snapshot("g_0", circuit_breaker=cb)
        cb._failure_count = 3
        result = mgr.cascade_rollback("g_0", circuit_breaker=cb)
        assert result.success is True
        assert result.rolled_back == ["g_0"]
        assert cb._failure_count == 0

    def test_cascade_branching(self) -> None:
        """In a branching DAG, rolling back g_2 only affects g_2 -> g_0."""
        mgr = SubgoalRollbackManager()
        mgr.register_dag(_make_branching_dag())
        cb = MagicMock()
        cb._failure_count = 0
        for nid in ["g_0", "g_1", "g_2"]:
            mgr.snapshot(nid, circuit_breaker=cb)
        cb._failure_count = 4
        result = mgr.cascade_rollback("g_2", circuit_breaker=cb)
        assert result.success is True
        assert result.rolled_back == ["g_2", "g_0"]
        # g_1 (sibling branch) not affected
        assert "g_1" not in result.rolled_back
