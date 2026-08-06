from __future__ import annotations

import time

import pytest

from maref.cross_validator.consensus_algorithm import (
    VoteValue,
    WeightedConsensusEngine,
)
from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor
from maref.security.agent_identity import ATPHandshakeRequest, ATPKeyPair
from maref.security.security_proofs import SecurityProofError, SecurityPropertyProver
from maref.security.trust_boundary import TrustBoundaryManager
from maref.security.trust_chain import DelegationCapability, DelegationChain


class TestSecurityPropertyProver:
    def test_proof_error_is_exception(self) -> None:
        exc = SecurityProofError("test error")
        assert isinstance(exc, Exception)
        assert str(exc) == "test error"

    def test_create_prover(self) -> None:
        from maref.security.security_proofs import create_security_property_prover

        prover = create_security_property_prover()
        assert isinstance(prover, SecurityPropertyProver)

    # --- Proof 1: Delegation Chain Unforgeability ---

    def test_delegation_chain_unforgeability_detects_tamper(self) -> None:
        chain = DelegationChain.create("root-agent", max_depth=5)
        chain.add_delegation("root-agent", "agent-1", DelegationCapability.DELEGATE)
        chain.add_delegation("agent-1", "agent-2", DelegationCapability.READ)

        tampered = DelegationChain.create("root-agent", max_depth=5)
        tampered.add_delegation("root-agent", "agent-1", DelegationCapability.DELEGATE)
        tampered.add_delegation("agent-1", "attacker", DelegationCapability.ADMIN)

        result = SecurityPropertyProver.prove_delegation_chain_unforgeability(chain, tampered)
        assert result["proved"] is True
        assert result["hash_changed"] is True
        assert result["collision_impossible"] is True

    def test_delegation_chain_unforgeability_raises_on_identical(self) -> None:
        chain = DelegationChain.create("root-agent", max_depth=5)
        chain.add_delegation("root-agent", "agent-1", DelegationCapability.READ)

        with pytest.raises(SecurityProofError, match="hash should change"):
            SecurityPropertyProver.prove_delegation_chain_unforgeability(chain, chain)

    # --- Proof 2: Zero Trust Boundary Enforcement ---

    def test_zero_trust_boundary_enforcement_with_manager(self) -> None:
        manager = TrustBoundaryManager()
        result = SecurityPropertyProver.prove_zero_trust_boundary_enforcement(
            manager, "agent-1", "default"
        )
        assert result["proved"] is True

    def test_zero_trust_boundary_enforcement_with_custom_boundary(self) -> None:
        manager = TrustBoundaryManager()
        result = SecurityPropertyProver.prove_zero_trust_boundary_enforcement(
            manager, "agent-test", "production"
        )
        assert result["proved"] is True

    # --- Proof 3: ATP Authentication Security ---

    def test_atp_authentication_security_success(self) -> None:
        key_pair = ATPKeyPair(
            public_key=b"test_public",
            private_key=b"test_private",
            algorithm="hmac-sha256",
            key_id="test-key",
        )
        request = ATPHandshakeRequest(
            agent_did="did:test:agent",
            session_id="session-123",
            timestamp=int(time.time()),
            capabilities=["read"],
            nonce="abc123xyz",
        )
        result = SecurityPropertyProver.prove_atp_authentication_security(key_pair, request)
        assert result["proved"] is True
        assert result["freshness"] is True
        assert result["signature_binding"] is True
        assert result["nonce_entropy"] is True

    def test_atp_authentication_fails_on_expired_request(self) -> None:
        key_pair = ATPKeyPair(
            public_key=b"pk",
            private_key=b"pk",
            algorithm="hmac-sha256",
            key_id="k",
        )
        request = ATPHandshakeRequest(
            agent_did="did:test:agent",
            session_id="sess-1",
            timestamp=0,
            capabilities=["read"],
            nonce="abc123xyz",
        )
        with pytest.raises(SecurityProofError, match="not fresh"):
            SecurityPropertyProver.prove_atp_authentication_security(key_pair, request, max_age_seconds=1)

    def test_atp_authentication_fails_on_short_nonce(self) -> None:
        key_pair = ATPKeyPair(
            public_key=b"pk",
            private_key=b"pk",
            algorithm="hmac-sha256",
            key_id="k",
        )
        request = ATPHandshakeRequest(
            agent_did="did:test:agent",
            session_id="sess-1",
            timestamp=int(time.time()),
            capabilities=["read"],
            nonce="ab",
        )
        with pytest.raises(SecurityProofError, match="sufficient entropy"):
            SecurityPropertyProver.prove_atp_authentication_security(key_pair, request)

    # --- Proof 4: Consensus Agreement ---

    def test_consensus_agreement_when_no_consensus(self) -> None:
        engine = WeightedConsensusEngine()
        result = SecurityPropertyProver.prove_consensus_agreement(
            engine, "nonexistent-proposal", VoteValue.APPROVE
        )
        assert result["proved"] is True
        assert result["consensus_reached"] is False

    # --- Proof 5: Merkle Integrity ---

    def test_merkle_integrity_proof(self) -> None:
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
        assert result["proved"] is True
        assert result["proof_valid"] is True
        assert result["root_matches"] is True

    def test_merkle_integrity_raises_on_missing_evidence(self) -> None:
        auditor = MerkleAuditor()
        with pytest.raises(SecurityProofError, match="not found"):
            SecurityPropertyProver.prove_merkle_integrity(auditor, "nonexistent")

    def test_tampered_merkle_root_detected(self) -> None:
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

    # --- Integration: run_all_proofs ---

    def test_run_all_proofs_passes_all(self) -> None:
        result = SecurityPropertyProver.run_all_proofs()
        assert result["all_proved"] is True
        assert result["proof_count"] >= 4
        assert result["passed"] >= 4
        assert result["failed"] == 0

    def test_run_all_proofs_returns_results_for_each(self) -> None:
        result = SecurityPropertyProver.run_all_proofs()
        assert "delegation_chain_unforgeability" in result["results"]
        assert "zero_trust_boundary" in result["results"]
        assert "atp_authentication" in result["results"]
        assert "consensus_agreement" in result["results"]
        assert "merkle_integrity" in result["results"]

    def test_run_all_proofs_individual_results_are_proved(self) -> None:
        result = SecurityPropertyProver.run_all_proofs()
        for name, proof in result["results"].items():
            assert proof.get("proved", False), f"{name} should be proved"
