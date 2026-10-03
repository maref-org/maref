"""人工审批防篡改台账测试（框架 3.0 附件2 二.3(3)）。

覆盖 4 条验收断言：
1. 篡改任一历史记录 → verify_chain() == False；
2. MerkleProof 可离线独立验证；
3. 审批人身份不可伪造（验签失败即拒 / 非 active 拒绝）；
4. 高风险操作缺记录 → fail-closed 阻断。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from maref.crypto.ed25519_keys import Ed25519KeyPair
from maref.eivl.merkle_auditor import merkle_hash_pair
from maref.human.approval_ledger import (
    DECISION_APPROVED,
    DECISION_DENIED,
    HAS_SM2,
    ApprovalLedger,
    ApprovalLedgerError,
    ApprovalMissingError,
    integrate_with_approval_engine,
)


class _FakeIdentityService:
    def __init__(self, active: set[str] | None = None):
        self.active = active or set()

    def is_active(self, did_string: str) -> bool:
        return did_string in self.active


class _ExplodingIdentityService:
    def is_active(self, did_string: str) -> bool:  # noqa: ARG002
        raise RuntimeError("identity backend down")


def _ledger(**kwargs) -> ApprovalLedger:
    return ApprovalLedger(ed25519_keypair=Ed25519KeyPair.generate(), **kwargs)


class TestLedgerRecording:
    def test_record_creates_chained_record(self):
        ledger = _ledger()
        first = ledger.record("alice", "delete_db", DECISION_APPROVED, "reviewed")
        second = ledger.record("bob", "deploy", DECISION_DENIED, "risk")

        assert first.previous_hash == "0" * 64
        assert second.previous_hash == first.chain_hash
        assert ledger.verify_chain() is True

    def test_invalid_decision_rejected(self):
        ledger = _ledger()
        with pytest.raises(ApprovalLedgerError):
            ledger.record("alice", "x", "maybe")

    def test_empty_approver_rejected(self):
        ledger = _ledger()
        with pytest.raises(ApprovalLedgerError):
            ledger.record("", "x", DECISION_APPROVED)

    def test_safe_record_defaults_to_denied(self):
        ledger = _ledger()
        record = ledger.safe_record("alice", "dangerous", exc=RuntimeError("boom"))
        assert record.decision == DECISION_DENIED
        assert "boom" in record.rationale
        assert ledger.verify_chain() is True

    def test_summary_counts(self):
        ledger = _ledger()
        ledger.record("a", "x", DECISION_APPROVED)
        ledger.record("b", "y", DECISION_DENIED)
        summary = ledger.summary()
        assert summary["total"] == 2
        assert summary["approved"] == 1
        assert summary["denied"] == 1
        assert summary["chain_valid"] is True


class TestTamperDetection:
    """验收断言 1：篡改任一历史记录即被检出。"""

    def test_tamper_rationale_detected(self):
        ledger = _ledger()
        record = ledger.record("alice", "wipe", DECISION_APPROVED, "ok")
        record.rationale = "tampered"
        assert ledger.verify_chain() is False

    def test_tamper_decision_detected(self):
        ledger = _ledger()
        record = ledger.record("alice", "wipe", DECISION_DENIED, "no")
        record.decision = DECISION_APPROVED
        assert ledger.verify_chain() is False

    def test_tamper_chain_hash_detected(self):
        ledger = _ledger()
        record = ledger.record("alice", "wipe", DECISION_APPROVED, "ok")
        record.chain_hash = "f" * 64
        assert ledger.verify_chain() is False

    def test_tamper_middle_record_breaks_chain(self):
        ledger = _ledger()
        ledger.record("a", "x", DECISION_APPROVED)
        middle = ledger.record("b", "y", DECISION_APPROVED)
        ledger.record("c", "z", DECISION_APPROVED)
        middle.rationale = "changed"
        assert ledger.verify_chain() is False


class TestSignatureIdentity:
    """验收断言 3：审批人身份不可伪造。"""

    def test_forged_signature_rejected(self):
        ledger = _ledger()
        record = ledger.record("alice", "wipe", DECISION_APPROVED)
        record.signature = "00" * 64
        assert ledger.verify_record(record, record.previous_hash) is False

    def test_swapped_public_key_rejected(self):
        ledger = _ledger()
        record = ledger.record("alice", "wipe", DECISION_APPROVED)
        record.signer_public_key = Ed25519KeyPair.generate().public_key_pem
        assert ledger.verify_record(record, record.previous_hash) is False

    def test_inactive_approver_rejected(self):
        service = _FakeIdentityService(active={"did:maref:active"})
        ledger = _ledger(identity_service=service)
        with pytest.raises(ApprovalLedgerError):
            ledger.record(
                "alice", "wipe", DECISION_APPROVED, approver_did="did:maref:inactive"
            )

    def test_active_approver_accepted(self):
        service = _FakeIdentityService(active={"did:maref:active"})
        ledger = _ledger(identity_service=service)
        record = ledger.record(
            "alice", "wipe", DECISION_APPROVED, approver_did="did:maref:active"
        )
        assert record.approver_did == "did:maref:active"
        assert ledger.verify_chain() is True

    def test_identity_backend_failure_is_fail_closed(self):
        ledger = _ledger(identity_service=_ExplodingIdentityService())
        with pytest.raises(ApprovalLedgerError):
            ledger.record("alice", "wipe", DECISION_APPROVED, approver_did="did:maref:x")


class TestHighRiskEnforcement:
    """验收断言 4：高风险缺记录即阻断。"""

    def test_require_record_missing_blocks(self):
        ledger = _ledger()
        with pytest.raises(ApprovalMissingError):
            ledger.require_record("delete_prod")

    def test_enforce_high_risk_blocks_without_record(self):
        ledger = _ledger()
        with pytest.raises(ApprovalMissingError):
            ledger.enforce_high_risk("delete_prod", "critical")

    def test_enforce_high_risk_passes_with_approval(self):
        ledger = _ledger()
        ledger.record("alice", "delete_prod", DECISION_APPROVED, risk_level="critical")
        result = ledger.enforce_high_risk("delete_prod", "critical")
        assert result is not None
        assert result.decision == DECISION_APPROVED

    def test_enforce_low_risk_does_not_require_record(self):
        ledger = _ledger()
        assert ledger.enforce_high_risk("read_doc", "low") is None

    def test_denied_record_does_not_satisfy_requirement(self):
        ledger = _ledger()
        ledger.record("alice", "delete_prod", DECISION_DENIED, risk_level="high")
        with pytest.raises(ApprovalMissingError):
            ledger.require_record("delete_prod")


class TestMerkleProof:
    """验收断言 2：MerkleProof 可离线独立验证。"""

    def test_merkle_proof_verifies(self):
        ledger = _ledger()
        ledger.record("a", "x", DECISION_APPROVED)
        record = ledger.record("b", "y", DECISION_APPROVED)
        proof = ledger.get_merkle_proof(record.record_id)
        assert proof is not None
        assert proof.verify() is True
        assert proof.root_hash == ledger.merkle_root()

    def test_merkle_proof_offline_recompute(self):
        """仅用 merkle_hash_pair 独立重算，证明可离线验证（不依赖台账实例）。"""
        ledger = _ledger()
        ledger.record("a", "x", DECISION_APPROVED)
        record = ledger.record("b", "y", DECISION_APPROVED)
        proof = ledger.get_merkle_proof(record.record_id)

        current = proof.target_hash
        for sibling, direction in proof.proof_path:
            if direction == "left":
                current = merkle_hash_pair(sibling, current)
            else:
                current = merkle_hash_pair(current, sibling)
        assert current == proof.root_hash

    def test_proof_for_unknown_record_is_none(self):
        ledger = _ledger()
        assert ledger.get_merkle_proof("no-such-id") is None


class TestPersistence:
    def test_reload_restores_chain(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ApprovalLedger(ed25519_keypair=Ed25519KeyPair.generate(), storage_path=path)
        ledger.record("a", "x", DECISION_APPROVED)
        ledger.record("b", "y", DECISION_DENIED)

        reloaded = ApprovalLedger(
            ed25519_keypair=Ed25519KeyPair.generate(), storage_path=path
        )
        assert len(reloaded.records) == 2
        assert reloaded.verify_chain() is True
        assert reloaded.get_record(ledger.records[0].record_id) is not None


@pytest.mark.skipif(not HAS_SM2, reason="gmssl 未安装，SM2 通道不可用")
class TestSM2Channel:
    def test_sm2_sign_and_verify(self):
        from maref.crypto.sm2 import SM2KeyPair

        ledger = ApprovalLedger(sm2_keypair=SM2KeyPair.generate(), signature_type="sm2")
        record = ledger.record("alice", "wipe", DECISION_APPROVED)
        assert record.signature_type == "sm2"
        assert ledger.verify_chain() is True

    def test_sm2_tamper_detected(self):
        from maref.crypto.sm2 import SM2KeyPair

        ledger = ApprovalLedger(sm2_keypair=SM2KeyPair.generate(), signature_type="sm2")
        record = ledger.record("alice", "wipe", DECISION_APPROVED)
        record.rationale = "tampered"
        assert ledger.verify_chain() is False


class _FakeEngine:
    """最小 ApprovalEngine 替身：predict 返回带 risk_level 的决策对象。"""

    def __init__(self, risk_level: str):
        self._risk_level = risk_level
        self.predict_calls = 0

    def predict(self, request):  # noqa: ARG002
        self.predict_calls += 1
        return SimpleNamespace(risk_level=self._risk_level, action="allow")


class TestEngineIntegration:
    """验收断言 4（接线）：高风险决策必须具备台账记录，否则阻断。"""

    def test_high_risk_without_record_blocks(self):
        ledger = _ledger()
        engine = _FakeEngine("high")
        integrate_with_approval_engine(engine, ledger)
        with pytest.raises(ApprovalMissingError):
            engine.predict({"action": "delete_prod"})

    def test_high_risk_with_record_passes(self):
        ledger = _ledger()
        ledger.record("alice", "delete_prod", DECISION_APPROVED, risk_level="high")
        engine = _FakeEngine("critical")
        integrate_with_approval_engine(engine, ledger)
        decision = engine.predict({"action": "delete_prod"})
        assert decision is not None
        assert engine.predict_calls == 1

    def test_low_risk_not_checked(self):
        ledger = _ledger()
        engine = _FakeEngine("low")
        integrate_with_approval_engine(engine, ledger)
        engine.predict({"action": "read_doc"})  # 不应抛错


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
