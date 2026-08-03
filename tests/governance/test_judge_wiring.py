"""v0.47 S13 — Agent-as-a-Judge 真实接线.

1. ``VerifierConsensus.record_call(name, correct)`` writes back accuracy
   calibration after a Trace adjudication.
2. ``MAREFLoop`` wires ``RuleJudge`` into its consensus so trace inputs are
   genuinely adjudicated (not the simulated vote fallback).
3. ``ConvergentLoop`` submits a ``Trace`` for adjudication when the
   evaluator is a judge-wired ``VerifierConsensus``.
"""

from __future__ import annotations

from typing import Any

from maref.governance.judge import RuleJudge
from maref.governance.trace import Trace, TraceStep
from maref.governance.verifier_consensus import (
    ConsensusStrategy,
    ConsensusResult,
    VerifierConsensus,
)
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry


def _registry_with(name: str = "judge-1", accuracy: float = 0.5) -> VerifierRegistry:
    reg = VerifierRegistry()
    reg.register(VerifierEntry(name=name, model="m", methodology="mm", accuracy=accuracy))
    return reg


def _blocking_trace() -> Trace:
    """A trace whose steps hit a BLOCK pattern (e.g. 'bypass')."""
    trace = Trace(trace_id="t1", agent_id="agent-1")
    trace.add_step(
        TraceStep(agent_id="agent-1", action="network.scan", decision="bypass")
    )
    return trace


class TestRecordCall:
    def test_record_call_updates_accuracy(self) -> None:
        reg = _registry_with(accuracy=0.5)
        consensus = VerifierConsensus(reg)
        consensus.record_call("judge-1", correct=True)
        assert reg.get_accuracy("judge-1") > 0.5
        consensus.record_call("judge-1", correct=False)
        assert reg.get_accuracy("judge-1") < 0.5 + 0.01  # corrected down

    def test_record_call_unknown_verifier_noop(self) -> None:
        reg = _registry_with()
        consensus = VerifierConsensus(reg)
        consensus.record_call("nonexistent", correct=True)  # must not raise
        assert reg.get_accuracy("judge-1") == 0.5


class TestMAREFLoopJudgeWiring:
    def test_maref_loop_wires_rule_judge(self) -> None:
        from maref.integration.maref_loop_adapter import MAREFLoop

        loop = MAREFLoop()
        loop.register_verifier("judge-1", model="m", methodology="mm", accuracy=0.5)
        assert loop._consensus.has_judges is True

    def test_maref_loop_adjudicates_blocking_trace(self) -> None:
        from maref.integration.maref_loop_adapter import MAREFLoop

        loop = MAREFLoop()
        loop.register_verifier("judge-1", model="m", methodology="mm", accuracy=0.5)
        result = loop._consensus.evaluate(
            _blocking_trace(),
            strategy=ConsensusStrategy.WEIGHTED_MAJORITY,
        )
        assert result.passed is False  # BLOCK pattern → rejected


class TestConvergentJudgeAdjudication:
    def test_convergent_submits_trace_to_judged_consensus(self) -> None:
        from maref.loop.convergent import ConvergentLoop

        reg = _registry_with()
        consensus = VerifierConsensus(reg, judges={"judge-1": RuleJudge()})
        loop = ConvergentLoop(execute_fn=lambda x: "output", evaluator=consensus)
        result = loop._evaluate(_blocking_trace())
        # RuleJudge BLOCKs the bypass trace → consensus agreement is low/0.
        assert result.score < 0.5

    def test_convergent_dict_evaluator_backward_compatible(self) -> None:
        from maref.loop.convergent import ConvergentLoop

        loop = ConvergentLoop(execute_fn=lambda x: "output", evaluator=lambda o: type(
            "ER", (), {"score": 0.8, "errors": [], "improvement": 0.1}
        )())
        result = loop._evaluate("anything")
        assert result.score == 0.8
