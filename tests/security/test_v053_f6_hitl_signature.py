"""v0.53 F6: HITL 审批 Ed25519 验签。

验证：
1. 无 reviewer 公钥配置时（旧路径）不带签名审批不回归
2. 配置公钥后，无签名 / 伪造签名 / 未注册 signer 全部被拒（REJECTED）
3. 正确签名通过（APPROVED）
4. gaas_approve / reject / gaas_reject 同样受验签保护
"""

from __future__ import annotations

import time

import pytest

from maref.integration.hitl import HITLRouter, HITLStatus
from maref.signing.signing_key import ReportSigningKey


@pytest.fixture
def reviewer_key() -> ReportSigningKey:
    return ReportSigningKey.generate()


def _sign(
    key: ReportSigningKey,
    event_id: str,
    target_status: HITLStatus,
    signed_at: float,
) -> str:
    payload = f"{event_id}:{target_status.value}:{signed_at}".encode()
    return key.sign_report(payload)


class TestLegacyNoKeys:
    def test_approve_without_signature_still_works(self):
        router = HITLRouter()
        event = router.request("t1", "agent-a", "shell.exec", "run")
        assert router.approve(event.event_id) == HITLStatus.APPROVED

    def test_reject_without_signature_still_works(self):
        router = HITLRouter()
        event = router.request("t1", "agent-a", "shell.exec", "run")
        assert router.reject(event.event_id, "no") == HITLStatus.REJECTED

    def test_gaas_approve_without_signature_still_works(self):
        router = HITLRouter()
        event = router.request("t1", "agent-a", "shell.exec", "run")
        assert router.gaas_approve("t1", event.event_id) == HITLStatus.APPROVED


class TestSignatureRequired:
    @pytest.fixture
    def router(self, reviewer_key: ReportSigningKey) -> HITLRouter:
        return HITLRouter(reviewer_public_keys={"rev-1": reviewer_key.public_key_pem})

    def test_no_signature_rejected(self, router: HITLRouter):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        assert router.approve(event.event_id) == HITLStatus.REJECTED

    def test_forged_signature_rejected(self, router: HITLRouter):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        forged = ReportSigningKey.generate()
        sig = _sign(forged, event.event_id, HITLStatus.APPROVED, time.time())
        status = router.approve(
            event.event_id,
            signature=sig,
            signer_did="rev-1",
            signer_public_key=forged.public_key_pem,
        )
        assert status == HITLStatus.REJECTED

    def test_unknown_signer_rejected(self, router: HITLRouter, reviewer_key: ReportSigningKey):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        sig = _sign(reviewer_key, event.event_id, HITLStatus.APPROVED, time.time())
        status = router.approve(
            event.event_id,
            signature=sig,
            signer_did="unregistered",
            signer_public_key=reviewer_key.public_key_pem,
        )
        assert status == HITLStatus.REJECTED

    def test_valid_signature_approved(
        self, router: HITLRouter, reviewer_key: ReportSigningKey
    ):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        signed_at = time.time()
        sig = _sign(reviewer_key, event.event_id, HITLStatus.APPROVED, signed_at)
        status = router.approve(
            event.event_id,
            reviewer="human-1",
            signature=sig,
            signer_did="rev-1",
            signer_public_key=reviewer_key.public_key_pem,
            signed_at=signed_at,
        )
        assert status == HITLStatus.APPROVED
        resolved = router.get_history()[0]
        assert resolved.signer_did == "rev-1"
        assert resolved.approval_signature == sig

    def test_gaas_approve_valid_signature(
        self, router: HITLRouter, reviewer_key: ReportSigningKey
    ):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        signed_at = time.time()
        sig = _sign(reviewer_key, event.event_id, HITLStatus.APPROVED, signed_at)
        status = router.gaas_approve(
            "t1",
            event.event_id,
            reviewer="human-1",
            signature=sig,
            signer_did="rev-1",
            signer_public_key=reviewer_key.public_key_pem,
            signed_at=signed_at,
        )
        assert status == HITLStatus.APPROVED

    def test_reject_valid_signature(
        self, router: HITLRouter, reviewer_key: ReportSigningKey
    ):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        signed_at = time.time()
        sig = _sign(reviewer_key, event.event_id, HITLStatus.REJECTED, signed_at)
        status = router.reject(
            event.event_id,
            reason="denied",
            signature=sig,
            signer_did="rev-1",
            signer_public_key=reviewer_key.public_key_pem,
            signed_at=signed_at,
        )
        assert status == HITLStatus.REJECTED

    def test_gaas_reject_signature_rejected_when_forged(
        self, router: HITLRouter, reviewer_key: ReportSigningKey
    ):
        event = router.request("t1", "agent-a", "shell.exec", "run")
        wrong_status_sig = _sign(
            reviewer_key, event.event_id, HITLStatus.APPROVED, time.time()
        )
        # 签名针对 APPROVED 状态，用于 reject 时应失败
        status = router.gaas_reject(
            "t1",
            event.event_id,
            reason="denied",
            signature=wrong_status_sig,
            signer_did="rev-1",
            signer_public_key=reviewer_key.public_key_pem,
        )
        assert status == HITLStatus.REJECTED
