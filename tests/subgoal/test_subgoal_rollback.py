"""P5.2: SubgoalRollbackManager unit tests.

Validates:
- DAG registration builds correct parent map
- Snapshot captures circuit-breaker & state-machine state
- Ancestor chain computation (single, multi-level, cyclic)
- Cascade rollback across the parent chain
- Edge cases: no snapshot, no circuit-breaker, empty DAG
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

import pytest

from maref.subgoal.goal_inferencer import GoalDAG
from maref.subgoal.rollback import SubgoalRollbackManager


# ── Helpers ─────────────────────────────────────────────────────────


@dataclass
class FakeCircuitBreaker:
    _failure_count: int = 0
    _lock: Lock | None = None


@dataclass
class FakeStateMachine:
    _current_state: str = "ACTIVE"


def _build_dag(edges: list[tuple[str, str]]) -> GoalDAG:
    nodes_set = {n for e in edges for n in e}
    return GoalDAG(
        root_goal="root",
        nodes={n: {} for n in nodes_set},
        edges=edges,
    )


# ── register_dag ────────────────────────────────────────────────────


class TestRegisterDag:
    def test_simple_chain(self) -> None:
        dag = _build_dag([("root", "a"), ("a", "b"), ("b", "c")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr._parent_map == {"root": None, "a": "root", "b": "a", "c": "b"}

    def test_fan_out(self) -> None:
        dag = _build_dag([("root", "a"), ("root", "b"), ("a", "c")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr._parent_map["a"] == "root"
        assert mgr._parent_map["b"] == "root"
        assert mgr._parent_map["c"] == "a"

    def test_register_clears_previous(self) -> None:
        dag1 = _build_dag([("root", "a")])
        dag2 = _build_dag([("root", "b")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag1)
        mgr.register_dag(dag2)
        assert "a" not in mgr._parent_map
        assert mgr._parent_map.get("b") == "root"


# ── snapshot ────────────────────────────────────────────────────────


class TestSnapshot:
    def test_captures_failure_count(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        cb = FakeCircuitBreaker(_failure_count=3)
        mgr.snapshot("a", circuit_breaker=cb)
        snap = mgr._snapshots["a"]
        assert snap.cb_failure_count == 3
        assert snap.parent_id == "root"

    def test_captures_state_machine_state(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        sm = FakeStateMachine(_current_state="HALTED")
        mgr.snapshot("a", state_machine=sm)
        assert mgr._snapshots["a"].sm_state == "HALTED"

    def test_no_circuit_breaker_defaults_zero(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        mgr.snapshot("a")
        assert mgr._snapshots["a"].cb_failure_count == 0

    def test_no_state_machine_defaults_unknown(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        mgr.snapshot("a")
        assert mgr._snapshots["a"].sm_state == "unknown"

    def test_timestamp_is_set(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        mgr.snapshot("a")
        assert mgr._snapshots["a"].timestamp > 0


# ── get_ancestors ───────────────────────────────────────────────────


class TestGetAncestors:
    def test_single_ancestor(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr.get_ancestors("a") == ["root"]

    def test_multi_level(self) -> None:
        dag = _build_dag([("root", "a"), ("a", "b"), ("b", "c")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr.get_ancestors("c") == ["b", "a", "root"]

    def test_root_has_no_ancestors(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr.get_ancestors("root") == []

    def test_unknown_node(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        assert mgr.get_ancestors("unknown") == []

    def test_cycle_terminates(self) -> None:
        dag = _build_dag([("root", "a"), ("a", "b"), ("b", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        ancestors = mgr.get_ancestors("a")
        assert len(ancestors) == 1
        assert ancestors == ["root"]


# ── cascade_rollback ────────────────────────────────────────────────


class TestCascadeRollback:
    def test_single_node_rollback(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        cb = FakeCircuitBreaker(_failure_count=5)
        mgr.snapshot("a", circuit_breaker=cb)
        cb._failure_count = 99

        result = mgr.cascade_rollback("a", circuit_breaker=cb)
        assert result.success is True
        assert result.rolled_back == ["a"]
        assert cb._failure_count == 5

    def test_cascade_multi_level(self) -> None:
        dag = _build_dag([("root", "a"), ("a", "b"), ("b", "c")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        cb = FakeCircuitBreaker(_failure_count=0)
        for node in ["c", "b", "a"]:
            cb._failure_count = 0
            mgr.snapshot(node, circuit_breaker=cb)

        cb._failure_count = 99
        result = mgr.cascade_rollback("c", circuit_breaker=cb)
        assert result.success is True
        assert set(result.rolled_back) == {"c", "b", "a"}
        assert cb._failure_count == 0

    def test_no_snapshot_fails(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        result = mgr.cascade_rollback("a")
        assert result.success is False
        assert "no snapshot" in result.reason

    def test_no_circuit_breaker_rollback(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        mgr.snapshot("a")
        result = mgr.cascade_rollback("a")
        assert result.success is True
        assert result.rolled_back == ["a"]

    def test_rollback_with_lock(self) -> None:
        dag = _build_dag([("root", "a")])
        mgr = SubgoalRollbackManager()
        mgr.register_dag(dag)
        cb = FakeCircuitBreaker(_failure_count=3, _lock=Lock())
        mgr.snapshot("a", circuit_breaker=cb)
        cb._failure_count = 50

        result = mgr.cascade_rollback("a", circuit_breaker=cb)
        assert result.success is True
        assert cb._failure_count == 3


# ── get_latest_snapshot_id / snapshot_count ─────────────────────────


class TestSnapshotsMetadata:
    def test_get_latest_snapshot_id(self) -> None:
        mgr = SubgoalRollbackManager()
        dag = _build_dag([("root", "a"), ("root", "b")])
        mgr.register_dag(dag)
        mgr.snapshot("a")
        mgr.snapshot("b")
        assert mgr.get_latest_snapshot_id() == "b"

    def test_get_latest_empty(self) -> None:
        mgr = SubgoalRollbackManager()
        assert mgr.get_latest_snapshot_id() is None

    def test_snapshot_count(self) -> None:
        mgr = SubgoalRollbackManager()
        dag = _build_dag([("root", "a"), ("root", "b")])
        mgr.register_dag(dag)
        assert mgr.snapshot_count == 0
        mgr.snapshot("a")
        assert mgr.snapshot_count == 1
        mgr.snapshot("b")
        assert mgr.snapshot_count == 2

    def test_clear_on_register(self) -> None:
        mgr = SubgoalRollbackManager()
        dag1 = _build_dag([("root", "a")])
        dag2 = _build_dag([("root", "b")])
        mgr.register_dag(dag1)
        mgr.snapshot("a")
        assert mgr.snapshot_count == 1
        mgr.register_dag(dag2)
        assert mgr.snapshot_count == 0
