from __future__ import annotations

import time

from maref.security.security_proofs import SecurityProofError, SecurityPropertyProver


class TestSecurityProofs:
    def test_proof_error_is_exception(self) -> None:
        exc = SecurityProofError("test error")
        assert isinstance(exc, Exception)
        assert str(exc) == "test error"

    def test_merkle_integrity_proof(self) -> None:
        from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor

        auditor = MerkleAuditor()
        evidence = AuditEvidence(
            evidence_id="merkle-test-1",
            timestamp=time.time(),
            evidence_type="integrity_check",
            source_agent="agent-a",
            target_agent="agent-b",
            action="verify",
            result={"hash": "abc123"},
            previous_hash="0" * 64,
            nonce=1,
        )
        auditor.add_evidence(evidence)
        result = SecurityPropertyProver.prove_merkle_integrity(auditor, "merkle-test-1")
        assert result["proved"]
        assert result["proof_valid"]
        assert result["root_matches"]

    def test_tampered_merkle_root_detected(self) -> None:
        from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor

        auditor = MerkleAuditor()
        evidence = AuditEvidence(
            evidence_id="tamper-test",
            timestamp=time.time(),
            evidence_type="integrity_check",
            source_agent="agent-a",
            target_agent="agent-b",
            action="verify",
            result={"hash": "original"},
            previous_hash="0" * 64,
            nonce=1,
        )
        auditor.add_evidence(evidence)

        proof = SecurityPropertyProver.prove_merkle_integrity(auditor, "tamper-test")
        root_before = proof["root_hash"]

        tampered = AuditEvidence(
            evidence_id="tamper-test",
            timestamp=time.time(),
            evidence_type="integrity_check",
            source_agent="attacker",
            target_agent="agent-b",
            action="verify",
            result={"hash": "tampered"},
            previous_hash="0" * 64,
            nonce=2,
        )
        auditor.add_evidence(tampered)
        auditor._rebuild_tree()

        root_after = auditor.get_root_hash()
        assert root_before != root_after
