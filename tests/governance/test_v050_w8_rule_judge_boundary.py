"""
v0.50 W8 — 评审与规则补强（A11 词边界 + A10 无官时 fail-closed）

W8-S1 (A11) RuleJudge 词边界精确匹配：
- 子串不再误报：`privilege` 不命中 `privilege_escalation`、`bypass` 不命中
  `bypassable`（原 `pattern in blob` 子串匹配存在误报）
- 精确 token 命中：独立词 `bypass`、`exfiltrate` 仍 BLOCK
- 下划线复合词：`escalation_privilege` 作为一个 token 精确匹配
- 中文模式支持：中文字符串 pattern 可命中
- 否定语境：`not_bypass` 不误报

W8-S2 (A10) VerifierConsensus 无官时 fail-closed：
- 未装配任何 judge 时，非 Trace 输入不再走确定性仿真（ground_truth 表决
  可被构造输入操纵），一律返回 passed=False + error 标记
- 装配 judge 后，Trace 输入走真实仲裁
"""

from __future__ import annotations

from typing import Any

from maref.governance.judge import RuleJudge
from maref.governance.trace import Trace, TraceStep, VerdictDecision


def _trace_with(actions: list[tuple[str, str]]) -> Trace:
    trace = Trace(trace_id="t1", agent_id="agent-a")
    for action, decision in actions:
        trace.add_step(TraceStep(agent_id="agent-a", action=action, decision=decision))
    return trace


class TestW8SubstringNoFalsePositive:
    def test_privilege_not_match_privilege_escalation_token(self) -> None:
        judge = RuleJudge()
        # "privilege_escalation" 是整体 token，不应命中独立 pattern "privilege"
        trace = _trace_with([("file.read", "privilege_escalation")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS

    def test_bypass_not_match_bypassable(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("network.route", "bypassable")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS

    def test_retry_not_match_retrying(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("queue.worker", "retrying")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS

    def test_negation_context_not_flagged(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("file.read", "not_bypass")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS


class TestW8ExactTokenHit:
    def test_exact_bypass_still_blocks(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("governance.override_deny", "forced")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK

    def test_exact_exfiltrate_still_blocks(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("network.exfiltrate", "sent")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK

    def test_underscore_compound_token_matches(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("rbac.role", "escalation_privilege")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK

    def test_retry_standalone_still_flags(self) -> None:
        judge = RuleJudge()
        trace = _trace_with([("queue.worker", "retry")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.FLAG


class TestW8ChinesePattern:
    def test_chinese_pattern_blocks(self) -> None:
        judge = RuleJudge(block_patterns=("越权",))
        trace = _trace_with([("file.read", "越权操作")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.BLOCK

    def test_chinese_pattern_no_false_positive(self) -> None:
        judge = RuleJudge(block_patterns=("越权",))
        trace = _trace_with([("file.read", "正常读取")])
        verdict = judge.arbitrate(trace)
        assert verdict.decision == VerdictDecision.PASS


class TestW8NoJudgeFailClosed:
    """A10：无官时非 Trace 输入 fail-closed，不再确定性仿真。"""

    def _registry(self) -> Any:
        from maref.governance.verifier_registry import VerifierEntry, VerifierRegistry

        reg = VerifierRegistry()
        reg.register(
            VerifierEntry(name="v1", model="m", methodology="x", accuracy=0.9)
        )
        reg.register(
            VerifierEntry(name="v2", model="m", methodology="x", accuracy=0.8)
        )
        return reg

    def test_bool_input_fails_closed_without_judges(self) -> None:
        from maref.governance.verifier_consensus import VerifierConsensus

        consensus = VerifierConsensus(self._registry())
        result = consensus.evaluate(True)
        assert result.passed is False
        assert result.votes
        assert all(v["verdict"]["error"] == "no_judge_for_input" for v in result.votes)

    def test_false_input_fails_closed_without_judges(self) -> None:
        from maref.governance.verifier_consensus import VerifierConsensus

        consensus = VerifierConsensus(self._registry())
        result = consensus.evaluate(False)
        assert result.passed is False

    def test_dict_input_fails_closed_without_judges(self) -> None:
        from maref.governance.verifier_consensus import VerifierConsensus

        consensus = VerifierConsensus(self._registry())
        result = consensus.evaluate({"action": "deploy"})
        assert result.passed is False
        assert all(v["approved"] is False for v in result.votes)

    def test_trace_with_judge_arbitrates(self) -> None:
        from maref.governance.verifier_consensus import VerifierConsensus

        consensus = VerifierConsensus(
            self._registry(), judges={"v1": RuleJudge(), "v2": RuleJudge()}
        )
        trace = _trace_with([("file.read", "allowed")])
        result = consensus.evaluate(trace)
        assert result.passed is True
        assert all(v["verdict"]["decision"] == "pass" for v in result.votes)

    def test_empty_registry_no_judge_still_fails(self) -> None:
        from maref.governance.verifier_consensus import VerifierConsensus
        from maref.governance.verifier_registry import VerifierRegistry

        consensus = VerifierConsensus(VerifierRegistry())
        result = consensus.evaluate({"action": "deploy"})
        assert result.passed is False
        assert result.votes == []
