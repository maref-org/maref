"""
v0.50 W6-S2 — F14 HITL 审批人签名

覆盖：
- reviewer="human" 无签名 → 允许（配合 sidecar scope 门禁）
- 自动化审批（reviewer != human）无签名 → 拒绝（fail-closed）
- 自动化审批带 signature + reviewer_did → 允许
- 签名和 reviewer_did 记录在请求上
"""

from __future__ import annotations

from maref.federation.hitl import (
    CrossOrgApprovalStatus,
    CrossOrgHITL,
)


def _make_request(engine: CrossOrgHITL) -> str:
    request = engine.request_approval(
        action="cross_border_transfer",
        description="Approve transfer",
        requesting_org="org-a",
        reviewing_org="org-b",
        agent_did="did:maref:agent-1",
        task_id="task-1",
    )
    return request.request_id


class TestW6HITLSigning:
    def test_human_reviewer_without_signature_allowed(self) -> None:
        engine = CrossOrgHITL()
        request_id = _make_request(engine)
        assert engine.approve(request_id, reviewer="human") is True
        assert engine._requests[request_id].status == CrossOrgApprovalStatus.APPROVED

    def test_automated_reviewer_without_signature_rejected(self) -> None:
        engine = CrossOrgHITL()
        request_id = _make_request(engine)
        assert engine.approve(request_id, reviewer="policy-engine") is False
        assert engine._requests[request_id].status == CrossOrgApprovalStatus.PENDING

    def test_automated_reviewer_with_signature_allowed(self) -> None:
        engine = CrossOrgHITL()
        request_id = _make_request(engine)
        ok = engine.approve(
            request_id,
            reviewer="policy-engine",
            signature="sig-abc-123",
            reviewer_did="did:maref:policy-engine-1",
        )
        assert ok is True
        req = engine._requests[request_id]
        assert req.status == CrossOrgApprovalStatus.APPROVED
        assert req.approval_signature == "sig-abc-123"
        assert req.reviewer_did == "did:maref:policy-engine-1"

    def test_automated_reviewer_missing_reviewer_did_rejected(self) -> None:
        engine = CrossOrgHITL()
        request_id = _make_request(engine)
        assert (
            engine.approve(request_id, reviewer="policy-engine", signature="sig-1")
            is False
        )
        assert engine._requests[request_id].status == CrossOrgApprovalStatus.PENDING

    def test_human_reviewer_with_forged_signature_still_allowed(self) -> None:
        """reviewer='human' 时签名非强制（身份由 sidecar scope 门禁管控），
        即使携带任意 signature 也按 human 语义放行 —— 记录但不校验。"""
        engine = CrossOrgHITL()
        request_id = _make_request(engine)
        ok = engine.approve(
            request_id, reviewer="human", signature="attacker-sig", reviewer_did="did:x"
        )
        assert ok is True
        req = engine._requests[request_id]
        assert req.approval_signature == "attacker-sig"
        assert req.reviewer_did == "did:x"
