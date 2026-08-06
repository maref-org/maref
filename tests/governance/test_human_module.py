"""测试 human/ 模块：DecisionAPI + InterruptProtocol + RuleEngine"""
import pytest
import time
import threading
from maref.human.decision_api import (
    HumanDecisionAPI, DecisionRequest, DecisionResponse,
    DecisionContext, DecisionMode, UrgencyLevel, DecisionStatus,
)
from maref.human.interrupt_protocol import (
    InterruptProtocol, InterruptType, InterruptSignal,
)
from maref.human.rule_engine import (
    CollaborationRuleEngine, CollaborationRule, CollaborationAction,
    RuleCondition,
)


class TestHumanDecisionAPI:
    """覆盖 decision_api.py ~280 行中的核心路径"""

    def setup_method(self):
        self.api = HumanDecisionAPI()

    def _make_request(self, **kwargs) -> DecisionRequest:
        ctx = DecisionContext(
            task_id="t1", agent_id="a1",
            action_description="test action", risk_score=0.3,
        )
        params = dict(task_id="t1", context=ctx)
        params.update(kwargs)
        return DecisionRequest(**params)

    def test_sync_approve(self):
        """SYNC 模式：提交请求后注入响应"""
        req = self._make_request(mode=DecisionMode.SYNC, timeout=5.0)
        result = [None]

        def respond_later():
            time.sleep(0.05)
            self.api.submit_response(DecisionResponse(
                request_id=req.request_id, decision="approve",
            ))
        threading.Thread(target=respond_later, daemon=True).start()

        resp = self.api.request_decision(req)
        assert resp is not None
        assert resp.decision == "approve"

    def test_async_mode(self):
        """ASYNC 模式：立即返回 None"""
        req = self._make_request(mode=DecisionMode.ASYNC)
        resp = self.api.request_decision(req)
        assert resp is None

    def test_batch_detection(self):
        """批处理：注册 filter 后自动组批"""
        self.api.register_batch_filter(lambda r: r.context.risk_score > 0.1)
        reqs = [self._make_request(mode=DecisionMode.SYNC, timeout=1.0) for _ in range(6)]
        for i, r in enumerate(reqs):
            r.context.risk_score = 0.5
            r.request_id = f"req-{i}"
        # 前 4 个返回 batched
        for i in range(4):
            resp = self.api.request_decision(reqs[i])
            assert resp.decision == "batched", f"req-{i} should be batched"
        # 第 5 个触发 flush
        resp5 = self.api.request_decision(reqs[4])
        assert resp5.decision == "batch_approved"

    def test_timeout_high_urgency(self):
        """HIGH 超时 → auto-escalated"""
        req = self._make_request(urgency=UrgencyLevel.HIGH, timeout=0.05)
        resp = self.api.request_decision(req)
        assert resp.decision == "escalated"

    def test_timeout_low_urgency(self):
        """LOW 超时 → suspended"""
        req = self._make_request(urgency=UrgencyLevel.LOW, timeout=0.05)
        resp = self.api.request_decision(req)
        assert resp.decision == "suspended"

    def test_get_pending(self):
        """获取待处理请求列表"""
        req = self._make_request(mode=DecisionMode.ASYNC)
        self.api.request_decision(req)
        pending = self.api.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == req.request_id

    def test_flush_batch(self):
        """手动触发 batch flush"""
        self.api.register_batch_filter(lambda r: True)
        for i in range(3):
            req = self._make_request(mode=DecisionMode.ASYNC)
            req.request_id = f"batch-req-{i}"
            self.api.request_decision(req)
        resp = self.api.flush_batch("a1:test")
        assert resp.decision == "batch_approved"

    def test_to_dict(self):
        """DecisionRequest/Response 序列化"""
        req = self._make_request()
        d = req.to_dict()
        assert d["task_id"] == "t1"
        assert "context" in d
        resp = DecisionResponse(request_id="r1", decision="approve", reason="ok")
        d2 = resp.to_dict()
        assert d2["decision"] == "approve"


class TestInterruptProtocol:
    """覆盖 interrupt_protocol.py ~160 行"""

    def setup_method(self):
        self.proto = InterruptProtocol()

    def test_issue_and_retrieve(self):
        signal = self.proto.issue_interrupt(
            InterruptType.ABORT, issued_by="admin", reason="emergency",
        )
        assert signal.interrupt_type == InterruptType.ABORT
        assert signal.global_sequence == 1
        latest = self.proto.get_latest_interrupt()
        assert latest is not None
        assert latest.signal_id == signal.signal_id

    def test_multiple_issues(self):
        for i in range(3):
            self.proto.issue_interrupt(InterruptType.PAUSE, issued_by="user")
        assert self.proto.get_latest_interrupt().global_sequence == 3
        sigs = self.proto.get_interrupts_since(1)
        assert len(sigs) == 2  # seq 2, 3

    def test_should_agent_stop(self):
        self.proto.issue_interrupt(InterruptType.ABORT, issued_by="admin",
                                    target_agents=["a1"])
        assert self.proto.should_agent_stop("a1", 0) is not None
        assert self.proto.should_agent_stop("a2", 0) is None  # not targeted
        assert self.proto.should_agent_stop("a1", 99) is None  # already seen

    def test_broadcast_stops_all(self):
        self.proto.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        for agent in ["a1", "a2", "a3"]:
            assert self.proto.should_agent_stop(agent, 0) is not None

    def test_propagation(self):
        signal = self.proto.issue_interrupt(InterruptType.RESUME, issued_by="admin",
                                            target_agents=["a1", "a2"])
        result = self.proto.propagate_to_agents(["a1", "a2", "a3"], signal)
        assert result["a1"] is True
        assert result["a2"] is True
        assert result["a3"] is False

    def test_history(self):
        for _ in range(5):
            self.proto.issue_interrupt(InterruptType.OVERRIDE, issued_by="user")
        history = self.proto.get_history(limit=3)
        assert len(history) == 3

    def test_interrupt_to_dict(self):
        signal = self.proto.issue_interrupt(InterruptType.PAUSE, issued_by="admin")
        d = signal.to_dict()
        assert d["interrupt_type"] == "pause"

    def test_get_interrupt_nonexistent(self):
        assert self.proto.get_interrupt(999) is None


class TestCollaborationRuleEngine:
    """覆盖 rule_engine.py ~250 行"""

    def setup_method(self):
        self.engine = CollaborationRuleEngine()

    def test_add_and_evaluate_rule(self):
        self.engine.add_rule(CollaborationRule(
            name="high_cost",
            when=[RuleCondition("cost", ">", 500)],
            then=CollaborationAction.HITL,
        ))
        action = self.engine.evaluate({"cost": 600})
        assert action == CollaborationAction.HITL
        action2 = self.engine.evaluate({"cost": 100})
        assert action2 == CollaborationAction.HATL  # default

    def test_rule_with_else(self):
        self.engine.add_rule(CollaborationRule(
            name="pii_check",
            when=[RuleCondition("data_classification", "==", "PII")],
            then=CollaborationAction.HITL,
            else_=CollaborationAction.HOTL,
        ))
        assert self.engine.evaluate({"data_classification": "PII"}) == CollaborationAction.HITL
        assert self.engine.evaluate({"data_classification": "PUBLIC"}) == CollaborationAction.HOTL

    def test_multiple_conditions_and(self):
        self.engine.add_rule(CollaborationRule(
            name="high_cost_pii",
            when=[
                RuleCondition("cost", ">", 500),
                RuleCondition("data_classification", "==", "PII"),
            ],
            then=CollaborationAction.HALT,
        ))
        assert self.engine.evaluate({"cost": 600, "data_classification": "PII"}) == CollaborationAction.HALT
        assert self.engine.evaluate({"cost": 600, "data_classification": "PUBLIC"}) == CollaborationAction.HATL

    def test_rule_priority(self):
        self.engine.add_rule(CollaborationRule(
            name="low", when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.NOTIFY, priority=0,
        ))
        self.engine.add_rule(CollaborationRule(
            name="high", when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.HALT, priority=10,
        ))
        # Higher priority evaluated first
        action = self.engine.evaluate({"x": 1})
        assert action == CollaborationAction.HALT

    def test_disable_rule(self):
        self.engine.add_rule(CollaborationRule(
            name="disabled_test", when=[RuleCondition("x", "==", 1)],
            then=CollaborationAction.HITL,
        ))
        assert self.engine.disable_rule("disabled_test") is True
        action = self.engine.evaluate({"x": 1})
        assert action == CollaborationAction.HATL  # rule disabled
        assert self.engine.enable_rule("disabled_test") is True
        action = self.engine.evaluate({"x": 1})
        assert action == CollaborationAction.HITL

    def test_remove_rule(self):
        self.engine.add_rule(CollaborationRule(
            name="remove_me", when=[RuleCondition("x", ">", 0)],
            then=CollaborationAction.HALT,
        ))
        assert self.engine.remove_rule("remove_me") is True
        assert self.engine.remove_rule("nonexistent") is False
        assert len(self.engine.list_rules()) == 0

    def test_evaluate_with_trace(self):
        self.engine.add_rule(CollaborationRule(
            name="trace_test", when=[RuleCondition("y", "<", 10)],
            then=CollaborationAction.NOTIFY,
        ))
        action, trace = self.engine.evaluate_with_trace({"y": 5})
        assert action == CollaborationAction.NOTIFY
        assert "trace_test" in trace

    def test_parse_dsl(self):
        rule = CollaborationRuleEngine.parse_rule(
            "parsed", "WHEN cost > 500 AND data == PII THEN HITL ELSE HOTL"
        )
        assert len(rule.when) == 2
        assert rule.then == CollaborationAction.HITL
        assert rule.else_ == CollaborationAction.HOTL
        # Evaluate
        self.engine.add_rule(rule)
        assert self.engine.evaluate({"cost": 600, "data": "PII"}) == CollaborationAction.HITL

    def test_parse_dsl_invalid(self):
        import pytest
        with pytest.raises(ValueError):
            CollaborationRuleEngine.parse_rule("bad", "INVALID SYNTAX")

    def test_get_history(self):
        self.engine.add_rule(CollaborationRule(
            name="hist", when=[RuleCondition("z", ">", 0)],
            then=CollaborationAction.NOTIFY,
        ))
        self.engine.evaluate({"z": 1})
        self.engine.evaluate({"z": 2})
        history = self.engine.get_history(limit=10)
        assert len(history) == 2

    def test_parse_value_types(self):
        assert CollaborationRuleEngine._parse_value("42") == 42
        assert CollaborationRuleEngine._parse_value("3.14") == 3.14
        assert CollaborationRuleEngine._parse_value("'hello'") == "hello"

    def test_contains_operator(self):
        self.engine.add_rule(CollaborationRule(
            name="contains_check", when=[RuleCondition("text", "contains", "urgent")],
            then=CollaborationAction.ESCALATE,
        ))
        assert self.engine.evaluate({"text": "this is urgent"}) == CollaborationAction.ESCALATE
        assert self.engine.evaluate({"text": "normal"}) == CollaborationAction.HATL

    def test_in_operator(self):
        self.engine.add_rule(CollaborationRule(
            name="in_check", when=[RuleCondition("role", "in", ["admin", "supervisor"])],
            then=CollaborationAction.HOTL,
        ))
        assert self.engine.evaluate({"role": "admin"}) == CollaborationAction.HOTL
        assert self.engine.evaluate({"role": "viewer"}) == CollaborationAction.HATL
