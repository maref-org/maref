from __future__ import annotations

import time

import pytest

from maref.recursive.recursive_evolution_loop import (
    RELSafetyGovernor,
    RELTransaction,
    SafetyGovernorConfig,
    TransactionState,
)


class TestRELSafetyGovernor:
    @pytest.fixture
    def governor(self) -> RELSafetyGovernor:
        config = SafetyGovernorConfig(
            max_rounds_per_session=5,
            max_files_per_round=3,
            hitl_interval_rounds=2,
            max_wall_clock_seconds=3600,
            rel_cb_trip_threshold=2,
        )
        return RELSafetyGovernor(config=config)

    def test_start_session_resets_counters(self, governor: RELSafetyGovernor) -> None:
        governor._round_count = 10
        governor._consecutive_rollbacks = 5
        governor.start_session()
        assert governor.round_count == 0
        assert governor.consecutive_rollbacks == 0

    def test_pre_deploy_under_limit(self, governor: RELSafetyGovernor) -> None:
        governor.start_session()
        verdict = governor.check_pre_deploy(["f1.py", "f2.py"])
        assert verdict.allowed
        assert not verdict.halt

    def test_pre_deploy_exceeds_file_limit(self, governor: RELSafetyGovernor) -> None:
        governor.start_session()
        verdict = governor.check_pre_deploy(["f1.py", "f2.py", "f3.py", "f4.py"])
        assert not verdict.allowed
        assert "exceeds limit" in verdict.reason

    def test_pre_deploy_exceeds_wall_clock(self) -> None:
        config = SafetyGovernorConfig(max_wall_clock_seconds=0)
        governor = RELSafetyGovernor(config=config)
        governor.start_session()
        time.sleep(0.01)
        verdict = governor.check_pre_deploy(["f1.py"])
        assert not verdict.allowed
        assert verdict.halt

    def test_post_round_halt_on_max_rounds(self, governor: RELSafetyGovernor) -> None:
        governor.start_session()
        for i in range(5):
            governor._round_count = i
            verdict = governor.check_post_round(None)
            if i < 4:
                assert verdict.allowed or verdict.requires_hitl
            else:
                assert not verdict.allowed
                assert verdict.halt

    def test_post_round_hitl_interval(self) -> None:
        config = SafetyGovernorConfig(
            max_rounds_per_session=10,
            hitl_interval_rounds=2,
        )
        gov = RELSafetyGovernor(config=config)
        gov.start_session()
        for i in range(1, 7):
            verdict = gov.check_post_round(None)
            if i % 2 == 0:
                assert verdict.requires_hitl, f"Round {i} should require HITL"
                assert verdict.hitl_proposal_id.startswith("hitl_rel_round_")
            else:
                assert not verdict.requires_hitl, f"Round {i} should not require HITL"

    def test_circuit_breaker_trips_on_consecutive_rollbacks(
        self, governor: RELSafetyGovernor
    ) -> None:
        governor.start_session()
        assert governor.consecutive_rollbacks == 0

        tx = RELTransaction(
            tx_id="test_tx",
            round_number=1,
            snapshots=[],
            generated_files=[],
            baseline_metrics={},
            state=TransactionState.ROLLED_BACK,
        )
        v1 = governor.check_post_round(tx)
        assert v1.allowed or v1.requires_hitl

        v2 = governor.check_post_round(tx)
        assert not v2.allowed
        assert v2.halt
        assert "consecutive rollbacks" in v2.reason

    def test_no_circuit_breaker_on_success(self, governor: RELSafetyGovernor) -> None:
        governor.start_session()
        tx = RELTransaction(
            tx_id="test_tx",
            round_number=1,
            snapshots=[],
            generated_files=[],
            baseline_metrics={},
            state=TransactionState.COMMITTED,
        )
        for _ in range(3):
            v = governor.check_post_round(tx)
            assert not v.halt or not v.halt
        assert governor.consecutive_rollbacks == 0

    def test_hitl_proposal_id_is_unique(self, governor: RELSafetyGovernor) -> None:
        governor.start_session()
        ids = set()
        for i in range(1, 7):
            governor._round_count = i
            verdict = governor.check_post_round(None)
            if verdict.requires_hitl:
                assert verdict.hitl_proposal_id not in ids
                ids.add(verdict.hitl_proposal_id)
