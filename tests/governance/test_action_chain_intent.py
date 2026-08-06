"""G2 动作链意图推理测试 (v0.52.1 M3)。

覆盖:
- C1 ActionChainTracker 链追踪
- C2 ChainPatternLibrary 模式匹配
- C3 IntentHypothesisEngine 意图假设
- C4 SequentialRiskAggregator 单步风险累积 (核心: 单步 LOW 组合 → HIGH)
- C5 LongHorizonAnalyzer 长时程漂移 (34.5h 问题)
- C6 ChainInterruptGate 链级裁决
- 端到端 AISI 供应链攻击链
"""

from __future__ import annotations

import time

from maref.governance.intent import (
    ActionCategory,
    ActionChainTracker,
    ActionMatcher,
    ActionRecord,
    ChainDecision,
    ChainInterruptGate,
    ChainPattern,
    ChainPatternLibrary,
    ChainRiskLevel,
    IntentHypothesisEngine,
    LongHorizonAnalyzer,
    SequentialRiskAggregator,
)


def _rec(
    action: str,
    category: ActionCategory,
    agent: str = "agent-01",
    ts: float | None = None,
    risk: ChainRiskLevel = ChainRiskLevel.LOW,
    outcome: str = "success",
    metadata: dict | None = None,
) -> ActionRecord:
    return ActionRecord(
        action=action,
        agent_id=agent,
        category=category,
        timestamp=ts if ts is not None else time.time(),
        risk_level=risk,
        outcome=outcome,
        metadata=metadata or {},
    )


class TestActionChainTracker:
    def test_record_and_chain(self):
        tracker = ActionChainTracker()
        tracker.record(_rec("file.read", ActionCategory.READ))
        tracker.record(_rec("file.write", ActionCategory.UPDATE, ts=time.time() + 1))
        chain = tracker.chain("agent-01")
        assert len(chain) == 2
        assert chain[0].action == "file.read"
        assert chain[-1].action == "file.write"

    def test_prune_expired(self):
        tracker = ActionChainTracker(window_seconds=10)
        old = time.time() - 100
        tracker.record(_rec("old.action", ActionCategory.READ, ts=old))
        tracker.record(_rec("new.action", ActionCategory.READ))
        chain = tracker.chain("agent-01")
        assert [r.action for r in chain] == ["new.action"]

    def test_recent_agents(self):
        tracker = ActionChainTracker()
        tracker.record(_rec("a", ActionCategory.READ, agent="agent-1"))
        tracker.record(_rec("b", ActionCategory.READ, agent="agent-2"))
        assert sorted(tracker.recent_agents()) == ["agent-1", "agent-2"]

    def test_clear_and_latest(self):
        tracker = ActionChainTracker()
        r = _rec("a", ActionCategory.READ)
        tracker.record(r)
        assert tracker.latest("agent-01") == r
        tracker.clear("agent-01")
        assert tracker.chain("agent-01") == []

    def test_missing_agent_raises(self):
        tracker = ActionChainTracker()
        rec = ActionRecord(action="x", agent_id="")
        import pytest

        with pytest.raises(ValueError):
            tracker.record(rec)


class TestChainPatternLibrary:
    def test_builtin_patterns(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        ids = {p.pattern_id for p in lib.list_patterns()}
        assert len(ids) == 8
        assert "supply_chain_lie" in ids
        assert "se_human_lure" in ids

    def test_custom_register(self):
        lib = ChainPatternLibrary()
        pattern = ChainPattern(
            pattern_id="custom_pat",
            name="自定义",
            sequence=[ActionMatcher(category=ActionCategory.READ)],
        )
        lib.register(pattern)
        assert lib.get("custom_pat") is not None

    def test_match_supply_chain(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        t = time.time()
        chain = [
            _rec("github.submit_code", ActionCategory.EXTERNAL, ts=t),
            _rec("github.review_approve", ActionCategory.IDENTITY, ts=t + 10),
            _rec("github.thank_reviewer", ActionCategory.COMMUNICATE, ts=t + 20),
        ]
        matches = lib.match(chain)
        assert any(m.pattern.pattern_id == "supply_chain_lie" for m in matches)

    def test_match_with_gap_tolerance(self):
        lib = ChainPatternLibrary(max_gap=2)
        lib.register_builtin_patterns()
        t = time.time()
        chain = [
            _rec("github.submit_code", ActionCategory.EXTERNAL, ts=t),
            _rec("file.read", ActionCategory.READ, ts=t + 5),  # gap
            _rec("github.review_approve", ActionCategory.IDENTITY, ts=t + 10),
            _rec("github.thank_reviewer", ActionCategory.COMMUNICATE, ts=t + 20),
        ]
        matches = lib.match(chain)
        assert any(m.pattern.pattern_id == "supply_chain_lie" for m in matches)

    def test_no_match_benign(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        chain = [
            _rec("file.read", ActionCategory.READ),
            _rec("search.query", ActionCategory.READ),
        ]
        assert lib.match(chain) == []


class TestIntentHypothesisEngine:
    def test_hypothesize_from_match(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        t = time.time()
        chain = [
            _rec("github.submit_code", ActionCategory.EXTERNAL, ts=t),
            _rec("github.review_approve", ActionCategory.IDENTITY, ts=t + 10),
            _rec("github.thank_reviewer", ActionCategory.COMMUNICATE, ts=t + 20),
        ]
        matches = lib.match(chain)
        hypotheses = IntentHypothesisEngine(lib).hypothesize(chain, matches)
        assert len(hypotheses) >= 1
        top = hypotheses[0]
        assert top.escalation == ChainRiskLevel.CRITICAL
        assert top.confidence >= 0.9
        assert top.goal

    def test_no_match_no_hypothesis(self):
        engine = IntentHypothesisEngine(ChainPatternLibrary())
        chain = [_rec("file.read", ActionCategory.READ)]
        assert engine.hypothesize(chain, []) == []

    def test_hypothesis_to_dict(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        t = time.time()
        chain = [
            _rec("github.submit_code", ActionCategory.EXTERNAL, ts=t),
            _rec("github.review_approve", ActionCategory.IDENTITY, ts=t + 10),
            _rec("github.thank_reviewer", ActionCategory.COMMUNICATE, ts=t + 20),
        ]
        hyp = IntentHypothesisEngine(lib).hypothesize(chain, lib.match(chain))[0]
        d = hyp.to_dict()
        assert d["escalation"] == "CRITICAL"
        assert "supply_chain_lie" in d["strategy"]


class TestSequentialRiskAggregator:
    def test_all_low_steps_accumulate_to_high(self):
        """核心验收: 单步全 LOW 的组合链 → 链级 HIGH/CRITICAL。"""
        t = time.time()
        chain = [
            _rec("github.create_account", ActionCategory.IDENTITY, ts=t, risk=ChainRiskLevel.LOW),
            _rec("github.create_account", ActionCategory.IDENTITY, ts=t + 1, risk=ChainRiskLevel.LOW),
            _rec("github.submit_code", ActionCategory.EXTERNAL, ts=t + 2, risk=ChainRiskLevel.LOW),
            _rec("github.review_approve", ActionCategory.IDENTITY, ts=t + 3, risk=ChainRiskLevel.LOW),
            _rec("github.edit_history", ActionCategory.UPDATE, ts=t + 4, risk=ChainRiskLevel.LOW),
            _rec("identity.switch", ActionCategory.IDENTITY, ts=t + 5, risk=ChainRiskLevel.LOW),
        ]
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        matches = lib.match(chain)
        risk = SequentialRiskAggregator().aggregate(chain, matches)
        assert risk.level in (ChainRiskLevel.HIGH, ChainRiskLevel.CRITICAL)
        assert risk.score > 0
        assert risk.signals

    def test_benign_chain_low(self):
        chain = [
            _rec("file.read", ActionCategory.READ, risk=ChainRiskLevel.LOW),
            _rec("search.query", ActionCategory.READ, risk=ChainRiskLevel.LOW),
        ]
        risk = SequentialRiskAggregator().aggregate(chain, [])
        assert risk.level == ChainRiskLevel.LOW

    def test_high_single_step(self):
        # 单步 HIGH (3*0.3=0.9) 不足链级阈值 → LOW; 单步风险由动作级
        # TrustBoundaryManager 拦截, 链级聚合聚焦"单步 LOW 的组合"
        chain = [_rec("shell.exec", ActionCategory.EXECUTE, risk=ChainRiskLevel.HIGH)]
        risk = SequentialRiskAggregator().aggregate(chain, [])
        assert risk.level == ChainRiskLevel.LOW

    def test_chain_risk_to_dict(self):
        chain = [_rec("a", ActionCategory.READ)]
        d = SequentialRiskAggregator().aggregate(chain, []).to_dict()
        assert "level" in d and "score" in d


class TestLongHorizonAnalyzer:
    def test_slow_drift_detected(self):
        """34.5h 问题: 前期 LOW, 后期逐渐越界 → 漂移检出。"""
        t = time.time() - 7200  # 2 小时前
        tracker = ActionChainTracker(window_seconds=999999)
        # 早期段: 低风险查询 (15 分钟一段)
        for i in range(4):
            tracker.record(_rec(f"read.{i}", ActionCategory.READ, ts=t + i * 100))
        # 后期段: 高风险越界
        for i in range(4):
            tracker.record(
                _rec(f"external.{i}", ActionCategory.EXTERNAL, ts=t + 3600 + i * 100,
                     risk=ChainRiskLevel.HIGH)
            )
        analyzer = LongHorizonAnalyzer(segment_seconds=1800)
        analysis = analyzer.analyze(tracker, "agent-01")
        assert analysis.drift_detected
        assert analysis.drift_signal

    def test_no_drift_benign(self):
        t = time.time() - 3600
        tracker = ActionChainTracker(window_seconds=999999)
        for i in range(4):
            tracker.record(_rec(f"read.{i}", ActionCategory.READ, ts=t + i * 60))
        analysis = LongHorizonAnalyzer().analyze(tracker, "agent-01")
        assert not analysis.drift_detected
        assert analysis.peak_level == ChainRiskLevel.LOW

    def test_analysis_to_dict(self):
        t = time.time() - 3600
        tracker = ActionChainTracker(window_seconds=999999)
        for i in range(4):
            tracker.record(_rec(f"read.{i}", ActionCategory.READ, ts=t + i * 60))
        d = LongHorizonAnalyzer().analyze(tracker, "agent-01").to_dict()
        assert "segment_risks" in d and "total_actions" in d


class TestChainInterruptGate:
    def test_halt_on_supply_chain(self):
        """端到端: AISI 供应链攻击链 → HALT。"""
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        tracker = ActionChainTracker(window_seconds=999999)
        t = time.time()
        for i, (action, cat, risk) in enumerate([
            ("github.submit_code", ActionCategory.EXTERNAL, ChainRiskLevel.LOW),
            ("github.create_account", ActionCategory.IDENTITY, ChainRiskLevel.LOW),
            ("github.review_approve", ActionCategory.IDENTITY, ChainRiskLevel.LOW),
            ("github.thank_reviewer", ActionCategory.COMMUNICATE, ChainRiskLevel.LOW),
            ("github.edit_history", ActionCategory.UPDATE, ChainRiskLevel.LOW),
            ("identity.switch", ActionCategory.IDENTITY, ChainRiskLevel.LOW),
        ]):
            tracker.record(_rec(action, cat, ts=t + i * 10, risk=risk))

        gate = ChainInterruptGate(pattern_library=lib)
        verdict = gate.evaluate_agent(tracker, "agent-01")
        assert verdict.decision == ChainDecision.HALT
        assert verdict.level == ChainRiskLevel.CRITICAL
        assert "force_halt" in verdict.actions
        assert verdict.needs_action

    def test_continue_on_benign(self):
        tracker = ActionChainTracker()
        tracker.record(_rec("file.read", ActionCategory.READ))
        gate = ChainInterruptGate(ChainPatternLibrary())
        verdict = gate.evaluate_agent(tracker, "agent-01")
        assert verdict.decision == ChainDecision.CONTINUE

    def test_handler_called_on_halt(self):
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        tracker = ActionChainTracker(window_seconds=999999)
        t = time.time()
        for i, (action, cat) in enumerate([
            ("github.submit_code", ActionCategory.EXTERNAL),
            ("github.review_approve", ActionCategory.IDENTITY),
            ("github.thank_reviewer", ActionCategory.COMMUNICATE),
        ]):
            tracker.record(_rec(action, cat, ts=t + i * 10))

        gate = ChainInterruptGate(pattern_library=lib)
        calls: list = []
        gate.on_verdict(lambda v: calls.append(v.decision))
        verdict = gate.evaluate_agent(tracker, "agent-01")
        assert verdict.decision == ChainDecision.HALT
        assert ChainDecision.HALT in calls

    def test_watch_on_medium(self):
        t = time.time()
        chain = [
            _rec("external.a", ActionCategory.EXTERNAL, ts=t, risk=ChainRiskLevel.HIGH),
            _rec("external.b", ActionCategory.EXTERNAL, ts=t + 1, risk=ChainRiskLevel.HIGH),
            _rec("external.c", ActionCategory.EXTERNAL, ts=t + 2, risk=ChainRiskLevel.HIGH),
            _rec("network.d", ActionCategory.NETWORK, ts=t + 3, risk=ChainRiskLevel.MEDIUM),
        ]
        gate = ChainInterruptGate(ChainPatternLibrary())
        verdict = gate.evaluate(chain, agent_id="agent-01")
        assert verdict.decision in (ChainDecision.WATCH, ChainDecision.ESCALATE)

    def test_verdict_to_dict(self):
        tracker = ActionChainTracker()
        tracker.record(_rec("file.read", ActionCategory.READ))
        verdict = ChainInterruptGate(ChainPatternLibrary()).evaluate_agent(tracker, "agent-01")
        d = verdict.to_dict()
        assert d["decision"] == "continue"


class TestPipelineIntegration:
    """C7: core_pipeline 挂接链级意图评估。"""

    def _make_pipeline(self):
        from maref.governance.core_pipeline import GovernancePipeline

        tracker = ActionChainTracker(window_seconds=999999)
        lib = ChainPatternLibrary()
        lib.register_builtin_patterns()
        gate = ChainInterruptGate(pattern_library=lib)
        pipe = GovernancePipeline(intent_tracker=tracker, intent_gate=gate)
        return pipe

    def test_chain_halt_overrides_single_allow(self):
        """单步全 ALLOW 的供应链链 → 末次被链级覆盖为 DENY。"""
        from maref.governance.core_pipeline import GovernanceRequest, Verdict

        pipe = self._make_pipeline()
        for action in [
            "github.submit_code",
            "github.create_account",
            "github.review_approve",
            "github.thank_reviewer",
            "github.edit_history",
            "identity.switch",
        ]:
            pipe.govern(GovernanceRequest(action=action, agent_id="agent-01", trust_score=90, role="震"))
        result = pipe.govern(
            GovernanceRequest(action="github.submit_code", agent_id="agent-01", trust_score=90, role="震")
        )
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "intent_chain_halt"

    def test_no_intent_no_behavior_change(self):
        """未注入 intent 组件 → 行为完全不变。"""
        from maref.governance.core_pipeline import GovernancePipeline, GovernanceRequest, Verdict

        pipe = GovernancePipeline()
        result = pipe.govern(
            GovernanceRequest(action="github.submit_code", agent_id="agent-01", trust_score=90, role="震")
        )
        assert result.verdict == Verdict.ALLOW

    def test_escalate_asks_user(self):
        """record_tamper (HIGH) → ASK_USER。"""
        from maref.governance.core_pipeline import GovernanceRequest, Verdict

        pipe = self._make_pipeline()
        for action in ["github.edit_history", "identity.switch"]:
            pipe.govern(GovernanceRequest(action=action, agent_id="agent-01", trust_score=90, role="震"))
        result = pipe.govern(
            GovernanceRequest(action="github.edit_history", agent_id="agent-01", trust_score=90, role="震")
        )
        assert result.verdict == Verdict.ASK_USER
        assert result.matched_rule == "intent_chain_escalate"

    def test_intent_eval_failure_does_not_block(self):
        """链级评估异常不阻断主流程 (fail-open)。"""
        from maref.governance.core_pipeline import GovernancePipeline, GovernanceRequest, Verdict

        class BrokenGate:
            def evaluate_agent(self, *args, **kwargs):
                raise RuntimeError("boom")

        pipe = GovernancePipeline(intent_tracker=object(), intent_gate=BrokenGate())
        result = pipe.govern(
            GovernanceRequest(action="file.read", agent_id="agent-01", trust_score=90, role="震")
        )
        assert result.verdict == Verdict.ALLOW
