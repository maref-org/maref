"""Unit tests for CrossOrgHITL (cross-org human-in-the-loop)."""

from __future__ import annotations

import time

from maref.federation.hitl import (
    CrossOrgApprovalRequest,
    CrossOrgApprovalStatus,
    CrossOrgHITL,
)


class TestCrossOrgApprovalRequest:
    def test_is_pending_for_pending_status(self) -> None:
        req = CrossOrgApprovalRequest(
            request_id="r1", action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        assert req.is_pending is True
        assert req.is_resolved is False

    def test_is_pending_for_escalated_status(self) -> None:
        req = CrossOrgApprovalRequest(
            request_id="r1", action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            status=CrossOrgApprovalStatus.ESCALATED,
        )
        assert req.is_pending is True
        assert req.is_resolved is False

    def test_is_resolved_for_approved(self) -> None:
        req = CrossOrgApprovalRequest(
            request_id="r1", action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            status=CrossOrgApprovalStatus.APPROVED,
        )
        assert req.is_pending is False
        assert req.is_resolved is True

    def test_to_dict(self) -> None:
        req = CrossOrgApprovalRequest(
            request_id="r1", action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        d = req.to_dict()
        assert d["request_id"] == "r1"
        assert d["status"] == "pending"
        assert d["requesting_org"] == "A"
        assert d["reviewing_org"] == "B"


class TestCrossOrgHITLRequest:
    def test_request_approval_creates_pending(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="data_transfer",
            description="Transfer PII data to OrgB",
            requesting_org="OrgA",
            reviewing_org="OrgB",
            agent_did="did:1",
            task_id="task-1",
        )
        assert req.request_id.startswith("xhitl_")
        assert req.status == CrossOrgApprovalStatus.PENDING
        assert hitl.request_count == 1

    def test_intra_org_auto_approved(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="internal_action",
            description="d",
            requesting_org="OrgA",
            reviewing_org="OrgA",
            agent_did="did:1",
            task_id="t1",
        )
        assert req.status == CrossOrgApprovalStatus.APPROVED
        assert req.reviewer == "auto"
        assert req.resolved_at is not None

    def test_request_with_parameters(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            parameters={"data_type": "pii", "volume": 1000},
        )
        assert req.parameters["data_type"] == "pii"
        assert req.parameters["volume"] == 1000

    def test_request_with_escalation_org(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            escalation_org="OrgC",
        )
        assert req.escalation_org == "OrgC"


class TestCrossOrgHITLApproveReject:
    def test_approve_pending(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        assert hitl.approve(req.request_id, reviewer="alice") is True
        assert req.status == CrossOrgApprovalStatus.APPROVED
        assert req.reviewer == "alice"
        assert req.resolved_at is not None

    def test_approve_already_resolved_returns_false(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.approve(req.request_id)
        assert hitl.approve(req.request_id) is False

    def test_reject_with_reason(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        assert hitl.reject(req.request_id, reason="data too sensitive") is True
        assert req.status == CrossOrgApprovalStatus.REJECTED
        assert req.reason == "data too sensitive"

    def test_reject_already_resolved_returns_false(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.reject(req.request_id)
        assert hitl.reject(req.request_id) is False

    def test_approve_nonexistent_returns_false(self) -> None:
        hitl = CrossOrgHITL()
        assert hitl.approve("nonexistent") is False


class TestCrossOrgHITLTimeouts:
    def test_timeout_expires_without_escalation(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            timeout_seconds=1.0,
        )
        # Simulate time passing beyond timeout.
        future = req.created_at + 5.0
        affected = hitl.process_timeouts(now=future)
        assert req.request_id in affected
        assert req.status == CrossOrgApprovalStatus.EXPIRED

    def test_timeout_escalates_with_escalation_org(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            timeout_seconds=1.0,
            escalation_org="OrgC",
        )
        future = req.created_at + 5.0
        affected = hitl.process_timeouts(now=future)
        assert req.request_id in affected
        assert req.status == CrossOrgApprovalStatus.ESCALATED
        assert req.escalated_to == "OrgC"
        # The request should now be pending in OrgC's queue.
        orgc_pending = hitl.get_pending("OrgC")
        assert len(orgc_pending) == 1

    def test_escalated_timeout_expires_on_second_timeout(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            timeout_seconds=1.0,
            escalation_org="OrgC",
        )
        # First timeout: escalate.
        first_future = req.created_at + 5.0
        hitl.process_timeouts(now=first_future)
        assert req.status == CrossOrgApprovalStatus.ESCALATED

        # Second timeout: expire.
        second_future = req.created_at + 10.0
        affected = hitl.process_timeouts(now=second_future)
        assert req.request_id in affected
        assert req.status == CrossOrgApprovalStatus.EXPIRED

    def test_timeout_does_not_affect_non_expired(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            timeout_seconds=300.0,
        )
        # Process timeouts immediately — should not affect this request.
        affected = hitl.process_timeouts()
        assert req.request_id not in affected
        assert req.status == CrossOrgApprovalStatus.PENDING

    def test_timeout_does_not_affect_resolved(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="act", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
            timeout_seconds=1.0,
        )
        hitl.approve(req.request_id)
        future = req.created_at + 10.0
        affected = hitl.process_timeouts(now=future)
        assert req.request_id not in affected


class TestCrossOrgHITLQueries:
    def test_get_pending_by_reviewing_org(self) -> None:
        hitl = CrossOrgHITL()
        hitl.request_approval(
            action="a", description="d",
            requesting_org="OrgA", reviewing_org="OrgB",
            agent_did="did:1", task_id="t1",
        )
        hitl.request_approval(
            action="a", description="d",
            requesting_org="OrgA", reviewing_org="OrgC",
            agent_did="did:1", task_id="t2",
        )
        orgb_pending = hitl.get_pending("OrgB")
        orgc_pending = hitl.get_pending("OrgC")
        assert len(orgb_pending) == 1
        assert len(orgc_pending) == 1

    def test_get_pending_all(self) -> None:
        hitl = CrossOrgHITL()
        hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="C",
            agent_did="did:1", task_id="t2",
        )
        assert len(hitl.get_pending()) == 2

    def test_get_pending_excludes_resolved(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.approve(req.request_id)
        assert len(hitl.get_pending("B")) == 0

    def test_get_pending_count(self) -> None:
        hitl = CrossOrgHITL()
        hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:2", task_id="t2",
        )
        assert hitl.get_pending_count("B") == 2

    def test_get_history_filtered_by_org(self) -> None:
        hitl = CrossOrgHITL()
        req1 = hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        req2 = hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="C",
            agent_did="did:2", task_id="t2",
        )
        hitl.approve(req1.request_id)
        hitl.reject(req2.request_id)

        # Org A is requesting org in both → both in history.
        org_a_history = hitl.get_history(org="A")
        assert len(org_a_history) == 2

        # Org B is reviewing org in only req1.
        org_b_history = hitl.get_history(org="B")
        assert len(org_b_history) == 1

    def test_get_history_limit_offset(self) -> None:
        hitl = CrossOrgHITL()
        for i in range(5):
            req = hitl.request_approval(
                action="a", description="d",
                requesting_org="A", reviewing_org="B",
                agent_did=f"did:{i}", task_id=f"t{i}",
            )
            hitl.approve(req.request_id)
            time.sleep(0.01)

        page1 = hitl.get_history(limit=2, offset=0)
        page2 = hitl.get_history(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2

    def test_get_request(self) -> None:
        hitl = CrossOrgHITL()
        req = hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        found = hitl.get_request(req.request_id)
        assert found is not None
        assert found.task_id == "t1"
        assert hitl.get_request("nonexistent") is None


class TestCrossOrgHITLSummary:
    def test_hitl_summary(self) -> None:
        hitl = CrossOrgHITL()
        r1 = hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="B",
            agent_did="did:1", task_id="t1",
        )
        hitl.request_approval(
            action="a", description="d",
            requesting_org="A", reviewing_org="C",
            agent_did="did:2", task_id="t2",
        )
        hitl.approve(r1.request_id)
        # Second request stays pending.

        summary = hitl.hitl_summary()
        assert summary["total_requests"] == 2
        assert summary["status_counts"]["approved"] == 1
        assert summary["status_counts"]["pending"] == 1
        assert summary["pending_count"] == 1
        assert summary["total_orgs"] == 3  # A, B, C
