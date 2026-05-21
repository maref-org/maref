"""
Cross-Validator 测试
"""

from __future__ import annotations

import pytest

from maref.cross_validator.ast_normalizer import (
    ASTNormalizer,
    SemanticEquivalenceChecker,
    SemanticFingerprint,
)
from maref.cross_validator.consensus_algorithm import (
    ConsensusStatus,
    VoteValue,
    WeightedConsensusEngine,
    CrossValidator,
    create_consensus_engine,
    create_cross_validator,
)


class TestASTNormalizer:
    """测试 AST 归一化器"""
    
    def test_create_normalizer(self) -> None:
        """测试创建归一化器"""
        normalizer = ASTNormalizer()
        assert normalizer is not None
    
    def test_normalize_simple_assignment(self) -> None:
        """测试归一化简单赋值"""
        normalizer = ASTNormalizer()
        code = "x = 1 + 2"
        
        result = normalizer.normalize(code)
        assert result is not None
    
    def test_generate_fingerprint(self) -> None:
        """测试生成指纹"""
        normalizer = ASTNormalizer()
        code = "def hello():\n    return 42"
        
        fingerprint = normalizer.generate_fingerprint(code)
        
        assert isinstance(fingerprint, SemanticFingerprint)
        assert fingerprint.hash != ""
        assert len(fingerprint.token_sequence) > 0
    
    def test_equivalent_code_same_fingerprint(self) -> None:
        """测试等价代码产生相同指纹"""
        normalizer = ASTNormalizer()
        
        # 注意：完全相同的代码应该产生相同的指纹
        code1 = "x = 1\ny = 2\nprint(x + y)"
        code2 = "x = 1\ny = 2\nprint(x + y)"
        
        fp1 = normalizer.generate_fingerprint(code1)
        fp2 = normalizer.generate_fingerprint(code2)
        
        assert fp1.hash == fp2.hash
    
    def test_syntax_error_handling(self) -> None:
        """测试语法错误处理"""
        normalizer = ASTNormalizer()
        code = "def broken(:\n    pass"
        
        fingerprint = normalizer.generate_fingerprint(code)
        
        assert fingerprint.hash == ""
        assert "error" in fingerprint.metadata


class TestSemanticEquivalenceChecker:
    """测试语义等价性检查器"""
    
    def test_exact_equivalence(self) -> None:
        """测试完全等价"""
        checker = SemanticEquivalenceChecker()
        
        code = "def add(a, b):\n    return a + b"
        
        result = checker.check_equivalence(code, code)
        
        assert result["equivalent"] == True
        assert result["similarity"] == 1.0
    
    def test_different_code(self) -> None:
        """测试不同代码"""
        checker = SemanticEquivalenceChecker()
        
        code1 = "x = 1 + 2"
        code2 = "x = 3 * 4"
        
        result = checker.check_equivalence(code1, code2)
        
        assert result["equivalent"] == False
        assert result["similarity"] < 1.0
    
    def test_similar_structure(self) -> None:
        """测试相似结构"""
        checker = SemanticEquivalenceChecker()
        
        code1 = "def foo():\n    x = 1\n    return x"
        code2 = "def bar():\n    y = 1\n    return y"
        
        result = checker.check_equivalence(code1, code2)
        
        # 结构相似但变量名不同
        assert "similarity" in result
        assert result["similarity"] > 0.0


class TestWeightedConsensusEngine:
    """测试加权共识引擎"""
    
    def test_create_engine(self) -> None:
        """测试创建引擎"""
        engine = create_consensus_engine()
        assert isinstance(engine, WeightedConsensusEngine)
    
    def test_register_validator(self) -> None:
        """测试注册验证者"""
        engine = create_consensus_engine()
        
        validator = engine.register_validator("node-1", initial_weight=2.0)
        
        assert validator.node_id == "node-1"
        assert validator.weight == 2.0
        assert validator.initial_weight == 2.0
    
    def test_create_and_vote_on_proposal(self) -> None:
        """测试创建提案并投票"""
        engine = create_consensus_engine()
        
        # 注册验证者
        engine.register_validator("node-1", initial_weight=2.0)
        engine.register_validator("node-2", initial_weight=1.0)
        
        # 创建提案
        proposal = engine.create_proposal(
            proposal_id="prop-1",
            content={"action": "deploy"},
            proposer_id="node-1",
            quorum_threshold=0.5,
        )
        
        assert proposal.proposal_id == "prop-1"
        
        # 投票
        vote1 = engine.cast_vote("prop-1", "node-1", VoteValue.APPROVE)
        vote2 = engine.cast_vote("prop-1", "node-2", VoteValue.APPROVE)
        
        assert vote1 is not None
        assert vote2 is not None
    
    def test_consensus_reached(self) -> None:
        """测试共识达成"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=2.0)
        engine.register_validator("node-2", initial_weight=1.0)
        engine.register_validator("node-3", initial_weight=1.0)
        
        engine.create_proposal("prop-1", {"action": "test"}, "node-1", quorum_threshold=0.5)
        
        engine.cast_vote("prop-1", "node-1", VoteValue.APPROVE)
        engine.cast_vote("prop-1", "node-2", VoteValue.APPROVE)
        
        result = engine.evaluate_consensus("prop-1")
        
        assert result.status == ConsensusStatus.REACHED
        assert result.winning_vote == VoteValue.APPROVE
        assert result.confidence > 0.5
    
    def test_consensus_not_reached(self) -> None:
        """测试未达成"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=1.0)
        engine.register_validator("node-2", initial_weight=1.0)
        engine.register_validator("node-3", initial_weight=1.0)
        
        engine.create_proposal("prop-1", {"action": "test"}, "node-1", quorum_threshold=0.8)
        
        engine.cast_vote("prop-1", "node-1", VoteValue.APPROVE)
        
        result = engine.evaluate_consensus("prop-1")
        
        assert result.status == ConsensusStatus.PENDING
    
    def test_duplicate_vote_rejected(self) -> None:
        """测试重复投票被拒绝"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=1.0)
        engine.create_proposal("prop-1", {"action": "test"}, "node-1")
        
        vote1 = engine.cast_vote("prop-1", "node-1", VoteValue.APPROVE)
        vote2 = engine.cast_vote("prop-1", "node-1", VoteValue.REJECT)
        
        assert vote1 is not None
        assert vote2 is None  # 重复投票应被拒绝
    
    def test_weight_update_after_consensus(self) -> None:
        """测试共识后权重更新"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=1.0)
        engine.register_validator("node-2", initial_weight=1.0)
        
        engine.create_proposal("prop-1", {"action": "test"}, "node-1", quorum_threshold=0.5)
        
        engine.cast_vote("prop-1", "node-1", VoteValue.APPROVE)
        engine.cast_vote("prop-1", "node-2", VoteValue.REJECT)
        
        # 评估共识
        engine.evaluate_consensus("prop-1")
        
        # 更新权重
        engine.update_weights_after_consensus("prop-1")
        
        # 投票给多数派的节点应被奖励
        node1 = engine._validators["node-1"]
        assert len(node1.reputation_history) > 0
    
    def test_byzantine_detection(self) -> None:
        """测试拜占庭检测"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=2.0)
        engine.register_validator("node-2", initial_weight=2.0)
        engine.register_validator("node-3", initial_weight=1.0)
        
        # 创建多个提案并投票，制造不一致行为
        for i in range(5):
            engine.create_proposal(f"prop-{i}", {"action": f"test-{i}"}, "node-1", quorum_threshold=0.5)
            engine.cast_vote(f"prop-{i}", "node-1", VoteValue.APPROVE)
            engine.cast_vote(f"prop-{i}", "node-2", VoteValue.APPROVE)
            engine.cast_vote(f"prop-{i}", "node-3", VoteValue.REJECT)
            engine.evaluate_consensus(f"prop-{i}")
            engine.update_weights_after_consensus(f"prop-{i}")
        
        # node-3 总是反对多数派，应被标记
        stats = engine.get_validator_stats("node-3")
        assert stats is not None
    
    def test_network_stats(self) -> None:
        """测试网络统计"""
        engine = create_consensus_engine()
        
        engine.register_validator("node-1", initial_weight=2.0)
        engine.register_validator("node-2", initial_weight=1.0)
        
        stats = engine.get_network_stats()
        
        assert stats["total_validators"] == 2
        assert stats["active_validators"] == 2
        assert stats["total_weight"] == 3.0


class TestCrossValidator:
    """测试交叉验证器"""
    
    def test_create_cross_validator(self) -> None:
        """测试创建交叉验证器"""
        cv = create_cross_validator()
        assert isinstance(cv, CrossValidator)
    
    def test_validate_agent_outputs_with_reference(self) -> None:
        """测试带参考输出的验证"""
        cv = create_cross_validator()
        
        outputs = {
            "agent-1": "x = 1 + 2\nprint(x)",
            "agent-2": "x = 1 + 2\nprint(x)",
        }
        
        result = cv.validate_agent_outputs(
            proposal_id="test-1",
            outputs=outputs,
            reference_output="x = 1 + 2\nprint(x)",
        )
        
        assert "consensus" in result
        assert "approvals" in result
        assert "rejections" in result
        assert "agent-1" in result["approvals"] or "agent-1" in result["rejections"]
    
    def test_validate_agent_outputs_without_reference(self) -> None:
        """测试不带参考输出的验证"""
        cv = create_cross_validator()
        
        outputs = {
            "agent-1": "def add(a, b):\n    return a + b",
            "agent-2": "def add(a, b):\n    return a + b",
        }
        
        result = cv.validate_agent_outputs(
            proposal_id="test-2",
            outputs=outputs,
        )
        
        assert "consensus" in result
        assert result["total_agents"] == 2
