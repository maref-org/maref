"""方案 C：Agent-as-a-Judge 真实化测试。

覆盖：轨迹仲裁（越权 BLOCK / 风险 FLAG / 正常 PASS）、证据溯源、
多法官加权共识、单法官故障降级、向后兼容仿真路径。
"""

from __future__ import annotations

from maref.governance.judge import ProviderJudge, RuleJudge
from maref.governance.trace import Trace, TraceStep, VerdictDecision
from maref.governance.verifier_consensus import ConsensusStrategy, VerifierConsensus
from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry


def _trace_with(actions: list[tuple[str, str]]) -> Trace:
    trace = Trace(trace_id="t1", agent_id="agent-a")
    for action, decision in actions:
        trace.add_step(TraceStep(agent_id="agent-a", action=action, decision=decision))
    return trace


class TestRuleJudge:
    def test_pass_on_normal_trace(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("file.read", "allowed"), ("network.observe", "allowed")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS
        assert verdict.evidence_refs == []

    def test_block_on_bypass(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("file.read", "allowed"), ("governance.override_deny", "forced")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK
        assert len(verdict.evidence_refs) >= 1
        assert "override_deny" in verdict.evidence_refs[0]

    def test_block_on_exfiltration(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("network.exfiltrate", "sent")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK
        assert verdict.confidence >= 0.9

    def test_flag_on_degraded(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("retry", "circuit_breaker_trip")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.FLAG


class TestConsensusWithJudges:
    def test_block_consensus_blocks_trace(self) -> None:
        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="j1", model="rule", methodology="trace", accuracy=0.9))
        reg.register(VerifierEntry(name="j2", model="rule", methodology="trace", accuracy=0.8))
        consensus = VerifierConsensus(reg, judges={
            "j1": RuleJudge(),
            "j2": RuleJudge(),
        })
        trace = _trace_with([("file.read", "allowed"), ("privilege_escalation", "attempted")])
        result = consensus.evaluate(trace)
        assert result.passed is False
        assert len(result.votes) == 2
        assert all(v["approved"] is False for v in result.votes)

    def test_verdict_schema_passthrough(self) -> None:
        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="j1", model="rule", methodology="trace", accuracy=0.9))
        schema = {"required_decision": "block"}
        consensus = VerifierConsensus(reg, judges={"j1": RuleJudge()})
        trace = _trace_with([("exfiltrate", "sent")])
        result = consensus.evaluate(trace, verdict_schema=schema)
        assert result.passed is False

    def test_judge_failure_degrades_to_consensus(self) -> None:
        """单法官抛异常不应中断整体共识（容错降级）。"""
        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="good", model="rule", methodology="trace", accuracy=0.9))
        reg.register(VerifierEntry(name="bad", model="broken", methodology="trace", accuracy=0.1))
        consensus = VerifierConsensus(reg, judges={
            "good": RuleJudge(),
            "bad": None,  # 未注入法官 → 走仿真路径
        })
        trace = _trace_with([("file.read", "allowed")])
        result = consensus.evaluate(trace)
        # good 法官 PASS；bad 走仿真（accuracy 0.1 → 反选 → False）
        assert result.votes[0]["approved"] is True
        assert result.votes[1]["approved"] is False

    def test_judge_exception_fails_closed_without_aborting(self) -> None:
        """注入的法官 arbitrate 抛异常 → fail-closed 拒绝且不中断共识。"""
        class ExplodingJudge:
            name = "exploding"

            def arbitrate(self, trace, verdict_schema=None):
                raise RuntimeError("judge crashed")

        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="stable", model="rule", methodology="trace", accuracy=0.9))
        reg.register(VerifierEntry(name="exploding", model="llm", methodology="trace", accuracy=0.9))
        consensus = VerifierConsensus(reg, judges={
            "stable": RuleJudge(),
            "exploding": ExplodingJudge(),
        })
        trace = _trace_with([("file.read", "allowed")])
        result = consensus.evaluate(trace)
        # stable PASS、exploding fail-closed False
        assert len(result.votes) == 2
        assert result.votes[0]["approved"] is True
        assert result.votes[1]["approved"] is False
        assert result.votes[1]["verdict"]["error"] == "judge_failed"

    def test_verdict_evidence_exposed_in_votes(self) -> None:
        """法官裁决的证据引用应透出到共识 votes（可溯源）。"""
        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="j1", model="rule", methodology="trace", accuracy=0.9))
        consensus = VerifierConsensus(reg, judges={"j1": RuleJudge()})
        trace = _trace_with([("exfiltrate", "sent")])
        result = consensus.evaluate(trace)
        verdict = result.votes[0]["verdict"]
        assert verdict["decision"] == "block"
        assert len(verdict["evidence_refs"]) >= 1
        assert verdict["reasoning"]


class TestProviderJudge:
    def test_provider_verdict_mapped(self) -> None:
        class FakeProvider:
            def arbitrate(self, trace: Trace, verdict_schema=None) -> dict:
                return {
                    "decision": "flag",
                    "reasoning": "suspicious pattern",
                    "evidence_refs": ["ref-1"],
                    "confidence": 0.7,
                }

        judge = ProviderJudge(FakeProvider())
        trace = _trace_with([("file.read", "allowed")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.FLAG
        assert verdict.evidence_refs == ["ref-1"]
        assert verdict.confidence == 0.7


class TestTraceModel:
    def test_trace_to_dict(self) -> None:
        trace = _trace_with([("file.read", "allowed")])
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["action"] == "file.read"

    def test_trace_size(self) -> None:
        trace = _trace_with([("a", "b"), ("c", "d")])
        assert trace.size == 2


class TestBackwardCompat:
    def test_bool_item_still_uses_simulation(self) -> None:
        """未注入法官时，布尔输入保持既有仿真行为。"""
        reg = VerifierRegistry()
        reg.register(VerifierEntry(name="v1", model="gpt-4", methodology="cross-check", accuracy=0.9))
        consensus = VerifierConsensus(reg)
        result = consensus.evaluate(True)
        assert result.passed
        result = consensus.evaluate(False, strategy=ConsensusStrategy.UNANIMITY)
        assert result.passed is False
