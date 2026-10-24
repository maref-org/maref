"""PredictiveBreaker 单元测试 — DTMC/PCTL/PAC 前瞻熔断.

覆盖：合法/非法转移过滤、Laplace 平滑、吸收态、PCTL 可达概率、
PAC 误差界、期望吸收步数、前置干预判定、审计日志解析。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from maref.governance.constants import compute_valid_transitions
from maref.governance.predictive_breaker import PredictiveBreaker, PreemptionDecision
from maref.governance.types import GovernanceState, StateTransition


class TestFitting:
    def test_observe_accepts_legal_transition(self) -> None:
        pb = PredictiveBreaker()
        assert pb.observe(GovernanceState.INIT, GovernanceState.OBSERVE) is True
        assert pb.sample_count == 1
        assert pb.fitted is True

    def test_observe_rejects_illegal_transition(self) -> None:
        pb = PredictiveBreaker()
        # INIT(0000) -> HALT(1101) 汉明距离 3，非单比特，非法
        assert pb.observe(GovernanceState.INIT, GovernanceState.HALT) is False
        assert pb.sample_count == 0
        assert pb.fitted is False

    def test_halt_self_loop_accepted(self) -> None:
        pb = PredictiveBreaker()
        assert pb.observe(GovernanceState.HALT, GovernanceState.HALT) is True

    def test_fit_returns_accepted_count(self) -> None:
        pb = PredictiveBreaker()
        assert pb.fit([(0, 1), (1, 2), (0, 9)]) == 2

    def test_fit_from_records(self) -> None:
        pb = PredictiveBreaker()
        records = [
            {"event_type": "state_transition", "metadata": {"from_state_id": 4, "to_state_id": 5}},
            {"event_type": "other", "metadata": {"from_state_id": 1, "to_state_id": 2}},
            {"event_type": "state_transition", "metadata": {"from_state_id": 5, "to_state_id": 6}},
        ]
        assert pb.fit_from_records(records) == 2

    def test_fit_from_audit_log_skips_malformed_lines(self, tmp_path: Path) -> None:
        log = tmp_path / "governance_audit.jsonl"
        lines = [
            json.dumps(
                {
                    "event_type": "state_transition",
                    "metadata": {"from_state_id": 1, "to_state_id": 2},
                }
            ),
            "not-json",
            json.dumps(
                {
                    "event_type": "state_transition",
                    "metadata": {"from_state_id": 2, "to_state_id": 3},
                }
            ),
        ]
        log.write_text("\n".join(lines), encoding="utf-8")
        pb = PredictiveBreaker.from_audit_log(log)
        assert pb.sample_count == 2

    def test_fit_from_missing_log_is_noop(self, tmp_path: Path) -> None:
        pb = PredictiveBreaker.from_audit_log(tmp_path / "absent.jsonl")
        assert pb.sample_count == 0


class TestTransitionMatrix:
    def test_rows_are_stochastic(self) -> None:
        pb = PredictiveBreaker.from_transitions([(0, 1), (1, 2), (2, 3)])
        for row in pb.transition_matrix():
            assert abs(sum(row) - 1.0) < 1e-9

    def test_illegal_entries_are_zero(self) -> None:
        pb = PredictiveBreaker.from_transitions([(0, 1)])
        matrix = pb.transition_matrix()
        assert matrix[0][9] == 0.0

    def test_halt_is_absorbing(self) -> None:
        pb = PredictiveBreaker.from_transitions([(4, 5)])
        matrix = pb.transition_matrix()
        assert matrix[9][9] == 1.0
        assert sum(matrix[9]) == 1.0

    def test_laplace_smoothing_spreads_over_legal_edges(self) -> None:
        pb = PredictiveBreaker()
        pb.observe(0, 1)
        row = pb.transition_matrix()[0]
        legal = compute_valid_transitions()[0]
        for successor in legal:
            assert row[successor] > 0.0
        assert abs(sum(row[successor] for successor in legal) - 1.0) < 1e-9


class TestProbReach:
    def test_already_at_target(self) -> None:
        pb = PredictiveBreaker.from_transitions([(0, 1)])
        estimate, upper = pb.prob_reach(GovernanceState.HALT, GovernanceState.HALT, 3)
        assert estimate == 1.0
        assert upper == 1.0

    def test_learned_bias_raises_reachability(self) -> None:
        pb = PredictiveBreaker()
        for _ in range(500):
            pb.observe(8, 9)
        estimate, upper = pb.prob_reach(8, 9, 1)
        assert estimate > 0.9
        assert upper >= estimate

    def test_no_path_yields_zero(self) -> None:
        pb = PredictiveBreaker()
        pb.observe(0, 1)
        estimate, _ = pb.prob_reach(0, None, 1)
        assert estimate == 0.0

    def test_multi_step_horizon_non_decreasing(self) -> None:
        pb = PredictiveBreaker.from_transitions([(7, 8), (8, 9)])
        short, _ = pb.prob_reach(7, 9, 1)
        long, _ = pb.prob_reach(7, 9, 2)
        assert long >= short


class TestPACBound:
    def test_unobserved_state_has_max_epsilon(self) -> None:
        pb = PredictiveBreaker()
        assert pb.pac_epsilon(0) == 1.0

    def test_epsilon_shrinks_with_samples(self) -> None:
        pb = PredictiveBreaker()
        for _ in range(10):
            pb.observe(0, 1)
        epsilon_small = pb.pac_epsilon(0)
        for _ in range(990):
            pb.observe(0, 1)
        epsilon_large = pb.pac_epsilon(0)
        assert epsilon_large < epsilon_small < 1.0

    def test_upper_bound_not_below_estimate(self) -> None:
        pb = PredictiveBreaker.from_transitions([(8, 9)])
        estimate, upper = pb.prob_reach(8, 9, 1)
        assert upper >= estimate


class TestExpectedSteps:
    def test_expected_steps_finite_and_at_least_one(self) -> None:
        pb = PredictiveBreaker()
        for _ in range(1000):
            pb.observe(8, 9)
        steps = pb.expected_steps_to_halt()
        assert GovernanceState.HALT not in steps
        value = steps[GovernanceState.REPORT]
        assert not math.isinf(value)
        assert value >= 1.0

    def test_reachable_from_all_transient_states(self) -> None:
        pb = PredictiveBreaker.from_transitions([(0, 1), (1, 2), (2, 3)])
        steps = pb.expected_steps_to_halt()
        assert len(steps) == len(GovernanceState) - 1


class TestPreemption:
    def test_preempt_when_probability_exceeds_threshold(self) -> None:
        pb = PredictiveBreaker(threshold=0.3)
        for _ in range(200):
            pb.observe(8, 9)
        decision = pb.should_preempt(8, threshold=0.3, horizon=1)
        assert decision.preempt is True
        assert "HALT" in decision.reason

    def test_no_preempt_when_probability_below_threshold(self) -> None:
        pb = PredictiveBreaker()
        decision = pb.should_preempt(0, threshold=0.9, horizon=1)
        assert decision.preempt is False
        assert decision.reason == ""

    def test_decision_serializable(self) -> None:
        pb = PredictiveBreaker()
        decision = pb.should_preempt(0)
        assert isinstance(decision, PreemptionDecision)
        payload = decision.to_dict()
        assert payload["state"] == "INIT"
        assert payload["horizon"] == 5


class TestRiskReport:
    def test_report_covers_all_states(self) -> None:
        pb = PredictiveBreaker.from_transitions([(0, 1), (1, 2)])
        report = pb.risk_report()
        assert report["target"] == "HALT"
        assert len(report["states"]) == len(GovernanceState)
        assert {"state", "prob_reach", "pac_upper", "expected_steps_to_halt"} <= set(
            report["states"][0]
        )


class TestValidation:
    def test_invalid_horizon(self) -> None:
        with pytest.raises(ValueError):
            PredictiveBreaker(horizon=0)

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            PredictiveBreaker(threshold=1.5)

    def test_invalid_delta(self) -> None:
        with pytest.raises(ValueError):
            PredictiveBreaker(pac_delta=0.0)

    def test_invalid_state_raises(self) -> None:
        pb = PredictiveBreaker()
        with pytest.raises(ValueError):
            pb.prob_reach("INIT")  # type: ignore[arg-type]


class _FakeStateMachine:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def add_callback(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def remove_callback(self, callback: Any) -> None:
        self.callbacks.remove(callback)


class TestOnlineAttachment:
    def test_observe_event_accepts_legal(self) -> None:
        pb = PredictiveBreaker()
        event = StateTransition(from_state=GovernanceState.INIT, to_state=GovernanceState.OBSERVE)
        assert pb.observe_event(event) is True
        assert pb.sample_count == 1

    def test_observe_event_rejects_illegal(self) -> None:
        pb = PredictiveBreaker()
        event = StateTransition(from_state=GovernanceState.INIT, to_state=GovernanceState.HALT)
        assert pb.observe_event(event) is False

    def test_attach_registers_and_learns(self) -> None:
        pb = PredictiveBreaker()
        host = _FakeStateMachine()
        pb.attach(host)
        assert len(host.callbacks) == 1
        host.callbacks[0](StateTransition(GovernanceState.INIT, GovernanceState.OBSERVE))
        assert pb.sample_count == 1

    def test_detach_removes_callback(self) -> None:
        pb = PredictiveBreaker()
        host = _FakeStateMachine()
        pb.attach(host)
        pb.detach(host)
        assert host.callbacks == []
