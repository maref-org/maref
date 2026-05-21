"""Formal verification tests for MAREF governance state machine.

Uses shared fixtures from conftest.py for Gray code validation,
snapshot/restore, entropy profiles, and BFS path-finding.
"""

from __future__ import annotations

from typing import Any

from maref.governance.constants import ENTROPY_LEVELS as _ENTROPY_INT
from maref.governance.constants import hamming_distance
from maref.governance.types import GovernanceState, StateMachineSnapshot


class TestGrayCodeValidator:
    """6 formal verification checks via fixture."""

    def test_all_checks_pass(self, validator: type[Any]) -> None:
        results = validator.run_all()
        assert len(results) == 6, f"Expected 6 checks, got {len(results)}"
        for r in results:
            assert r["passed"], f"FAILED: {r['check']} — {r['detail']}"
        print("\n  All 6 checks: PASSED")

    def test_single_bit_only(self, validator: type[Any]) -> None:
        results = validator.check_single_bit_transitions()
        assert results[0]["passed"]

    def test_no_self_loops(self, validator: type[Any]) -> None:
        results = validator.check_no_self_loops()
        assert results[0]["passed"]

    def test_terminal_absorbing(self, validator: type[Any]) -> None:
        results = validator.check_terminal_absorbing()
        assert results[0]["passed"]

    def test_reachability(self, validator: type[Any]) -> None:
        results = validator.check_reachability()
        assert results[0]["passed"]

    def test_entropy_profile(self, validator: type[Any]) -> None:
        results = validator.check_entropy_profile()
        assert results[0]["passed"]

    def test_gray_code_uniqueness(self, validator: type[Any]) -> None:
        results = validator.check_gray_code_uniqueness()
        assert results[0]["passed"]


class TestSnapshotRestore:
    """Snapshot and restore functionality."""

    def test_snapshot_roundtrip(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        snap = sm.snapshot()
        assert snap.current_state == GovernanceState.ACT
        assert snap.transition_count == 5

    def test_restore_preserves_state(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        snap = sm.snapshot()
        restored = type(sm).restore(snap)
        assert restored.current_state == GovernanceState.ACT
        assert restored.transition_count == 5
        assert restored.current_entropy == _ENTROPY_INT[GovernanceState.ACT.value]

    def test_restore_does_not_preserve_history(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        snap = sm.snapshot()
        restored = type(sm).restore(snap)
        assert len(restored.get_history()) == 0

    def test_snapshot_from_init(self, initial_state_machine: Any) -> None:
        sm = initial_state_machine
        snap = sm.snapshot()
        assert snap.current_state == GovernanceState.INIT
        assert snap.transition_count == 0

    def test_snapshot_from_halt(self, halted_state_machine: Any) -> None:
        sm = halted_state_machine
        snap = sm.snapshot()
        assert snap.current_state == GovernanceState.HALT
        assert snap.transition_count == 9

    def test_snapshot_to_dict(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        snap = sm.snapshot()
        d = snap.to_dict()
        assert d["current_state"] == "ACT"
        assert d["current_state_id"] == 5
        assert isinstance(d["entropy_history"], list)

    def test_snapshot_from_dict(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        snap = sm.snapshot()
        d = snap.to_dict()
        restored_snap = StateMachineSnapshot.from_dict(d)
        assert restored_snap.current_state == GovernanceState.ACT
        assert restored_snap.transition_count == 5


class TestStateMachineFixtures:
    """Verify shared fixtures are correctly initialized."""

    def test_initial_is_init(self, initial_state_machine: Any) -> None:
        sm = initial_state_machine
        assert sm.current_state == GovernanceState.INIT
        assert sm.current_entropy == 0
        assert sm.transition_count == 0

    def test_mid_cycle_is_act(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        assert sm.current_state == GovernanceState.ACT
        assert sm.current_entropy == _ENTROPY_INT[GovernanceState.ACT.value]

    def test_halted_is_halt(self, halted_state_machine: Any) -> None:
        sm = halted_state_machine
        assert sm.current_state == GovernanceState.HALT
        assert sm.is_terminal()

    def test_halt_rejects_more_transitions(self, halted_state_machine: Any) -> None:
        sm = halted_state_machine
        assert not sm.can_transition(GovernanceState.REPORT)
        assert not sm.transition(GovernanceState.REPORT)

    def test_force_stabilize_from_mid_cycle(self, mid_cycle_state_machine: Any) -> None:
        sm = mid_cycle_state_machine
        assert sm.current_state == GovernanceState.ACT
        sm.force_stabilize("test")
        assert sm.current_state == GovernanceState.STABILIZE

    def test_force_stabilize_noop_on_halt(self, halted_state_machine: Any) -> None:
        sm = halted_state_machine
        result = sm.force_stabilize()
        assert not result
        assert sm.current_state == GovernanceState.HALT


class TestBFSPathFinding:
    """Verify BFS finds shortest paths for force operations."""

    def test_bfs_to_stabilize_from_observe(self, initial_state_machine: Any) -> None:
        sm = initial_state_machine
        sm.transition(GovernanceState.OBSERVE)
        sm.force_stabilize()
        assert sm.current_state == GovernanceState.STABILIZE

    def test_bfs_to_halt_from_observe(self, initial_state_machine: Any) -> None:
        sm = initial_state_machine
        sm.transition(GovernanceState.OBSERVE)
        sm.force_halt()
        assert sm.current_state == GovernanceState.HALT
        assert sm.is_terminal()

    def test_hamming_single_bit(self, gray_code_matrix: Any) -> None:
        codes = gray_code_matrix
        for i in range(9):
            assert hamming_distance(codes[i], codes[i + 1]) == 1, \
                f"Adjacent states {i}→{i + 1} must differ by 1 bit"
