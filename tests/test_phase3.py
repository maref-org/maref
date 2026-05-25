"""
Phase 3 测试: 形式化验证、性能优化、认证准备
"""

from __future__ import annotations

import asyncio
import time

import pytest

from maref.certification import (
    ControlEvidence,
    ISO27001Preparation,
    SelfBootstrapVerifier,
    SOC2Preparation,
    create_iso27001_preparation,
    create_self_bootstrap_verifier,
    create_soc2_preparation,
)
from maref.performance import (
    AsyncSecurityVerifier,
    BatchSecurityProcessor,
    DistributedTrustOptimizer,
    TrustScoreCache,
    create_async_security_verifier,
    create_batch_processor,
    create_distributed_trust_optimizer,
    create_trust_score_cache,
)
from maref.security.security_proofs import (
    SecurityProofError,
    SecurityPropertyProver,
    create_security_property_prover,
)


class TestSecurityProofs:
    """测试安全属性形式化证明"""

    def test_create_prover(self) -> None:
        prover = create_security_property_prover()
        assert isinstance(prover, SecurityPropertyProver)

    def test_prove_delegation_chain_unforgeability(self) -> None:
        import datetime

        from maref.security.trust_chain import DelegationCapability, DelegationChain

        now = datetime.datetime.now(datetime.timezone.utc)
        chain = DelegationChain.create("root-agent", max_depth=5)
        chain.add_delegation("root-agent", "agent-1", DelegationCapability.DELEGATE)
        chain.add_delegation("agent-1", "agent-2", DelegationCapability.READ)

        tampered = DelegationChain.create("root-agent", max_depth=5)
        tampered.add_delegation("root-agent", "agent-1", DelegationCapability.DELEGATE)
        tampered.add_delegation("agent-1", "attacker", DelegationCapability.ADMIN)

        result = SecurityPropertyProver.prove_delegation_chain_unforgeability(chain, tampered)
        assert result["proved"]
        assert result["hash_changed"]
        assert result["collision_impossible"]

    def test_prove_delegation_chain_fails_when_same(self) -> None:
        from maref.security.trust_chain import DelegationCapability, DelegationChain

        chain = DelegationChain.create("root-agent", max_depth=5)
        chain.add_delegation("root-agent", "agent-1", DelegationCapability.DELEGATE)

        with pytest.raises(SecurityProofError):
            SecurityPropertyProver.prove_delegation_chain_unforgeability(chain, chain)

    def test_prove_zero_trust_boundary(self) -> None:
        from maref.security.trust_boundary import TrustBoundaryManager
        boundary = TrustBoundaryManager()

        result = SecurityPropertyProver.prove_zero_trust_boundary_enforcement(
            boundary, "agent-1", "default"
        )
        assert result["proved"]

    def test_prove_atp_authentication(self) -> None:
        from maref.security.agent_identity import ATPHandshakeRequest, ATPKeyPair

        key_pair = ATPKeyPair(
            public_key=b"test_public",
            private_key=b"test_private",
            algorithm="hmac-sha256",
            key_id="test-key"
        )
        request = ATPHandshakeRequest(
            agent_did="did:test:agent",
            session_id="session-123",
            timestamp=int(time.time()),
            capabilities=["read"],
            nonce="abc123xyz789"
        )

        result = SecurityPropertyProver.prove_atp_authentication_security(
            key_pair, request, max_age_seconds=60
        )
        assert result["proved"]
        assert result["freshness"]
        assert result["signature_binding"]

    def test_prove_merkle_integrity(self) -> None:
        from maref.eivl.merkle_auditor import AuditEvidence, MerkleAuditor

        auditor = MerkleAuditor()
        evidence = AuditEvidence(
            evidence_id="proof-test-1",
            timestamp=time.time(),
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="evaluate",
            result={"score": 85.0},
            previous_hash="0" * 64,
            nonce=1,
        )
        auditor.add_evidence(evidence)

        result = SecurityPropertyProver.prove_merkle_integrity(auditor, "proof-test-1")
        assert result["proved"]
        assert result["proof_valid"]
        assert result["root_matches"]

    def test_run_all_proofs(self) -> None:
        result = SecurityPropertyProver.run_all_proofs()
        assert result["all_proved"]
        assert result["passed"] == result["proof_count"]


class TestTrustScoreCache:
    """测试信任评分缓存"""

    def test_create_cache(self) -> None:
        cache = create_trust_score_cache()
        assert isinstance(cache, TrustScoreCache)

    def test_cache_hit(self) -> None:
        cache = create_trust_score_cache(ttl_seconds=60)
        cache.set("agent-1", 85.0, [{"name": "task_completion", "value": 0.9}])

        cached = cache.get("agent-1")
        assert cached is not None
        assert cached.score == 85.0
        assert not cached.is_expired

    def test_cache_miss(self) -> None:
        cache = create_trust_score_cache()
        assert cache.get("nonexistent") is None
        assert cache._miss_count == 1

    def test_cache_expiration(self) -> None:
        cache = create_trust_score_cache(ttl_seconds=0.01)
        cache.set("agent-1", 85.0, [])
        time.sleep(0.02)

        cached = cache.get("agent-1")
        assert cached is None  # Expired

    def test_cache_invalidation(self) -> None:
        cache = create_trust_score_cache()
        cache.set("agent-1", 85.0, [])
        assert cache.invalidate("agent-1")
        assert cache.get("agent-1") is None

    def test_cache_stats(self) -> None:
        cache = create_trust_score_cache()
        cache.set("agent-1", 85.0, [])
        cache.get("agent-1")
        cache.get("agent-1")
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats["hit_count"] == 2
        assert stats["miss_count"] == 1
        assert stats["hit_rate"] == pytest.approx(2 / 3, rel=0.01)

    def test_lru_eviction(self) -> None:
        cache = create_trust_score_cache(max_size=2)
        cache.set("agent-1", 85.0, [])
        cache.set("agent-2", 80.0, [])
        cache.set("agent-3", 90.0, [])  # Should evict agent-1

        assert cache.get("agent-1") is None  # Evicted
        assert cache.get("agent-2") is not None
        assert cache.get("agent-3") is not None


class TestAsyncSecurityVerifier:
    """测试异步安全验证器"""

    def test_create_verifier(self) -> None:
        verifier = create_async_security_verifier()
        assert isinstance(verifier, AsyncSecurityVerifier)

    @pytest.mark.asyncio
    async def test_verify_identity_success(self) -> None:
        verifier = create_async_security_verifier()

        async def mock_verifier(agent_id: str) -> dict:
            return {"verified": True, "agent_id": agent_id}

        result = await verifier.verify_identity("agent-1", mock_verifier)
        assert result["verified"]
        assert "verification_latency_ms" in result

    @pytest.mark.asyncio
    async def test_verify_identity_timeout(self) -> None:
        verifier = create_async_security_verifier(default_timeout=0.01)

        async def slow_verifier(agent_id: str) -> dict:
            await asyncio.sleep(1)
            return {"verified": True}

        result = await verifier.verify_identity("agent-1", slow_verifier)
        assert not result["verified"]
        assert "timeout" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_verify_batch(self) -> None:
        verifier = create_async_security_verifier(max_concurrent=2)

        async def mock_verifier(agent_id: str) -> dict:
            return {"verified": True, "agent_id": agent_id}

        results = await verifier.verify_batch(["agent-1", "agent-2", "agent-3"], mock_verifier)
        assert len(results) == 3
        assert all(r["verified"] for r in results)

    def test_stats(self) -> None:
        verifier = create_async_security_verifier()
        stats = verifier.get_stats()
        assert stats["max_concurrent"] == 10


class TestBatchSecurityProcessor:
    """测试批量安全处理器"""

    def test_create_processor(self) -> None:
        processor = create_batch_processor()
        assert isinstance(processor, BatchSecurityProcessor)

    def test_submit_and_flush(self) -> None:
        processor = create_batch_processor(batch_size=5)

        op_id = processor.submit("trust_evaluation", [
            {"agent_id": f"agent-{i}"} for i in range(3)
        ])
        assert op_id.startswith("batch-")

        result = processor.flush()
        assert result["processed"] == 3

    def test_auto_flush_on_batch_size(self) -> None:
        processor = create_batch_processor(batch_size=3)

        processor.submit("trust_evaluation", [{"agent_id": "1"}])
        processor.submit("trust_evaluation", [{"agent_id": "2"}])
        # Third submission should trigger auto-flush (3 >= 3)
        processor.submit("trust_evaluation", [{"agent_id": "3"}])

        stats = processor.get_stats()
        assert stats["batch_count"] >= 1

    def test_empty_flush(self) -> None:
        processor = create_batch_processor()
        result = processor.flush()
        assert result["processed"] == 0

    def test_stats(self) -> None:
        processor = create_batch_processor()
        processor.submit("trust_evaluation", [{"agent_id": "1"}])
        processor.flush()

        stats = processor.get_stats()
        assert stats["total_items_processed"] == 1


class TestDistributedTrustOptimizer:
    """测试分布式信任优化器"""

    def test_create_optimizer(self) -> None:
        opt = create_distributed_trust_optimizer()
        assert isinstance(opt, DistributedTrustOptimizer)

    def test_propagate_trust_incremental(self) -> None:
        opt = create_distributed_trust_optimizer()

        result = opt.propagate_trust_incremental("agent-a", "agent-b", 10.0)
        assert result["propagated"]
        assert result["new_trust"] == 10.0

        # Incremental update
        result2 = opt.propagate_trust_incremental("agent-a", "agent-b", 5.0)
        assert result2["new_trust"] == 15.0
        assert result2["old_trust"] == 10.0

    def test_trust_bounds(self) -> None:
        opt = create_distributed_trust_optimizer()

        # Upper bound
        result = opt.propagate_trust_incremental("a", "b", 150.0)
        assert result["new_trust"] == 100.0  # Max

        # Lower bound
        opt.propagate_trust_incremental("a", "b", -200.0)
        vector = opt.get_trust_vector("a")
        assert vector["b"] == 0.0  # Min

    def test_handle_partition(self) -> None:
        opt = create_distributed_trust_optimizer()

        result = opt.handle_partition("partition-1", ["agent-1", "agent-2"], False)
        assert result["is_available"] == False
        assert result["action"] == "frozen"

    def test_merge_partition(self) -> None:
        opt = create_distributed_trust_optimizer()
        opt.handle_partition("p1", ["agent-1"], False)

        result = opt.merge_partition("p1")
        assert result["status"] == "merged"

    def test_get_stats(self) -> None:
        opt = create_distributed_trust_optimizer()
        opt.propagate_trust_incremental("a", "b", 50.0)

        stats = opt.get_stats()
        assert stats["agents_tracked"] >= 1


class TestISO27001Preparation:
    """测试 ISO 27001 认证准备"""

    def test_create_preparation(self) -> None:
        prep = create_iso27001_preparation()
        assert isinstance(prep, ISO27001Preparation)

    def test_add_evidence(self) -> None:
        prep = create_iso27001_preparation()

        evidence = ControlEvidence(
            control_id="A.5.1",
            control_name="Policies for information security",
            evidence_type="policy",
            description="MAREF Security Policy v1.0",
        )
        hash_val = prep.add_evidence(evidence)
        assert len(hash_val) == 64
        assert prep._compliance_status["A.5.1"] == "evidence_collected"

    def test_assess_control(self) -> None:
        prep = create_iso27001_preparation()

        result = prep.assess_control("A.5.1", "compliant", "Policy documented and approved")
        assert result["status"] == "compliant"

    def test_generate_soa(self) -> None:
        prep = create_iso27001_preparation()
        prep.assess_control("A.5.1", "compliant")

        soa = prep.generate_statement_of_applicability()
        assert "applicable_controls" in soa
        assert soa["total_controls"] > 0

    def test_get_readiness(self) -> None:
        prep = create_iso27001_preparation()

        readiness = prep.get_readiness_assessment()
        assert "readiness_percentage" in readiness
        assert "total_controls" in readiness


class TestSOC2Preparation:
    """测试 SOC 2 审计准备"""

    def test_create_preparation(self) -> None:
        prep = create_soc2_preparation()
        assert isinstance(prep, SOC2Preparation)

    def test_generate_control_matrix(self) -> None:
        prep = create_soc2_preparation()

        matrix = prep.generate_control_matrix()
        assert matrix["total_controls"] > 0
        assert len(matrix["controls"]) > 0

    def test_generate_audit_scope(self) -> None:
        prep = create_soc2_preparation()

        scope = prep.generate_audit_scope()
        assert scope["audit_type"] == "SOC 2 Type II"
        assert "in_scope_systems" in scope
        assert "MAREF Trust Engine" in scope["in_scope_systems"]


class TestSelfBootstrapVerifier:
    """测试自举验证器"""

    def test_create_verifier(self) -> None:
        verifier = create_self_bootstrap_verifier()
        assert isinstance(verifier, SelfBootstrapVerifier)

    def test_verify_own_module(self) -> None:
        verifier = create_self_bootstrap_verifier()

        source = '''
def safe_function():
    return 42
'''
        checks = [
            verifier.check_syntax_safety,
            verifier.check_import_integrity,
            verifier.check_no_hardcoded_secrets,
        ]

        result = verifier.verify_own_module("test_module", source, checks)
        assert result["all_passed"]
        assert result["checks_passed"] == 3

    def test_detect_dangerous_code(self) -> None:
        verifier = create_self_bootstrap_verifier()

        bad_source = '''
import os
os.system("rm -rf /")
'''
        result = verifier.check_syntax_safety(bad_source)
        assert not result["passed"]
        assert len(result["dangerous_patterns_found"]) > 0

    def test_detect_hardcoded_secrets(self) -> None:
        verifier = create_self_bootstrap_verifier()

        bad_source = '''
API_KEY = "sk-1234567890abcdef"
'''
        result = verifier.check_no_hardcoded_secrets(bad_source)
        assert not result["passed"]

    def test_trust_closure_not_achieved_initially(self) -> None:
        verifier = create_self_bootstrap_verifier()

        result = verifier.verify_trust_closure()
        assert not result["closure_achieved"]

    def test_trust_closure_achieved(self) -> None:
        verifier = create_self_bootstrap_verifier()

        safe_source = "def hello():\n    return 'safe'\n"
        checks = [verifier.check_syntax_safety, verifier.check_no_hardcoded_secrets]

        for i in range(3):
            verifier.verify_own_module(f"module-{i}", safe_source, checks)

        result = verifier.verify_trust_closure()
        assert result["closure_achieved"]
        assert result["modules_verified"] == 3

    def test_generate_bootstrap_report(self) -> None:
        verifier = create_self_bootstrap_verifier()

        report = verifier.generate_bootstrap_report()
        assert report["report_type"] == "self_bootstrap_verification"
        assert "trust_closure_achieved" in report
