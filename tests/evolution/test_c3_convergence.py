"""
Tests for C3 Convergence Verification phase (MAREF v0.24.0-rc).

Covers:
  - ConvergenceDashboard (simulated evolution data, saturation detection)
  - TLAReplayValidator (mock state sequences, invariant checks)
  - MetaAgentClosure 5 red lines (3 bypass attempts each → 100% blocked)
  - MetaCircuitBreaker cascade (OPEN → HALF_OPEN → CLOSED)
  - EvolutionDSL SafetyGate constraints on deploy paths
"""

import json
import tempfile
from pathlib import Path

from maref.recursive.convergence_dashboard import ConvergenceDashboard, ConvergenceSnapshot
from maref.recursive.evolution_dsl import EvolutionDSL, EvolutionRule, SafetyGate
from maref.recursive.meta_agent_closure import (
    EvolutionDecisionType,
    MetaAgentClosure,
)
from maref.recursive.meta_governance import MetaBreakerState, MetaCircuitBreaker
from maref.recursive.tla_replay import TLAReplayValidator, TLAValidationReport

# ──────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────


def _make_snapshot(
    round_num: int,
    cycle_id: str = "c3",
    fnr: float = 0.05,
    fpr: float = 0.02,
    kl_drift: float = 0.01,
    perf_score: float = 0.95,
    gain_pct: float = 0.005,
    saturated: bool = False,
) -> ConvergenceSnapshot:
    return ConvergenceSnapshot(
        round_num=round_num,
        cycle_id=cycle_id,
        fnr=fnr,
        fpr=fpr,
        kl_drift=kl_drift,
        perf_score=perf_score,
        gain_pct=gain_pct,
        saturated=saturated,
    )


# ──────────────────────────────────────────────────────
# R251-R253: Convergence Dashboard
# ──────────────────────────────────────────────────────


class TestConvergenceDashboardWithSimulatedData:
    def test_dashboard_initializes_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))
            assert dashboard.snapshot_count == 0
            assert dashboard.compute_convergence_curves() == {}

    def test_record_and_compute_curves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(50):
                dashboard.record(
                    _make_snapshot(
                        round_num=r,
                        cycle_id="c3",
                        fnr=0.10 - 0.001 * r,
                        fpr=0.06 - 0.0005 * r,
                        kl_drift=0.05 - 0.0008 * r,
                        perf_score=0.80 + 0.002 * r,
                    )
                )

            assert dashboard.snapshot_count == 50
            curves = dashboard.compute_convergence_curves()
            assert "c3" in curves
            c3 = curves["c3"]
            assert len(c3["fnr"]) == 50
            assert len(c3["fpr"]) == 50
            assert len(c3["kl_drift"]) == 50
            assert len(c3["perf_score"]) == 50
            assert c3["fnr"][-1] < c3["fnr"][0]
            assert c3["perf_score"][-1] > c3["perf_score"][0]

    def test_multiple_cycles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(50):
                dashboard.record(
                    _make_snapshot(
                        round_num=r,
                        cycle_id="c1",
                        fnr=0.12,
                        fpr=0.07,
                        kl_drift=0.02,
                        perf_score=0.80,
                    )
                )
            for r in range(100):
                dashboard.record(
                    _make_snapshot(
                        round_num=r,
                        cycle_id="c2",
                        fnr=0.08,
                        fpr=0.04,
                        kl_drift=0.01,
                        perf_score=0.88,
                    )
                )
            for r in range(50):
                dashboard.record(
                    _make_snapshot(
                        round_num=r,
                        cycle_id="c3",
                        fnr=0.04,
                        fpr=0.02,
                        kl_drift=0.005,
                        perf_score=0.95,
                    )
                )

            curves = dashboard.compute_convergence_curves()
            assert len(curves) == 3
            assert set(curves.keys()) == {"c1", "c2", "c3"}

    def test_export_report_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(10):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3"))

            report = dashboard.export_report(format="markdown")
            assert "MAREF Convergence Report" in report
            assert "c3" in report
            assert "FNR" in report or "fnr" in report.lower()
            assert "Saturation Analysis" in report
            assert "Pareto Front" in report

    def test_export_report_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(5):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3"))

            report = dashboard.export_report(format="json")
            data = json.loads(report)
            assert "curves" in data
            assert "saturation" in data
            assert "pareto_front" in data

    def test_plot_convergence_returns_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(20):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3"))

            plot = dashboard.plot_convergence()
            assert isinstance(plot, str)
            assert "Convergence Dashboard" in plot
            assert "Total snapshots" in plot

    def test_pareto_front_returns_nondominated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            dashboard.record(
                _make_snapshot(
                    round_num=1, cycle_id="A", fnr=0.10, fpr=0.05, kl_drift=0.02, perf_score=0.85
                )
            )
            dashboard.record(
                _make_snapshot(
                    round_num=2, cycle_id="B", fnr=0.05, fpr=0.02, kl_drift=0.01, perf_score=0.95
                )
            )

            pareto = dashboard.compute_pareto_front()
            assert len(pareto) == 1
            assert pareto[0]["cycle_id"] == "B"

    def test_clear_removes_snapshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(5):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3"))
            assert dashboard.snapshot_count == 5

            dashboard.clear()
            assert dashboard.snapshot_count == 0
            assert not history.exists()


# ──────────────────────────────────────────────────────
# R252: Saturation Detection
# ──────────────────────────────────────────────────────


class TestSaturationDetection:
    def test_active_when_gains_above_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(10):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=0.01))

            result = dashboard.detect_saturation(sensitivity=0.003, windows=5)
            assert result["overall_saturated"] is False

    def test_saturated_when_gains_below_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(10):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=0.0001))

            result = dashboard.detect_saturation(sensitivity=0.003, windows=5)
            assert result["overall_saturated"] is True
            assert "c3" in result["saturated_cycles"]

    def test_not_saturated_with_insufficient_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(3):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=0.0001))

            result = dashboard.detect_saturation(sensitivity=0.003, windows=5)
            assert result["overall_saturated"] is False

    def test_decreasing_gains_detect_saturation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            gains = [0.05, 0.03, 0.01, 0.005, 0.002, 0.001, 0.0008, 0.0005, 0.0003, 0.0002]
            for r, g in enumerate(gains):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=g))

            result = dashboard.detect_saturation(sensitivity=0.003, windows=5)
            assert result["overall_saturated"] is True

    def test_strict_threshold_no_saturation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(10):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=0.002))

            result = dashboard.detect_saturation(sensitivity=0.001, windows=5)
            assert result["overall_saturated"] is False

    def test_relaxed_threshold_detects_saturation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "test_history.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(10):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c3", gain_pct=0.002))

            result = dashboard.detect_saturation(sensitivity=0.005, windows=5)
            assert result["overall_saturated"] is True


# ──────────────────────────────────────────────────────
# R253: TLA Replay with Mock State Sequences
# ──────────────────────────────────────────────────────


class TestTLAReplayWithMockStates:
    def test_lyapunov_convergence_true(self):
        validator = TLAReplayValidator()
        states = [
            {"fnr": 0.15, "fpr": 0.08, "entropy": 5, "kl_drift": 0.05},
            {"fnr": 0.12, "fpr": 0.06, "entropy": 4, "kl_drift": 0.04},
            {"fnr": 0.10, "fpr": 0.05, "entropy": 3, "kl_drift": 0.03},
            {"fnr": 0.08, "fpr": 0.04, "entropy": 2, "kl_drift": 0.02},
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
        ]
        assert validator.check_lyapunov(states) is True

    def test_lyapunov_violation_detected(self):
        validator = TLAReplayValidator()
        states = [
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
            {"fnr": 0.20, "fpr": 0.10, "entropy": 5, "kl_drift": 0.10},
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
            {"fnr": 0.20, "fpr": 0.10, "entropy": 5, "kl_drift": 0.10},
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
            {"fnr": 0.20, "fpr": 0.10, "entropy": 5, "kl_drift": 0.10},
            {"fnr": 0.05, "fpr": 0.03, "entropy": 1, "kl_drift": 0.01},
        ]
        assert validator.check_lyapunov(states) is False

    def test_lyapunov_single_state(self):
        validator = TLAReplayValidator()
        assert validator.check_lyapunov([{"fnr": 0.1}]) is True
        assert validator.check_lyapunov([]) is True

    def test_halt_absorption_stays_halted(self):
        validator = TLAReplayValidator()
        states = [
            {"state": "OBSERVE"},
            {"state": "ANALYZE"},
            {"state": "HALT"},
            {"state": "HALT"},
            {"state": "HALT"},
        ]
        assert validator.check_halt_absorption(states) is True

    def test_halt_absorption_violation(self):
        validator = TLAReplayValidator()
        states = [
            {"state": "OBSERVE"},
            {"state": "HALT"},
            {"state": "ANALYZE"},
        ]
        assert validator.check_halt_absorption(states) is False

    def test_halt_no_halt_state_found(self):
        validator = TLAReplayValidator()
        states = [
            {"state": "OBSERVE"},
            {"state": "ANALYZE"},
            {"state": "DECIDE"},
        ]
        assert validator.check_halt_absorption(states) is True

    def test_gray_code_single_bit_transitions(self):
        validator = TLAReplayValidator()
        states = [
            {"agent_state": 0b00000},
            {"agent_state": 0b00001},
            {"agent_state": 0b00011},
            {"agent_state": 0b00010},
        ]
        assert validator.check_gray_code_transitions(states) is True

    def test_gray_code_multi_bit_violation(self):
        validator = TLAReplayValidator()
        states = [
            {"agent_state": 0b00000},
            {"agent_state": 0b00111},
            {"agent_state": 0b11111},
        ]
        assert validator.check_gray_code_transitions(states) is False

    def test_gray_code_empty_sequence(self):
        validator = TLAReplayValidator()
        assert validator.check_gray_code_transitions([]) is True
        assert validator.check_gray_code_transitions([{"agent_state": 0b00001}]) is True

    def test_generate_validation_report_without_states(self):
        validator = TLAReplayValidator()
        report = validator.generate_validation_report()

        assert isinstance(report, TLAValidationReport)
        assert report.total_checks == 5
        assert report.passed == 0
        assert report.failed == 0
        assert report.all_passed is False
        assert len(report.checks) == 5
        for check in report.checks:
            assert check.passed is None

    def test_generate_validation_report_with_states(self):
        validator = TLAReplayValidator()
        states = [
            {"fnr": 0.1, "fpr": 0.05, "entropy": 1.0, "kl_drift": 0.01, "halt": False, "agent_state": 0b00000},
            {"fnr": 0.08, "fpr": 0.04, "entropy": 0.8, "kl_drift": 0.005, "halt": False, "agent_state": 0b00001},
            {"fnr": 0.06, "fpr": 0.03, "entropy": 0.5, "kl_drift": 0.002, "halt": True, "agent_state": 0b00011},
            {"fnr": 0.04, "fpr": 0.02, "entropy": 0.3, "kl_drift": 0.001, "halt": True, "agent_state": 0b00011},
        ]
        report = validator.generate_validation_report(states)

        assert isinstance(report, TLAValidationReport)
        assert report.total_checks == 5
        assert report.state_count == 4
        assert len(report.checks) == 5
        # SafetyGate and RedLine are structural — passed=None
        structural = {c.invariant_name for c in report.checks if c.passed is None}
        assert structural == {"SafetyGateIntegrity", "RedLineImmutability"}
        # Lyapunov, HALT, GrayCode should have real results
        runtime = {c.invariant_name for c in report.checks if c.passed is not None}
        assert runtime == {"LyapunovConvergence", "HALTAbsorbing", "GrayCodeTransition"}

    def test_validation_report_to_dict_without_states(self):
        validator = TLAReplayValidator()
        report = validator.generate_validation_report()
        d = report.to_dict()

        assert d["all_passed"] is False
        assert d["total_checks"] == 5
        assert d["passed"] == 0
        assert len(d["checks"]) == 5


# ──────────────────────────────────────────────────────
# R254-R255: MetaAgentClosure 5 Red Lines
# ──────────────────────────────────────────────────────


class TestMetaAgentClosureRedLines:
    """
    Test all 5 constitutional red lines with:
      - RL-001: No agent shall modify its own safety red lines
      - RL-002: No agent shall disable or bypass the safety gate
      - RL-003: No agent shall execute code without prior audit trail
      - RL-004: No agent shall clone itself without constitutional review
      - RL-005: No agent shall modify trust evaluation weights unilaterally
    """

    def closure(self) -> MetaAgentClosure:
        return MetaAgentClosure()

    def test_rl001_self_modification_blocked_3_attempts(self):
        closure = self.closure()
        agent_ids = ["agent_alpha", "agent_beta", "agent_gamma"]

        for agent_id in agent_ids:
            decision = closure.submit_decision(
                agent_id=agent_id,
                decision_type=EvolutionDecisionType.RED_LINE_MODIFICATION,
                description=f"Agent {agent_id} attempts to modify RL-001",
            )
            assert decision.red_line_violation is True
            assert "RL-001" in decision.violated_red_lines
            assert decision.status == "rejected"

        assert len(closure.get_decisions()) == 3

    def test_rl002_safety_gate_bypass_blocked_3_attempts(self):
        closure = self.closure()
        attempts = [
            "Attempt to disable safety gate for faster processing",
            "Remove safety gate to allow emergency changes",
            "Bypass the safety gate for this update",
        ]

        for i, desc in enumerate(attempts):
            decision = closure.submit_decision(
                agent_id=f"agent_{i}",
                decision_type=EvolutionDecisionType.POLICY_UPDATE,
                description=desc,
            )
            assert decision.red_line_violation is True, f"Attempt {i+1} should be blocked"
            assert "RL-002" in decision.violated_red_lines
            assert decision.status == "rejected"

    def test_rl003_code_execution_without_audit_trail_blocked_3_attempts(self):
        closure = self.closure()
        agent_ids = ["agent_x", "agent_y", "agent_z"]

        for agent_id in agent_ids:
            decision = closure.submit_decision_with_reviewers(
                agent_id=agent_id,
                decision_type=EvolutionDecisionType.CODE_CHANGE,
                description=f"Deploy code without auditor in review chain by {agent_id}",
                reviewers=["reviewer_no_audit"],
            )
            assert decision.red_line_violation is True
            assert "RL-003" in decision.violated_red_lines
            assert decision.status == "rejected"

    def test_rl004_self_cloning_without_review_blocked_3_attempts(self):
        closure = self.closure()
        agent_ids = ["agent_one", "agent_two", "agent_three"]

        for agent_id in agent_ids:
            decision = closure.submit_decision(
                agent_id=agent_id,
                decision_type=EvolutionDecisionType.AGENT_CLONE,
                description=f"Self-clone by {agent_id} without constitutional review",
            )
            assert decision.red_line_violation is True
            assert "RL-004" in decision.violated_red_lines
            assert decision.status == "rejected"

    def test_rl005_trust_weights_unilateral_modification_blocked_3_attempts(self):
        closure = self.closure()
        attempts = [
            "Change trust_weight to favor agent A",
            "Modify trust score weight unilaterally",
            "Update weight unilaterally for agent B",
        ]

        for i, desc in enumerate(attempts):
            decision = closure.submit_decision(
                agent_id=f"agent_{i}",
                decision_type=EvolutionDecisionType.POLICY_UPDATE,
                description=desc,
            )
            assert decision.red_line_violation is True
            assert "RL-005" in decision.violated_red_lines
            assert decision.status == "rejected"

    def test_all_red_lines_100_pct_blocked(self):
        closure = self.closure()
        total_attempts = 0
        total_blocked = 0

        test_configs = [
            (EvolutionDecisionType.RED_LINE_MODIFICATION, "Modify RL-001", "RL-001", None),
            (EvolutionDecisionType.POLICY_UPDATE, "Disable safety gate", "RL-002", None),
            (EvolutionDecisionType.CODE_CHANGE, "Run code without audit", "RL-003", ["reviewer"]),
            (EvolutionDecisionType.AGENT_CLONE, "Clone without review", "RL-004", None),
            (EvolutionDecisionType.POLICY_UPDATE, "Change trust_weight to 0.9", "RL-005", None),
        ]

        for agent_num in range(3):
            for dt, desc, rl_id, reviewers in test_configs:
                total_attempts += 1
                if reviewers:
                    decision = closure.submit_decision_with_reviewers(
                        agent_id=f"test_agent_{agent_num}",
                        decision_type=dt,
                        description=f"{desc} (attempt {agent_num + 1})",
                        reviewers=reviewers,
                    )
                else:
                    decision = closure.submit_decision(
                        agent_id=f"test_agent_{agent_num}",
                        decision_type=dt,
                        description=f"{desc} (attempt {agent_num + 1})",
                    )
                if decision.red_line_violation and decision.status == "rejected":
                    total_blocked += 1

        assert total_attempts == 15
        assert total_blocked == total_attempts

    def test_red_lines_immutable_property(self):
        closure = self.closure()
        red_lines = closure.get_red_lines()

        for rl in red_lines:
            assert rl.immutable is True

    def test_non_red_line_decision_passes(self):
        closure = self.closure()

        decision = closure.submit_decision(
            agent_id="agent_safe",
            decision_type=EvolutionDecisionType.CAPABILITY_ADDITION,
            description="Add new monitoring capability",
        )
        assert decision.red_line_violation is False
        assert decision.status == "approved"


# ──────────────────────────────────────────────────────
# R256: MetaCircuitBreaker Cascade
# ──────────────────────────────────────────────────────


class TestMetaCircuitBreakerCascade:
    def test_initial_state_is_closed(self):
        cb = MetaCircuitBreaker()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_trips_open_after_threshold(self):
        cb = MetaCircuitBreaker(inner_trip_threshold=3)
        cb.record_trip()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 1

        cb.record_trip()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 2

        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN
        assert cb.inner_trip_count == 3

    def test_try_half_open_after_cooldown(self):
        import time

        cb = MetaCircuitBreaker(inner_trip_threshold=1, cooldown_seconds=0.0)
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

        time.sleep(0.001)
        result = cb.try_half_open()
        assert result is True
        assert cb.state == MetaBreakerState.HALF_OPEN

    def test_try_half_open_before_cooldown_fails(self):
        cb = MetaCircuitBreaker(inner_trip_threshold=1, cooldown_seconds=999999.0)
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

        result = cb.try_half_open()
        assert result is False
        assert cb.state == MetaBreakerState.OPEN

    def test_close_from_half_open(self):
        cb = MetaCircuitBreaker(inner_trip_threshold=1, cooldown_seconds=0.0)
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

        cb.try_half_open()
        assert cb.state == MetaBreakerState.HALF_OPEN

        cb.close()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_full_cascade_open_half_open_closed(self):
        import time

        cb = MetaCircuitBreaker(inner_trip_threshold=2, cooldown_seconds=0.0)

        cb.record_trip()
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

        time.sleep(0.001)
        assert cb.try_half_open() is True
        assert cb.state == MetaBreakerState.HALF_OPEN

        cb.close()
        assert cb.state == MetaBreakerState.CLOSED
        assert cb.inner_trip_count == 0

    def test_fail_half_open_reopens(self):
        import time

        cb = MetaCircuitBreaker(inner_trip_threshold=1, cooldown_seconds=0.0)
        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN

        time.sleep(0.001)
        cb.try_half_open()
        assert cb.state == MetaBreakerState.HALF_OPEN

        cb.fail_half_open()
        assert cb.state == MetaBreakerState.OPEN

    def test_cascade_with_custom_threshold(self):
        cb = MetaCircuitBreaker(inner_trip_threshold=5)
        for _ in range(4):
            cb.record_trip()
            assert cb.state == MetaBreakerState.CLOSED

        cb.record_trip()
        assert cb.state == MetaBreakerState.OPEN


# ──────────────────────────────────────────────────────
# R257: EvolutionDSL SafetyGate Constraints
# ──────────────────────────────────────────────────────


class TestEvolutionDSLSafetyGateConstraints:
    def test_safety_gate_default_parameters(self):
        gate = SafetyGate()
        assert gate.min_test_pass_rate == 0.95
        assert gate.max_coverage_drop_pct == 2.0
        assert gate.max_perf_regression_pct == 5.0
        assert gate.require_sandbox_simulation is True
        assert gate.forbid_core_removal is True

    def test_forbid_core_circuit_breaker_removal(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        bad_rule = EvolutionRule(
            rule_id="r1",
            target="circuit_breaker",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(bad_rule)
        assert result.passed is False
        assert "forbid_core_removal" in result.rejection_reason

    def test_forbid_core_state_machine_removal(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        bad_rule = EvolutionRule(
            rule_id="r2",
            target="state_machine",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(bad_rule)
        assert result.passed is False
        assert "forbid_core_removal" in result.rejection_reason

    def test_forbid_core_audit_logger_removal(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        bad_rule = EvolutionRule(
            rule_id="r3",
            target="audit_logger",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(bad_rule)
        assert result.passed is False
        assert "forbid_core_removal" in result.rejection_reason

    def test_non_core_removal_passes(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r4",
            target="unused_module",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(rule)
        assert result.passed is True

    def test_below_min_test_pass_rate_fails(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r5",
            target="some_config",
            current_value=0.5,
            proposed_value=0.4,
        )
        metrics = {
            "test_pass_rate": 0.80,
            "coverage_pct": 95.0,
            "baseline_coverage_pct": 95.0,
            "perf_regression_pct": 0.0,
        }
        result = gate.evaluate(rule, metrics)
        assert result.passed is False
        assert "test_pass_rate" in result.rejection_reason

    def test_below_min_test_pass_rate_edge_case(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r6",
            target="some_config",
            current_value=0.5,
            proposed_value=0.4,
        )
        metrics = {
            "test_pass_rate": 0.95,
            "coverage_pct": 95.0,
            "baseline_coverage_pct": 95.0,
            "perf_regression_pct": 0.0,
        }
        result = gate.evaluate(rule, metrics)
        assert result.passed is True

    def test_coverage_drop_exceeds_max_fails(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r7",
            target="some_config",
            current_value=0.5,
            proposed_value=0.4,
        )
        metrics = {
            "test_pass_rate": 1.0,
            "coverage_pct": 92.0,
            "baseline_coverage_pct": 95.5,
            "perf_regression_pct": 0.0,
        }
        result = gate.evaluate(rule, metrics)
        assert result.passed is False
        assert "coverage_drop" in result.rejection_reason

    def test_perf_regression_exceeds_max_fails(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r8",
            target="some_config",
            current_value=0.5,
            proposed_value=0.4,
        )
        metrics = {
            "test_pass_rate": 1.0,
            "coverage_pct": 95.0,
            "baseline_coverage_pct": 95.0,
            "perf_regression_pct": 7.0,
        }
        result = gate.evaluate(rule, metrics)
        assert result.passed is False
        assert "perf_regression" in result.rejection_reason

    def test_all_metrics_pass_succeeds(self):
        dsl = EvolutionDSL()
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r9",
            target="some_config",
            current_value=0.5,
            proposed_value=0.6,
        )
        metrics = {
            "test_pass_rate": 0.98,
            "coverage_pct": 96.0,
            "baseline_coverage_pct": 95.5,
            "perf_regression_pct": 1.0,
        }
        result = gate.evaluate(rule, metrics)
        assert result.passed is True
        assert result.risk_assessment == "LOW"

    def test_proposed_value_none_with_no_core_violation_passes(self):
        gate = SafetyGate()
        rule = EvolutionRule(
            rule_id="r10",
            target="unrelated_config",
            current_value=True,
            proposed_value=None,
        )
        result = gate.evaluate(rule)
        assert result.passed is True
        assert result.risk_assessment == "LOW"

    def test_dsl_apply_chain_with_safety_gate(self):
        from maref.recursive.evolution_dsl import EvolutionRule, SafetyGate

        bad_rule = EvolutionRule(
            rule_id="test_core_removal",
            target="circuit_breaker",
            current_value=True,
            proposed_value=None,
            justification="Remove core component",
        )
        gate = SafetyGate()
        result = gate.evaluate(bad_rule)
        assert result.passed is False

    def test_dsl_apply_chain_valid_rule(self):
        dsl = EvolutionDSL()
        good_rule = dsl.propose(
            target="logging_threshold",
            current_value="INFO",
            proposed_value="DEBUG",
            justification="Increase verbosity",
        )
        result = dsl.apply(good_rule)
        assert result.applied is True

    def test_safety_gate_rejects_all_core_components(self):
        gate = SafetyGate()
        cores = ["circuit_breaker", "state_machine", "audit_logger"]
        for core in cores:
            rule = EvolutionRule(
                rule_id=f"remove_{core}",
                target=core,
                current_value=True,
                proposed_value=None,
            )
            result = gate.evaluate(rule)
            assert result.passed is False, f"Should block removal of {core}"

    def test_rule_count_increases(self):
        dsl = EvolutionDSL()
        assert dsl.rule_count() == 0
        dsl.load_default_rules()
        assert dsl.rule_count() == 6


# ──────────────────────────────────────────────────────
# Edge Cases & Integration
# ──────────────────────────────────────────────────────


class TestConvergenceEdgeCases:
    def test_dashboard_reloads_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "reload_test.jsonl"

            dash1 = ConvergenceDashboard(history_path=str(history))
            for r in range(5):
                dash1.record(_make_snapshot(round_num=r, cycle_id="c3"))
            assert dash1.snapshot_count == 5

            dash2 = ConvergenceDashboard(history_path=str(history))
            assert dash2.snapshot_count == 5

    def test_dashboard_records_multiple_cycles_interleaved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history = Path(tmpdir) / "interleaved.jsonl"
            dashboard = ConvergenceDashboard(history_path=str(history))

            for r in range(3):
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c1"))
                dashboard.record(_make_snapshot(round_num=r, cycle_id="c2"))

            curves = dashboard.compute_convergence_curves()
            assert len(curves) == 2
            assert len(curves["c1"]["fnr"]) == 3
            assert len(curves["c2"]["fnr"]) == 3

    def test_tla_validation_report_all_checks_named(self):
        validator = TLAReplayValidator()
        report = validator.generate_validation_report()
        names = {c.invariant_name for c in report.checks}
        assert "LyapunovConvergence" in names
        assert "HALTAbsorbing" in names
        assert "GrayCodeTransition" in names
        assert "SafetyGateIntegrity" in names
        assert "RedLineImmutability" in names

    def test_spec_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = Path(tmpdir) / "custom_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "version": "0.24.0",
                        "invariants": [{"name": "TestInvariant", "description": "Test only"}],
                    }
                )
            )

            validator = TLAReplayValidator(tla_spec_path=str(spec_path))
            report = validator.generate_validation_report()
            assert report.total_checks == 1
            assert report.checks[0].invariant_name == "TestInvariant"
