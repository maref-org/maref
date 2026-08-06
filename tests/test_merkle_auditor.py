"""
Merkle 审计链测试
"""

from __future__ import annotations

import time

from maref.eivl.merkle_auditor import (
    AuditChainIntegrator,
    AuditEvidence,
    MerkleAuditor,
    create_audit_chain_integrator,
    create_merkle_auditor,
)


class TestAuditEvidence:
    """测试审计证据"""

    def test_create_evidence(self) -> None:
        """测试创建证据"""
        evidence = AuditEvidence(
            evidence_id="test-1",
            timestamp=time.time(),
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="evaluate",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        assert evidence.evidence_id == "test-1"
        assert evidence.source_agent == "agent-a"

    def test_compute_hash(self) -> None:
        """测试哈希计算"""
        evidence = AuditEvidence(
            evidence_id="test-1",
            timestamp=1234567890.0,
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent=None,
            action="evaluate",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        hash1 = evidence.compute_hash()
        hash2 = evidence.compute_hash()

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_hash_uniqueness(self) -> None:
        """测试哈希唯一性"""
        evidence1 = AuditEvidence(
            evidence_id="test-1",
            timestamp=1234567890.0,
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent=None,
            action="evaluate",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        evidence2 = AuditEvidence(
            evidence_id="test-2",
            timestamp=1234567890.0,
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent=None,
            action="evaluate",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        assert evidence1.compute_hash() != evidence2.compute_hash()


class TestMerkleAuditor:
    """测试 Merkle 审计器"""

    def test_create_auditor(self) -> None:
        """测试创建审计器"""
        auditor = create_merkle_auditor()
        assert isinstance(auditor, MerkleAuditor)

    def test_add_single_evidence(self) -> None:
        """测试添加单个证据"""
        auditor = create_merkle_auditor()

        evidence = AuditEvidence(
            evidence_id="ev-1",
            timestamp=time.time(),
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="test",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        hash_value = auditor.add_evidence(evidence)

        assert hash_value is not None
        assert len(hash_value) == 64
        assert auditor.get_root_hash() == hash_value

    def test_add_multiple_evidence(self) -> None:
        """测试添加多个证据"""
        auditor = create_merkle_auditor()

        for i in range(5):
            evidence = AuditEvidence(
                evidence_id=f"ev-{i}",
                timestamp=time.time(),
                evidence_type="trust_evaluation",
                source_agent="agent-a",
                target_agent="agent-b",
                action="test",
                result={"index": i},
                previous_hash="0" * 64,
                nonce=i,
            )
            auditor.add_evidence(evidence)

        root_hash = auditor.get_root_hash()
        assert root_hash is not None

        tree_info = auditor.get_tree_info()
        assert tree_info["leaf_count"] == 5
        assert tree_info["evidence_count"] == 5

    def test_generate_and_verify_proof(self) -> None:
        """测试生成和验证证明"""
        auditor = create_merkle_auditor()

        evidence = AuditEvidence(
            evidence_id="ev-proof",
            timestamp=time.time(),
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="test",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        evidence_hash = auditor.add_evidence(evidence)

        # 添加更多证据使树更复杂
        for i in range(3):
            ev = AuditEvidence(
                evidence_id=f"ev-extra-{i}",
                timestamp=time.time(),
                evidence_type="access_control",
                source_agent="agent-b",
                target_agent=None,
                action="read",
                result={"allowed": True},
                previous_hash=evidence_hash,
                nonce=i + 10,
            )
            auditor.add_evidence(ev)

        proof = auditor.generate_proof(evidence_hash)

        assert proof is not None
        assert proof.target_hash == evidence_hash
        assert proof.root_hash == auditor.get_root_hash()

        # 验证证明
        is_valid = proof.verify()
        assert is_valid == True

    def test_verify_evidence_integrity(self) -> None:
        """测试验证证据完整性"""
        auditor = create_merkle_auditor()

        evidence = AuditEvidence(
            evidence_id="ev-integrity",
            timestamp=time.time(),
            evidence_type="trust_evaluation",
            source_agent="agent-a",
            target_agent="agent-b",
            action="test",
            result={"score": 0.9},
            previous_hash="0" * 64,
            nonce=1,
        )

        auditor.add_evidence(evidence)

        result = auditor.verify_evidence_integrity("ev-integrity")

        assert result["valid"] == True
        assert result["evidence_id"] == "ev-integrity"

    def test_verify_nonexistent_evidence(self) -> None:
        """测试验证不存在的证据"""
        auditor = create_merkle_auditor()

        result = auditor.verify_evidence_integrity("nonexistent")

        assert result["valid"] == False
        assert result["reason"] == "Evidence not found"

    def test_compare_trees(self) -> None:
        """测试比较两棵树"""
        auditor1 = create_merkle_auditor()
        auditor2 = create_merkle_auditor()

        # 添加相同证据到两棵树
        for i in range(3):
            ev = AuditEvidence(
                evidence_id=f"ev-{i}",
                timestamp=time.time(),
                evidence_type="test",
                source_agent="agent-a",
                target_agent=None,
                action="test",
                result={"index": i},
                previous_hash="0" * 64,
                nonce=i,
            )
            auditor1.add_evidence(ev)
            auditor2.add_evidence(ev)

        comparison = auditor1.compare_trees(auditor2)

        assert comparison["consistent"] == True
        assert comparison["root_match"] == True

    def test_compare_different_trees(self) -> None:
        """测试比较不同的树"""
        auditor1 = create_merkle_auditor()
        auditor2 = create_merkle_auditor()

        for i in range(3):
            ev1 = AuditEvidence(
                evidence_id=f"ev-a-{i}",
                timestamp=time.time(),
                evidence_type="test",
                source_agent="agent-a",
                target_agent=None,
                action="test",
                result={"index": i},
                previous_hash="0" * 64,
                nonce=i,
            )
            auditor1.add_evidence(ev1)

            ev2 = AuditEvidence(
                evidence_id=f"ev-b-{i}",
                timestamp=time.time(),
                evidence_type="test",
                source_agent="agent-b",
                target_agent=None,
                action="test",
                result={"index": i},
                previous_hash="0" * 64,
                nonce=i + 100,
            )
            auditor2.add_evidence(ev2)

        comparison = auditor1.compare_trees(auditor2)

        assert comparison["consistent"] == False
        assert comparison["root_match"] == False


class TestAuditChainIntegrator:
    """测试审计链集成器"""

    def test_create_integrator(self) -> None:
        """测试创建集成器"""
        integrator = create_audit_chain_integrator()
        assert isinstance(integrator, AuditChainIntegrator)

    def test_record_trust_evaluation(self) -> None:
        """测试记录信任评估"""
        integrator = create_audit_chain_integrator()

        evidence_hash = integrator.record_trust_evaluation(
            agent_id="agent-1",
            trust_score=85.0,
            chain_risks=[{"name": "depth_exceeded"}],
        )

        assert evidence_hash is not None
        assert len(evidence_hash) == 64

    def test_record_access_control(self) -> None:
        """测试记录访问控制"""
        integrator = create_audit_chain_integrator()

        evidence_hash = integrator.record_access_control(
            agent_id="agent-1",
            action="read",
            resource="user_data:123",
            allowed=True,
            context={"ip": "127.0.0.1"},
        )

        assert evidence_hash is not None

    def test_record_delegation(self) -> None:
        """测试记录委托"""
        integrator = create_audit_chain_integrator()

        evidence_hash = integrator.record_delegation(
            delegator_id="agent-a",
            delegatee_id="agent-b",
            capabilities=["read", "execute"],
            chain_id="chain-1",
        )

        assert evidence_hash is not None

    def test_chain_integrity(self) -> None:
        """测试链完整性"""
        integrator = create_audit_chain_integrator()

        # 记录多个事件
        h1 = integrator.record_trust_evaluation("agent-1", 80.0, [])
        h2 = integrator.record_access_control("agent-1", "read", "res-1", True)
        h3 = integrator.record_delegation("agent-1", "agent-2", ["execute"])

        # 验证树中有3个证据
        tree_info = integrator.merkle.get_tree_info()
        assert tree_info["evidence_count"] == 3

        # 验证摘要
        summary = integrator.get_audit_summary()
        assert summary["latest_hash"] == h3
        assert summary["tree_info"]["evidence_count"] == 3
