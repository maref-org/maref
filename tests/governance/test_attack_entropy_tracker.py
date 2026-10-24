"""T-P0-2：攻击分布熵跟踪器测试。

依据：不可能锁（arXiv 2608.01388）——攻击分布熵上升说明攻击模式多样化，
规则集覆盖不足，应触发不变量进化（RSI 变异对象 = 不变量集）。
"""

from __future__ import annotations

import math

from maref.governance.judge import AttackEntropyTracker, RuleJudge
from maref.governance.trace import Trace, TraceStep, VerdictDecision


def _trace_with(actions: list[tuple[str, str]]) -> Trace:
    trace = Trace(trace_id="t1", agent_id="agent-a")
    for action, decision in actions:
        trace.add_step(TraceStep(agent_id="agent-a", action=action, decision=decision))
    return trace


class TestAttackEntropyTracker:
    def test_empty_tracker(self) -> None:
        t = AttackEntropyTracker()
        assert t.entropy() == 0.0
        assert t.normalized_entropy() == 0.0
        assert t.observed_classes() == 0
        assert t.should_evolve() is False

    def test_single_class_normalized_zero(self) -> None:
        t = AttackEntropyTracker()
        t.record(["block:bypass"] * 10)
        assert t.observed_classes() == 1
        assert t.entropy() == 0.0
        assert t.normalized_entropy() == 0.0
        assert t.should_evolve() is False

    def test_uniform_two_classes_normalized_one(self) -> None:
        t = AttackEntropyTracker()
        t.record(["block:bypass", "flag:retry"])
        assert t.observed_classes() == 2
        assert math.isclose(t.entropy(), 1.0, abs_tol=1e-9)
        assert math.isclose(t.normalized_entropy(), 1.0, abs_tol=1e-9)
        assert t.should_evolve() is True

    def test_skewed_distribution_below_threshold(self) -> None:
        t = AttackEntropyTracker(evolve_threshold=0.85)
        t.record(["a"] * 9 + ["b"] * 1)
        assert t.observed_classes() == 2
        assert 0.0 < t.normalized_entropy() < 0.85
        assert t.should_evolve() is False

    def test_snapshot_shape(self) -> None:
        t = AttackEntropyTracker()
        t.record(["a", "b"])
        snap = t.snapshot()
        for key in (
            "entropy_bits",
            "normalized_entropy",
            "observed_classes",
            "total_hits",
            "evolve_threshold",
            "should_evolve",
        ):
            assert key in snap
        assert snap["total_hits"] == 2


class TestRuleJudgeEntropyIntegration:
    def test_backward_compatible_no_args(self) -> None:
        judge = RuleJudge()
        verdict = judge.arbitrate(_trace_with([("read", "ok")]))
        assert verdict.decision == VerdictDecision.PASS
        assert judge.entropy_snapshot()["total_hits"] == 0

    def test_hits_recorded(self) -> None:
        judge = RuleJudge()
        judge.arbitrate(_trace_with([("bypass", "attempt")]))
        snap = judge.entropy_snapshot()
        assert snap["total_hits"] == 1
        assert snap["observed_classes"] == 1

    def test_diverse_attacks_trigger_evolve(self) -> None:
        judge = RuleJudge()
        judge.arbitrate(_trace_with([("bypass", "x")]))
        judge.arbitrate(_trace_with([("retry", "x")]))
        snap = judge.entropy_snapshot()
        assert snap["observed_classes"] == 2
        assert snap["should_evolve"] is True

    def test_custom_tracker_injected(self) -> None:
        tracker = AttackEntropyTracker(evolve_threshold=0.1)
        judge = RuleJudge(entropy_tracker=tracker)
        judge.arbitrate(_trace_with([("bypass", "x")]))
        assert tracker.observed_classes() == 1
        assert judge.entropy_snapshot()["evolve_threshold"] == 0.1
