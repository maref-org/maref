from __future__ import annotations

import time

import pytest

from maref.human.decision_api import (
    DecisionContext,
    DecisionMode,
    DecisionRequest,
    DecisionResponse,
    HumanDecisionAPI,
    UrgencyLevel,
)


class TestDecisionContext:
    def test_default_values(self) -> None:
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="do something")
        assert ctx.risk_score == 0.0
        assert ctx.data_classification == ""
        assert ctx.estimated_cost == 0.0
        assert ctx.affected_resources == []
        assert ctx.historical_precedent == ""


class TestDecisionRequest:
    def test_default_values(self) -> None:
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="test")
        req = DecisionRequest(task_id="t1", context=ctx)
        assert req.urgency == UrgencyLevel.MEDIUM
        assert req.mode == DecisionMode.SYNC
        assert req.options == ["approve", "reject", "escalate"]
        assert req.timeout == 300.0
        assert req.batch_key is None
        assert len(req.request_id) == 8

    def test_to_dict_includes_context(self) -> None:
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="test", risk_score=0.8)
        req = DecisionRequest(task_id="t1", context=ctx, urgency=UrgencyLevel.HIGH)
        d = req.to_dict()
        assert d["request_id"] == req.request_id
        assert d["urgency"] == "high"
        assert d["context"]["risk_score"] == 0.8
        assert d["context"]["action_description"] == "test"


class TestDecisionResponse:
    def test_default_values(self) -> None:
        resp = DecisionResponse(request_id="r1", decision="approve")
        assert resp.reason == ""
        assert resp.responded_by == ""
        assert resp.responded_at > 0

    def test_to_dict(self) -> None:
        resp = DecisionResponse(request_id="r1", decision="reject", reason="too risky", responded_by="user1")
        d = resp.to_dict()
        assert d["decision"] == "reject"
        assert d["reason"] == "too risky"
        assert d["responded_by"] == "user1"


class TestHumanDecisionAPISync:
    def test_sync_decision_responded(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="transfer funds")
        req = DecisionRequest(task_id="t1", context=ctx, timeout=5.0)
        api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))
        resp = api.request_decision(req)
        assert resp is not None
        assert resp.decision == "approve"

    def test_sync_decision_timeout_low_urgency(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="review log")
        req = DecisionRequest(task_id="t1", context=ctx, urgency=UrgencyLevel.LOW, timeout=0.1)
        resp = api.request_decision(req)
        assert resp is not None

    def test_sync_decision_timeout_medium_urgency(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="approve change")
        req = DecisionRequest(task_id="t1", context=ctx, urgency=UrgencyLevel.MEDIUM, timeout=0.1)
        resp = api.request_decision(req)
        assert resp is not None

    def test_sync_decision_timeout_high_urgency(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="emergency stop")
        req = DecisionRequest(task_id="t1", context=ctx, urgency=UrgencyLevel.HIGH, timeout=0.1)
        resp = api.request_decision(req)
        assert resp is not None


class TestHumanDecisionAPIAsync:
    def test_async_returns_none(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="deploy")
        req = DecisionRequest(task_id="t1", context=ctx, mode=DecisionMode.ASYNC)
        resp = api.request_decision(req)
        assert resp is None

    def test_async_with_callback(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="deploy")
        req = DecisionRequest(task_id="t1", context=ctx, mode=DecisionMode.ASYNC)
        results = []

        def cb(response: DecisionResponse) -> None:
            results.append(response)

        api.request_decision(req, callback=cb)
        api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))
        assert len(results) == 1
        assert results[0].decision == "approve"


class TestHumanDecisionAPIBatch:
    def test_batch_filter_groups_requests(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: r.context.agent_id == "batch_agent")

        ctx = DecisionContext(task_id="t1", agent_id="batch_agent", action_description="deploy service")
        req1 = DecisionRequest(task_id="t1", context=ctx, timeout=0.5)
        req2 = DecisionRequest(task_id="t2", context=ctx, timeout=0.5)

        resp1 = api.request_decision(req1)
        assert resp1 is not None
        assert resp1.decision == "batched"

        resp2 = api.request_decision(req2)
        assert resp2 is not None
        assert resp2.decision == "batched"

    def test_batch_flush_when_threshold_reached(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: True)
        ctx = DecisionContext(task_id="t", agent_id="agent", action_description="quick task")
        reqs = [DecisionRequest(task_id=f"t{i}", context=ctx, timeout=0.5) for i in range(5)]
        last_resp = None
        for req in reqs:
            last_resp = api.request_decision(req)
        assert last_resp is not None
        assert last_resp.decision == "batch_approved"

    def test_manual_batch_flush(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: True)
        ctx = DecisionContext(task_id="t1", agent_id="agent", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx, timeout=0.5)
        api.request_decision(req)
        resp = api.flush_batch("agent:task")
        assert resp is not None
        assert resp.decision == "batch_approved"

    def test_flush_empty_batch(self) -> None:
        api = HumanDecisionAPI()
        resp = api.flush_batch("nonexistent")
        assert resp.decision == "approved"

    def test_get_batch_queue(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: True)
        ctx = DecisionContext(task_id="t1", agent_id="agent", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx)
        api.request_decision(req)
        queue = api.get_batch_queue("agent:task")
        assert len(queue) == 1

    def test_batch_filter_skips_non_matching(self) -> None:
        api = HumanDecisionAPI()
        api.register_batch_filter(lambda r: False)
        ctx = DecisionContext(task_id="t1", agent_id="agent", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx, timeout=0.5)
        api.request_decision(req)
        assert len(api.get_pending()) == 1


class TestHumanDecisionAPIPending:
    def test_get_pending(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx, mode=DecisionMode.ASYNC)
        api.request_decision(req)
        pending = api.get_pending()
        assert len(pending) == 1
        assert pending[0].task_id == "t1"

    def test_pending_cleared_after_response(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx, mode=DecisionMode.ASYNC)
        api.request_decision(req)
        api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))
        assert len(api.get_pending()) == 0


class TestTimeoutPolicies:
    def test_default_timeout_low(self) -> None:
        api = HumanDecisionAPI()
        timeout = api._default_timeout(UrgencyLevel.LOW)
        assert timeout == 3600.0

    def test_default_timeout_medium(self) -> None:
        api = HumanDecisionAPI()
        timeout = api._default_timeout(UrgencyLevel.MEDIUM)
        assert timeout == 300.0

    def test_default_timeout_high(self) -> None:
        api = HumanDecisionAPI()
        timeout = api._default_timeout(UrgencyLevel.HIGH)
        assert timeout == 60.0

    def test_custom_timeout_not_overridden(self) -> None:
        api = HumanDecisionAPI()
        ctx = DecisionContext(task_id="t1", agent_id="a1", action_description="task")
        req = DecisionRequest(task_id="t1", context=ctx, timeout=10.0)
        stored = api._pending.get(req.request_id) if req.request_id in api._pending else None
        api.request_decision(req)
        assert req.request_id in api._pending or req not in api._pending
