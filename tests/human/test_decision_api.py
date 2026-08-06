"""Tests for Human Decision API."""

import time

from maref.human.decision_api import (
    DecisionContext,
    DecisionMode,
    DecisionRequest,
    DecisionResponse,
    HumanDecisionAPI,
    UrgencyLevel,
)


class TestHumanDecisionAPI:
    def test_sync_approve(self):
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t1",
            context=DecisionContext(
                task_id="t1", agent_id="a1", action_description="transfer $100"
            ),
            mode=DecisionMode.SYNC,
            timeout=1.0,
        )

        # Submit response in background
        def respond_later():
            time.sleep(0.1)
            api.submit_response(DecisionResponse(request_id=req.request_id, decision="approve"))

        import threading

        t = threading.Thread(target=respond_later)
        t.start()

        resp = api.request_decision(req)
        t.join()
        assert resp.decision == "approve"

    def test_async_callback(self):
        api = HumanDecisionAPI()
        received = []

        def callback(resp: DecisionResponse) -> None:
            received.append(resp)

        req = DecisionRequest(
            task_id="t2",
            context=DecisionContext(
                task_id="t2", agent_id="a1", action_description="delete database"
            ),
            mode=DecisionMode.ASYNC,
        )
        result = api.request_decision(req, callback=callback)
        assert result is None  # ASYNC returns immediately

        api.submit_response(DecisionResponse(request_id=req.request_id, decision="reject"))
        assert len(received) == 1
        assert received[0].decision == "reject"

    def test_timeout_high_urgency(self):
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t3",
            context=DecisionContext(
                task_id="t3", agent_id="a1", action_description="urgent action"
            ),
            urgency=UrgencyLevel.HIGH,
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "escalated"
        assert "Timeout" in resp.reason

    def test_timeout_low_urgency(self):
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t4",
            context=DecisionContext(task_id="t4", agent_id="a1", action_description="low priority"),
            urgency=UrgencyLevel.LOW,
            mode=DecisionMode.SYNC,
            timeout=0.1,
        )
        resp = api.request_decision(req)
        assert resp.decision == "suspended"

    def test_batch_confirmation(self):
        api = HumanDecisionAPI()
        # Register batch filter: all transfer actions go to batch
        api.register_batch_filter(lambda r: r.context.action_description.startswith("transfer"))

        # Send 5 transfer requests
        requests = []
        for i in range(5):
            req = DecisionRequest(
                task_id=f"batch-{i}",
                context=DecisionContext(
                    task_id=f"batch-{i}",
                    agent_id="a1",
                    action_description=f"transfer ${i * 10}",
                ),
                mode=DecisionMode.SYNC,
            )
            requests.append(req)

        # First 4 should be queued
        for i in range(4):
            resp = api.request_decision(requests[i])
            assert resp.decision == "batched"

        # 5th should trigger batch flush
        resp = api.request_decision(requests[4])
        assert resp.decision == "batch_approved"
        assert "5 requests" in resp.reason

    def test_get_pending(self):
        api = HumanDecisionAPI()
        req = DecisionRequest(
            task_id="t5",
            context=DecisionContext(task_id="t5", agent_id="a1", action_description="action"),
            mode=DecisionMode.ASYNC,
        )
        api.request_decision(req)
        pending = api.get_pending()
        assert len(pending) == 1
        assert pending[0].task_id == "t5"

    def test_decision_request_to_dict(self):
        req = DecisionRequest(
            task_id="t6",
            context=DecisionContext(task_id="t6", agent_id="a1", action_description="test"),
        )
        d = req.to_dict()
        assert d["task_id"] == "t6"
        assert d["urgency"] == "medium"
        assert d["context"]["agent_id"] == "a1"
