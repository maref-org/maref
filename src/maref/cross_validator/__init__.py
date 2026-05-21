"""
Cross-Validator 模块

拜占庭交叉验证引擎，提供 AST 语义归一化和加权共识算法。
"""

from maref.cross_validator.ast_normalizer import (
    ASTNormalizer,
    SemanticEquivalenceChecker,
    SemanticFingerprint,
)
from maref.cross_validator.consensus_algorithm import (
    ConsensusResult,
    ConsensusStatus,
    CrossValidator,
    Proposal,
    ValidatorNode,
    Vote,
    VoteValue,
    WeightedConsensusEngine,
    create_consensus_engine,
    create_cross_validator,
)

__all__ = [
    "ASTNormalizer",
    "SemanticEquivalenceChecker",
    "SemanticFingerprint",
    "WeightedConsensusEngine",
    "CrossValidator",
    "ValidatorNode",
    "Vote",
    "Proposal",
    "ConsensusResult",
    "ConsensusStatus",
    "VoteValue",
    "create_consensus_engine",
    "create_cross_validator",
]