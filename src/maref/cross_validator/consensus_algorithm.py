"""
加权共识引擎

Cross-Validator 核心组件：实现拜占庭容错的加权共识算法。
基于 multiagents.org 论文中的动态权重调整理念，支持信任传播和异常检测。

核心概念:
1. 验证者节点具有动态权重（基于历史行为）
2. 加权投票聚合
3. 拜占庭容错阈值计算
4. 信任传播和惩罚机制
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConsensusStatus(str, Enum):
    """共识状态"""

    PENDING = "pending"
    REACHED = "reached"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    BYZANTINE_DETECTED = "byzantine_detected"


class VoteValue(str, Enum):
    """投票值"""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


@dataclass
class ValidatorNode:
    """验证者节点"""

    node_id: str
    weight: float = 1.0  # 当前权重
    initial_weight: float = 1.0  # 初始权重
    trust_score: float = 1.0  # 信任分数 (0.0-1.0)
    reputation_history: list[dict[str, Any]] = field(default_factory=list)
    is_byzantine: bool = False  # 是否被标记为拜占庭节点
    is_active: bool = True

    def update_weight(self, new_weight: float) -> None:
        """更新权重"""
        self.weight = max(0.0, min(new_weight, 10.0))  # 限制权重范围

    def penalize(self, factor: float = 0.5) -> None:
        """惩罚节点（降低权重）"""
        self.weight *= factor
        self.trust_score *= factor
        self.reputation_history.append(
            {
                "timestamp": time.time(),
                "action": "penalize",
                "factor": factor,
                "weight_after": self.weight,
            }
        )

    def reward(self, factor: float = 1.1) -> None:
        """奖励节点（提升权重）"""
        self.weight = min(self.weight * factor, self.initial_weight * 2)
        self.trust_score = min(self.trust_score * 1.05, 1.0)
        self.reputation_history.append(
            {
                "timestamp": time.time(),
                "action": "reward",
                "factor": factor,
                "weight_after": self.weight,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "weight": round(self.weight, 3),
            "trust_score": round(self.trust_score, 3),
            "is_byzantine": self.is_byzantine,
            "is_active": self.is_active,
        }


@dataclass
class Vote:
    """投票 (Ed25519-signed for verifiable evidence)"""

    validator_id: str
    vote_value: VoteValue
    proposal_id: str
    timestamp: float
    justification: str | None = None
    signature: str | None = None  # Ed25519 hex signature

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "validator_id": self.validator_id,
            "vote": self.vote_value.value,
            "proposal_id": self.proposal_id,
            "timestamp": self.timestamp,
            "justification": self.justification,
        }
        if self.signature:
            result["signature"] = self.signature
        return result


@dataclass
class Proposal:
    """提案"""

    proposal_id: str
    content: dict[str, Any]
    proposer_id: str
    timestamp: float
    quorum_threshold: float = 0.67  # 默认 2/3 多数
    byzantine_threshold: float = 0.33  # 拜占庭节点容忍阈值

    def compute_hash(self) -> str:
        """计算提案哈希"""
        data = f"{self.proposal_id}:{self.proposer_id}:{self.timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "timestamp": self.timestamp,
            "quorum_threshold": self.quorum_threshold,
            "byzantine_threshold": self.byzantine_threshold,
        }


@dataclass
class ConsensusResult:
    """共识结果"""

    status: ConsensusStatus
    proposal_id: str
    winning_vote: VoteValue | None
    approve_weight: float
    reject_weight: float
    abstain_weight: float
    total_weight: float
    participation_rate: float
    byzantine_nodes_detected: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 置信度
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "proposal_id": self.proposal_id,
            "winning_vote": self.winning_vote.value if self.winning_vote else None,
            "approve_weight": round(self.approve_weight, 3),
            "reject_weight": round(self.reject_weight, 3),
            "abstain_weight": round(self.abstain_weight, 3),
            "total_weight": round(self.total_weight, 3),
            "participation_rate": round(self.participation_rate, 3),
            "byzantine_nodes": self.byzantine_nodes_detected,
            "confidence": round(self.confidence, 3),
        }


class WeightedConsensusEngine:
    """
    加权共识引擎

    实现动态权重的拜占庭容错共识算法。
    """

    def __init__(self):
        self._validators: dict[str, ValidatorNode] = {}
        self._votes: dict[str, list[Vote]] = {}  # proposal_id -> votes
        self._proposals: dict[str, Proposal] = {}
        self._consensus_history: list[ConsensusResult] = []

    def has_validator(self, node_id: str) -> bool:
        """Check if a validator is already registered."""
        return node_id in self._validators

    def register_validator(
        self, node_id: str, initial_weight: float = 1.0, trust_score: float = 1.0
    ) -> ValidatorNode:
        """
        注册验证者节点

        Args:
            node_id: 节点唯一标识
            initial_weight: 初始权重
            trust_score: 初始信任分数

        Returns:
            ValidatorNode: 创建的验证者节点
        """
        validator = ValidatorNode(
            node_id=node_id,
            weight=initial_weight,
            initial_weight=initial_weight,
            trust_score=trust_score,
        )
        self._validators[node_id] = validator
        return validator

    def unregister_validator(self, node_id: str) -> bool:
        """注销验证者节点"""
        if node_id in self._validators:
            del self._validators[node_id]
            return True
        return False

    def create_proposal(
        self,
        proposal_id: str,
        content: dict[str, Any],
        proposer_id: str,
        quorum_threshold: float = 0.67,
    ) -> Proposal:
        """
        创建提案

        Args:
            proposal_id: 提案唯一标识
            content: 提案内容
            proposer_id: 提案者 ID
            quorum_threshold: 共识阈值

        Returns:
            Proposal: 创建的提案
        """
        proposal = Proposal(
            proposal_id=proposal_id,
            content=content,
            proposer_id=proposer_id,
            timestamp=time.time(),
            quorum_threshold=quorum_threshold,
        )
        self._proposals[proposal_id] = proposal
        self._votes[proposal_id] = []
        return proposal

    def cast_vote(
        self,
        proposal_id: str,
        validator_id: str,
        vote_value: VoteValue,
        justification: str | None = None,
        signer: Any | None = None,
    ) -> Vote | None:
        """
        投票 (可选 Ed25519 签名)

        Args:
            proposal_id: 提案 ID
            validator_id: 验证者 ID
            vote_value: 投票值
            justification: 投票理由
            signer: Ed25519KeyPair 实例，用于签名投票

        Returns:
            Vote: 投票记录，如果失败返回 None
        """
        # 检查提案是否存在
        if proposal_id not in self._proposals:
            return None

        # 检查验证者是否存在且活跃
        validator = self._validators.get(validator_id)
        if not validator or not validator.is_active:
            return None

        # 检查验证者是否已投票
        existing_votes = self._votes.get(proposal_id, [])
        if any(v.validator_id == validator_id for v in existing_votes):
            return None  # 已投票，不允许重复投票

        vote = Vote(
            validator_id=validator_id,
            vote_value=vote_value,
            proposal_id=proposal_id,
            timestamp=time.time(),
            justification=justification,
        )

        # Ed25519 签名
        if signer is not None:
            try:
                msg = f"{validator_id}|{vote_value.value}|{proposal_id}|{vote.timestamp}".encode()
                sig = signer.sign(msg)
                vote.signature = sig.hex()
            except Exception:
                vote.signature = "sign_error"

        self._votes[proposal_id].append(vote)
        return vote

    def evaluate_consensus(self, proposal_id: str) -> ConsensusResult:
        """
        评估共识状态

        Args:
            proposal_id: 提案 ID

        Returns:
            ConsensusResult: 共识结果
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return ConsensusResult(
                status=ConsensusStatus.FAILED,
                proposal_id=proposal_id,
                winning_vote=None,
                approve_weight=0.0,
                reject_weight=0.0,
                abstain_weight=0.0,
                total_weight=0.0,
                participation_rate=0.0,
                confidence=0.0,
            )

        votes = self._votes.get(proposal_id, [])

        # 计算总权重
        total_weight = sum(v.weight for v in self._validators.values() if v.is_active)

        # 统计投票权重
        approve_weight = 0.0
        reject_weight = 0.0
        abstain_weight = 0.0

        voted_validators: set[str] = set()

        for vote in votes:
            validator = self._validators.get(vote.validator_id)
            if not validator or not validator.is_active:
                continue

            voted_validators.add(vote.validator_id)

            if vote.vote_value == VoteValue.APPROVE:
                approve_weight += validator.weight
            elif vote.vote_value == VoteValue.REJECT:
                reject_weight += validator.weight
            elif vote.vote_value == VoteValue.ABSTAIN:
                abstain_weight += validator.weight

        participation_rate = (
            sum(self._validators[v].weight for v in voted_validators) / total_weight
            if total_weight > 0
            else 0.0
        )

        # 检测拜占庭行为
        byzantine_nodes = self._detect_byzantine_behavior(proposal_id, votes)

        # 判断共识是否达成
        winning_vote = None
        status = ConsensusStatus.PENDING
        confidence = 0.0

        if participation_rate >= proposal.quorum_threshold:
            # 达到法定人数
            if approve_weight >= total_weight * proposal.quorum_threshold:
                winning_vote = VoteValue.APPROVE
                status = ConsensusStatus.REACHED
                confidence = approve_weight / total_weight
            elif reject_weight >= total_weight * proposal.quorum_threshold:
                winning_vote = VoteValue.REJECT
                status = ConsensusStatus.REACHED
                confidence = reject_weight / total_weight
            else:
                status = ConsensusStatus.INCONCLUSIVE
                confidence = max(approve_weight, reject_weight) / total_weight

        # 如果检测到拜占庭节点，标记状态
        if byzantine_nodes:
            if status != ConsensusStatus.REACHED:
                status = ConsensusStatus.BYZANTINE_DETECTED

        result = ConsensusResult(
            status=status,
            proposal_id=proposal_id,
            winning_vote=winning_vote,
            approve_weight=approve_weight,
            reject_weight=reject_weight,
            abstain_weight=abstain_weight,
            total_weight=total_weight,
            participation_rate=participation_rate,
            byzantine_nodes_detected=byzantine_nodes,
            confidence=confidence,
        )

        self._consensus_history.append(result)
        return result

    def _detect_byzantine_behavior(self, proposal_id: str, votes: list[Vote]) -> list[str]:
        """
        Detect Byzantine behavior using weighted consensus.

        Uses weighted voting to resist majority tyranny:
        - Computes weighted majority (not raw count)
        - Only flags nodes when consensus strength > 2/3
        - Considers trust score before flagging as Byzantine
        """
        byzantine_nodes: list[str] = []

        # Weighted vote aggregation
        total_approve_weight = 0.0
        total_reject_weight = 0.0

        for v in votes:
            validator = self._validators.get(v.validator_id)
            weight = validator.weight if validator else 1.0
            if v.vote_value == VoteValue.APPROVE:
                total_approve_weight += weight
            elif v.vote_value == VoteValue.REJECT:
                total_reject_weight += weight

        total_weight = total_approve_weight + total_reject_weight
        if total_weight == 0:
            return []

        # Weighted majority with strength check
        majority_approves = total_approve_weight > total_reject_weight
        majority_weight = max(total_approve_weight, total_reject_weight)
        consensus_strength = majority_weight / total_weight

        # Only flag if consensus is strong (>2/3 threshold)
        if consensus_strength <= 2 / 3:
            return []

        for vote in votes:
            validator = self._validators.get(vote.validator_id)
            if not validator:
                continue

            if vote.vote_value == VoteValue.ABSTAIN:
                continue

            dissents = (vote.vote_value == VoteValue.APPROVE and not majority_approves) or (
                vote.vote_value == VoteValue.REJECT and majority_approves
            )
            if not dissents:
                continue

            # Only flag as Byzantine if trust score is critically low
            # AND multiple penalizations in recent history
            penalization_count = sum(
                1 for h in validator.reputation_history[-10:] if h.get("action") == "penalize"
            )

            if validator.trust_score < 0.3 and penalization_count >= 3:
                byzantine_nodes.append(vote.validator_id)
                validator.is_byzantine = True

        return byzantine_nodes

    def update_weights_after_consensus(self, proposal_id: str) -> None:
        """
        共识达成后更新权重

        对支持多数共识的节点奖励，对反对的节点惩罚。
        """
        result = self.evaluate_consensus(proposal_id)

        if result.status not in (ConsensusStatus.REACHED, ConsensusStatus.INCONCLUSIVE):
            return

        votes = self._votes.get(proposal_id, [])
        winning_vote = result.winning_vote

        if not winning_vote:
            return

        for vote in votes:
            validator = self._validators.get(vote.validator_id)
            if not validator:
                continue

            if vote.vote_value == winning_vote:
                validator.reward(factor=1.05)
            elif vote.vote_value != VoteValue.ABSTAIN:
                validator.penalize(factor=0.95)

    def get_validator_stats(self, node_id: str) -> dict[str, Any] | None:
        """获取验证者统计信息"""
        validator = self._validators.get(node_id)
        if not validator:
            return None

        # 计算参与率
        total_proposals = len(self._proposals)
        participated = sum(
            1 for votes in self._votes.values() if any(v.validator_id == node_id for v in votes)
        )

        return {
            "node_id": node_id,
            "current_weight": round(validator.weight, 3),
            "initial_weight": round(validator.initial_weight, 3),
            "trust_score": round(validator.trust_score, 3),
            "is_byzantine": validator.is_byzantine,
            "is_active": validator.is_active,
            "participation_rate": round(participated / total_proposals, 3)
            if total_proposals > 0
            else 0.0,
            "reputation_events": len(validator.reputation_history),
        }

    def get_network_stats(self) -> dict[str, Any]:
        """获取网络统计信息"""
        active_validators = [v for v in self._validators.values() if v.is_active]
        byzantine_count = sum(1 for v in self._validators.values() if v.is_byzantine)

        total_weight = sum(v.weight for v in active_validators)
        avg_trust = (
            sum(v.trust_score for v in active_validators) / len(active_validators)
            if active_validators
            else 0.0
        )

        return {
            "total_validators": len(self._validators),
            "active_validators": len(active_validators),
            "byzantine_nodes": byzantine_count,
            "total_weight": round(total_weight, 3),
            "average_trust": round(avg_trust, 3),
            "total_proposals": len(self._proposals),
            "consensus_reached": sum(
                1 for r in self._consensus_history if r.status == ConsensusStatus.REACHED
            ),
        }


class CrossValidator:
    """
    交叉验证器

    整合语义等价性检测和加权共识，实现多 Agent 输出的交叉验证。
    """

    def __init__(self):
        self.consensus = WeightedConsensusEngine()
        from maref.cross_validator.ast_normalizer import SemanticEquivalenceChecker

        self.equivalence = SemanticEquivalenceChecker()

    def validate_agent_outputs(
        self,
        proposal_id: str,
        outputs: dict[str, str],  # agent_id -> output
        reference_output: str | None = None,
        similarity_threshold: float = 0.8,
    ) -> dict[str, Any]:
        """
        验证多个 Agent 的输出

        Args:
            proposal_id: 提案 ID
            outputs: Agent 输出字典
            reference_output: 参考输出（如果有）
            similarity_threshold: 相似度阈值

        Returns:
            验证结果
        """
        # 创建提案
        self.consensus.create_proposal(
            proposal_id=proposal_id,
            content={"agent_count": len(outputs), "has_reference": reference_output is not None},
            proposer_id="cross_validator",
        )

        # 如果没有参考输出，进行两两比较
        comparison_base = reference_output or next(iter(outputs.values()))

        # 对每个 Agent 的输出进行验证
        approvals = []
        rejections = []

        for agent_id, output in outputs.items():
            # 检查是否已注册为验证者，如果没有则自动注册
            if not self.consensus.has_validator(agent_id):
                self.consensus.register_validator(agent_id)

            # 语义等价性检查
            equiv_result = self.equivalence.check_equivalence(
                comparison_base, output, threshold=similarity_threshold
            )

            if equiv_result["equivalent"]:
                approvals.append(agent_id)
                self.consensus.cast_vote(
                    proposal_id=proposal_id,
                    validator_id=agent_id,
                    vote_value=VoteValue.APPROVE,
                    justification=f"Semantic similarity: {equiv_result['similarity']}",
                )
            else:
                rejections.append(agent_id)
                self.consensus.cast_vote(
                    proposal_id=proposal_id,
                    validator_id=agent_id,
                    vote_value=VoteValue.REJECT,
                    justification=f"Semantic similarity: {equiv_result['similarity']}",
                )

        # 评估共识
        consensus_result = self.consensus.evaluate_consensus(proposal_id)

        return {
            "proposal_id": proposal_id,
            "consensus": consensus_result.to_dict(),
            "approvals": approvals,
            "rejections": rejections,
            "total_agents": len(outputs),
        }


def create_consensus_engine() -> WeightedConsensusEngine:
    """创建共识引擎"""
    return WeightedConsensusEngine()


def create_cross_validator() -> CrossValidator:
    """创建交叉验证器"""
    return CrossValidator()


__all__ = [
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
