"""
HumanDecisionAPI 扩展测试

补充覆盖：get_batch_queue、flush_batch 空队列、
_default_timeout 映射、_on_timeout medium urgency、
DecisionRequest.to_dict 完整字段、DecisionResponse.to_dict、
DecisionContext 默认值、SYNC 超时后响应仍能被消费、
batch filter 不匹配时不进入 batch。
"""

from __future__ import annotations

import time

import pytest

from maref.human.decision_api import (
    DecisionContext,
    DecisionMode,
    DecisionRequest,
    DecisionResponse,
    DecisionStatus,
    HumanDecisionAPI,
    UrgencyLevel,
)


class TestDecisionRequest:
    def test_request_defaults(self) -> None:
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="test"),
        )
        assert req.mode == DecisionMode.SYNC
        assert req.urgency == UrgencyLevel.MEDIUM
        assert req.timeout == 300.0
        assert req.options == ["approve", "reject", "escalate"]

    def test_request_to_dict(self) -> None:
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(
                task_id="t1",
                agent_id="a1",
                action_description="test",
                risk_score=0.5,
                data_classification="PII",
                estimated_cost=100.0,
                affected_resources=["db1"],
                historical_precedent="none",
            ),
            options=["yes", "no"],
            timeout=60.0,
            urgency=UrgencyLevel.HIGH,
            mode=DecisionMode.ASYNC,
            batch_key="bk1",
        )
        d = req.to_dict()
        assert d["task_id"] == "t1"
        assert d["options"] == ["yes", "no"]
        assert d["timeout"] == 60.0
        assert d["urgency"] == "high"
        assert d["mode"] == "async"
        assert d["batch_key"] == "bk1"
        assert d["context"]["risk_score"] == 0.5
        assert d["context"]["data_classification"] == "PII"
        assert d["context"]["estimated_cost"] == 100.0
        assert d["context"]["affected_resources"] == ["db1"]
        assert d["context"]["historical_precedent"] == "none"


class TestDecisionResponse:
    def test_response_to_dict(self) -> None:
        resp = DecisionResponse(
            request_id="r1",
            decision="approve",
            reason="looks good",
            responded_by="user1",
            responded_at=1000.0,
        )
        d = resp.to_dict()
        assert d["request_id"] == "r1"
        assert d["decision"] == "approve"
        assert d["reason"] == "looks good"
        assert d["responded_by"] == "user1"
        assert d["responded_at"] == 1000.0


class TestDecisionContext:
    def test_context_defaults(self) -> None:
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="test")
        assert ctx.risk_score == 0.0
        assert ctx.data_classification == ""
        assert ctx.estimated_cost == 0.0
        assert ctx.affected_resources == []
        assert ctx.historical_precedent == ""


class TestSyncModes:
    def test_sync_approve(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="transfer $100"),
            mode=DecisionMode.SYNC,
            timeout=1.0,
        )

        def respond_later():
            time.sleep(0.1)
            api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))

        import threading
        t = threading.Thread(target=respond_later)
        t.start()
        resp = api.request_decision(req)
        t.join()
        assert resp.decision == "approve"

    def test_sync_timeout_high_urgency(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="urgent"),
            urgency=UrgencyLevel.HIGH,
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "escalated"
        assert "Timeout" in resp.reason

    def test_sync_timeout_low_urgency(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="low priority"),
            urgency=UrgencyLevel.LOW,
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "suspended"

    def test_sync_timeout_medium_urgency(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="medium"),
            urgency=UrgencyLevel.MEDIUM,
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "escalated"
        assert "supervisor" in resp.reason


class TestAsyncMode:
    def test_async_callback(self) -> None:
        api = HumanDecisionAPI()
        received = []

        def callback(resp: DecisionResponse) -> None:
            received.append(resp)

        req = DecisionRequest(
            task_id="t2",
            context=DecisionContext(task_id="t2", agent_id="a1", action_description="delete database"),
            mode=DecisionMode.ASYNC,
        )
        result = api.request_decision(req, callback=callback)
        assert result is None
        api.submit_response(DecisionResponse(request_id=req.request_id, decision="reject"))
        assert len(received) == 1
        assert received[0].decision == "reject"


class TestBatch:
    def test_batch_confirmation(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: r.context.action_description.startswith("transfer"))
        requests = []
        for i in range(5):
            req = DecisionRequest(
                task_id=f"batch-{i}",
                context=DecisionContext(
                    task_id=f"batch-{i}", agent_id="a1", action_description=f"transfer ${i * 10}"
                ),
                mode=DecisionMode.SYNC,
            )
            requests.append(req)
        for i in range(4):
            resp = api.request_decision(requests[i])
            assert resp.decision == "batched"
        resp = api.request_decision(requests[4])
        assert resp.decision == "batch_approved"
        assert "5 requests" in resp.reason

    def test_batch_filter_no_match(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: r.context.action_description.startswith("transfer"))
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="delete"),
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "escalated"

    def test_get_batch_queue(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: True)
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="test"),
            mode=DecisionMode.SYNC,
        )
        api.request_decision(req)
        queue = api.get_batch_queue(f"{req.context.agent_id}:test")
        assert len(queue) == 1

    def test_flush_batch_empty(self) -> None:
        api = HumanDecisionAPI()
        resp = api.flush_batch("nonexistent")
        assert resp.decision == "approved"
        assert "empty" in resp.reason


class TestPending:
    def test_get_pending(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="action"),
            mode=DecisionMode.ASYNC,
        )
        api.request_decision(req)
        pending = api.get_pending()
        assert len(pending) == 1
        assert pending[0].task_id == "t1"

    def test_submit_response_removes_pending(self) -> None:
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(task_id="t1", agent_id="a1", action_description="action"),
            mode=DecisionMode.ASYNC,
        )
        api.request_decision(req)
        assert len(api.get_pending()) == 1
        api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))
        assert len(api.get_pending()) == 0


class TestTimeoutDefaults:
    def test_default_timeout_low(self) -> None:
        api = HumanDecisionAPI()
        assert api._default_timeout(UrgencyLevel.LOW) == 3600.0

    def test_default_timeout_medium(self) -> None:
        api = HumanDecisionAPI()
        assert api._default_timeout(UrgencyLevel.MEDIUM) == 300.0

    def test_default_timeout_high(self) -> None:
        api = HumanDecisionAPI()
        assert api._default_timeout(UrgencyLevel.HIGH) == 60.0
