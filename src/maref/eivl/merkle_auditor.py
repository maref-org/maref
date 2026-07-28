"""
Merkle 审计链

基于 Merkle Tree 的不可篡改审计证据链，为 MAREF 安全体系提供可验证的日志存储。

核心特性:
1. 增量式 Merkle Tree 构建
2. 审计证据的不可篡改验证
3. 与现有 UnifiedAuditStore 集成
4. 支持批量证据提交和验证
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class MerkleNode:
    """Merkle Tree 节点"""
    hash: str
    left: MerkleNode | None = None
    right: MerkleNode | None = None
    data: str | None = None
    index: int = 0

    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def to_dict(self) -> dict[str, Any]:
        result = {'hash': self.hash, 'is_leaf': self.is_leaf()}
        if self.is_leaf():
            result['data'] = self.data
            result['index'] = self.index
        else:
            result['left'] = self.left.to_dict() if self.left else None
            result['right'] = self.right.to_dict() if self.right else None
        return result

@dataclass
class AuditEvidence:
    """审计证据"""
    evidence_id: str
    timestamp: float
    evidence_type: str
    source_agent: str
    target_agent: str | None
    action: str
    result: dict[str, Any]
    previous_hash: str
    nonce: int

    def compute_hash(self) -> str:
        """计算证据的哈希值"""
        data = {'evidence_id': self.evidence_id, 'timestamp': self.timestamp, 'evidence_type': self.evidence_type, 'source_agent': self.source_agent, 'target_agent': self.target_agent, 'action': self.action, 'result': self.result, 'previous_hash': self.previous_hash, 'nonce': self.nonce}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_audit_entry(
        cls,
        entry: Any,
        chain_previous_hash: str = '0' * 64,
        nonce: int = 0,
    ) -> AuditEvidence:
        """Create AuditEvidence from an AuditLogger AuditEntry.

        Bridges the AuditLogger (governance) and MerkleAuditor (EIVL) subsystems.
        The evidence_id, timestamps, actor/agent info are mapped from the entry.
        """
        return cls(
            evidence_id=entry.id,
            timestamp=entry.timestamp,
            evidence_type=entry.event_type,
            source_agent=entry.actor,
            target_agent=entry.metadata.get("target_agent"),
            action=entry.action,
            result={
                "details": entry.details,
                "metadata": entry.metadata,
                "chain_hash": entry.chain_hash,
                "signature_type": entry.signature_type,
            },
            previous_hash=chain_previous_hash,
            nonce=nonce,
        )

@dataclass
class MerkleProof:
    """Merkle 证明 - 用于验证某个证据是否包含在树中"""
    target_hash: str
    proof_path: list[tuple[str, str]]
    root_hash: str
    tree_size: int

    def verify(self) -> bool:
        """验证证明是否有效"""
        current_hash = self.target_hash
        for (sibling_hash, direction) in self.proof_path:
            if direction == 'left':
                current_hash = MerkleAuditor._hash_pair(sibling_hash, current_hash)
            else:
                current_hash = MerkleAuditor._hash_pair(current_hash, sibling_hash)
        return current_hash == self.root_hash

    def to_dict(self) -> dict[str, Any]:
        return {'target_hash': self.target_hash, 'proof_path': self.proof_path, 'root_hash': self.root_hash, 'tree_size': self.tree_size}

class MerkleAuditor:
    """
    Merkle 审计器

    管理基于 Merkle Tree 的审计证据链，提供不可篡改的日志验证。
    """

    def __init__(self):
        self._leaves: list[MerkleNode] = []
        self._root: MerkleNode | None = None
        self._evidence_map: dict[str, AuditEvidence] = {}
        self._hash_to_evidence: dict[str, str] = {}
        self._tree_version = 0
        self._last_rebuild = 0

    @staticmethod
    def _hash_pair(left: str, right: str) -> str:
        """对两个哈希值进行配对哈希"""
        combined = left + right
        return hashlib.sha256(combined.encode()).hexdigest()

    @staticmethod
    def _hash_data(data: str) -> str:
        """对数据进行哈希"""
        return hashlib.sha256(data.encode()).hexdigest()

    def add_evidence(self, evidence: AuditEvidence) -> str:
        """
        添加审计证据到 Merkle Tree

        Args:
            evidence: 审计证据

        Returns:
            str: 证据的哈希值
        """
        evidence_hash = evidence.compute_hash()
        leaf = MerkleNode(hash=evidence_hash, data=evidence_hash, index=len(self._leaves))
        self._leaves.append(leaf)
        self._evidence_map[evidence.evidence_id] = evidence
        self._hash_to_evidence[evidence_hash] = evidence.evidence_id
        self._rebuild_tree()
        return evidence_hash

    def add_evidence_batch(self, evidences: list[AuditEvidence]) -> list[str]:
        """
        批量添加审计证据

        Args:
            evidences: 审计证据列表

        Returns:
            list[str]: 证据哈希列表
        """
        hashes = []
        for evidence in evidences:
            evidence_hash = evidence.compute_hash()
            leaf = MerkleNode(hash=evidence_hash, data=evidence_hash, index=len(self._leaves))
            self._leaves.append(leaf)
            self._evidence_map[evidence.evidence_id] = evidence
            self._hash_to_evidence[evidence_hash] = evidence.evidence_id
            hashes.append(evidence_hash)
        self._rebuild_tree()
        return hashes

    def _rebuild_tree(self) -> None:
        """重建 Merkle Tree"""
        if not self._leaves:
            self._root = None
            return
        current_level = self._leaves.copy()
        while len(current_level) > 1:
            next_level: list[MerkleNode] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                parent = MerkleNode(hash=self._hash_pair(left.hash, right.hash), left=left, right=right)
                next_level.append(parent)
            current_level = next_level
        self._root = current_level[0]
        self._tree_version += 1
        self._last_rebuild = int(time.time())

    def get_root_hash(self) -> str | None:
        """获取 Merkle Root 哈希"""
        return self._root.hash if self._root else None

    def get_evidence(self, evidence_id: str) -> AuditEvidence | None:
        """根据 ID 获取证据"""
        return self._evidence_map.get(evidence_id)

    def get_evidence_by_hash(self, evidence_hash: str) -> AuditEvidence | None:
        """根据哈希获取证据"""
        evidence_id = self._hash_to_evidence.get(evidence_hash)
        if evidence_id:
            return self._evidence_map.get(evidence_id)
        return None

    def generate_proof(self, evidence_hash: str) -> MerkleProof | None:
        """
        为指定证据生成 Merkle 证明

        Args:
            evidence_hash: 证据哈希

        Returns:
            MerkleProof: 证明对象，如果证据不存在则返回 None
        """
        if evidence_hash not in self._hash_to_evidence:
            return None
        if not self._root:
            return None
        leaf_index = None
        for (i, leaf) in enumerate(self._leaves):
            if leaf.hash == evidence_hash:
                leaf_index = i
                break
        if leaf_index is None:
            return None
        proof_path: list[tuple[str, str]] = []
        current_index = leaf_index
        current_level = self._leaves.copy()
        while len(current_level) > 1:
            next_level: list[MerkleNode] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else current_level[i]
                if current_index == i:
                    proof_path.append((right.hash, 'right'))
                    current_index = len(next_level)
                elif current_index == i + 1 or (current_index == i and i == len(current_level) - 1):
                    proof_path.append((left.hash, 'left'))
                    current_index = len(next_level)
                parent = MerkleNode(hash=self._hash_pair(left.hash, right.hash), left=left, right=right)
                next_level.append(parent)
            current_level = next_level
        return MerkleProof(target_hash=evidence_hash, proof_path=proof_path, root_hash=self._root.hash, tree_size=len(self._leaves))

    def verify_evidence_integrity(self, evidence_id: str) -> dict[str, Any]:
        """
        验证证据的完整性

        Args:
            evidence_id: 证据 ID

        Returns:
            验证结果字典
        """
        evidence = self._evidence_map.get(evidence_id)
        if not evidence:
            return {'valid': False, 'reason': 'Evidence not found', 'evidence_id': evidence_id}
        computed_hash = evidence.compute_hash()
        proof = self.generate_proof(computed_hash)
        if not proof:
            return {'valid': False, 'reason': 'Could not generate Merkle proof', 'evidence_id': evidence_id, 'computed_hash': computed_hash}
        proof_valid = proof.verify()
        return {'valid': proof_valid, 'evidence_id': evidence_id, 'computed_hash': computed_hash, 'root_hash': proof.root_hash, 'tree_size': proof.tree_size, 'proof_path_length': len(proof.proof_path)}

    def get_tree_info(self) -> dict[str, Any]:
        """获取树的信息"""
        return {'leaf_count': len(self._leaves), 'root_hash': self.get_root_hash(), 'tree_version': self._tree_version, 'last_rebuild': self._last_rebuild, 'evidence_count': len(self._evidence_map)}

    def export_tree(self) -> dict[str, Any]:
        """导出完整的树结构（用于备份或传输）"""
        return {'root_hash': self.get_root_hash(), 'leaves': [{'hash': leaf.hash, 'index': leaf.index, 'evidence_id': self._hash_to_evidence.get(leaf.hash)} for leaf in self._leaves], 'tree_version': self._tree_version, 'metadata': {'export_time': time.time(), 'leaf_count': len(self._leaves)}}

    def compare_trees(self, other: MerkleAuditor) -> dict[str, Any]:
        """
        比较两个 Merkle Tree

        用于分布式审计节点之间的一致性检查。
        """
        self_root = self.get_root_hash()
        other_root = other.get_root_hash()
        if self_root == other_root:
            return {'consistent': True, 'root_match': True, 'self_leaves': len(self._leaves), 'other_leaves': len(other._leaves)}
        self_hashes = {leaf.hash for leaf in self._leaves}
        other_hashes = {leaf.hash for leaf in other._leaves}
        only_in_self = self_hashes - other_hashes
        only_in_other = other_hashes - self_hashes
        return {'consistent': False, 'root_match': False, 'self_root': self_root, 'other_root': other_root, 'self_leaves': len(self._leaves), 'other_leaves': len(other._leaves), 'differences': {'only_in_self_count': len(only_in_self), 'only_in_other_count': len(only_in_other), 'common_count': len(self_hashes & other_hashes)}}

class AuditChainIntegrator:
    """
    审计链集成器

    将 Merkle 审计链与现有的 UnifiedAuditStore 集成。
    """

    def __init__(self, merkle_auditor: MerkleAuditor | None=None):
        self.merkle = merkle_auditor or MerkleAuditor()
        self._previous_hash = '0' * 64

    def record_trust_evaluation(self, agent_id: str, trust_score: float, chain_risks: list[dict[str, Any]], evaluator: str='system') -> str:
        """记录信任评估到审计链"""
        evidence = AuditEvidence(evidence_id=f'trust-{agent_id}-{int(time.time() * 1000)}', timestamp=time.time(), evidence_type='trust_evaluation', source_agent=evaluator, target_agent=agent_id, action='evaluate_trust', result={'trust_score': trust_score, 'chain_risks': chain_risks}, previous_hash=self._previous_hash, nonce=0)
        evidence_hash = self.merkle.add_evidence(evidence)
        self._previous_hash = evidence_hash
        return evidence_hash

    def record_access_control(self, agent_id: str, action: str, resource: str, allowed: bool, context: dict[str, Any] | None=None) -> str:
        """记录访问控制决策到审计链"""
        evidence = AuditEvidence(evidence_id=f'access-{agent_id}-{int(time.time() * 1000)}', timestamp=time.time(), evidence_type='access_control', source_agent=agent_id, target_agent=None, action=action, result={'resource': resource, 'allowed': allowed, 'context': context or {}}, previous_hash=self._previous_hash, nonce=0)
        evidence_hash = self.merkle.add_evidence(evidence)
        self._previous_hash = evidence_hash
        return evidence_hash

    def record_delegation(self, delegator_id: str, delegatee_id: str, capabilities: list[str], chain_id: str | None=None) -> str:
        """记录委托行为到审计链"""
        evidence = AuditEvidence(evidence_id=f'delegate-{delegator_id}-{int(time.time() * 1000)}', timestamp=time.time(), evidence_type='delegation', source_agent=delegator_id, target_agent=delegatee_id, action='delegate_capabilities', result={'capabilities': capabilities, 'chain_id': chain_id}, previous_hash=self._previous_hash, nonce=0)
        evidence_hash = self.merkle.add_evidence(evidence)
        self._previous_hash = evidence_hash
        return evidence_hash

    def record_audit_entry(self, entry: Any) -> str:
        """Record an AuditLogger entry into the Merkle audit chain.

        Converts the AuditEntry to AuditEvidence and adds it to the Merkle tree.
        Returns the Merkle leaf hash for proof generation.

        Args:
            entry: An AuditEntry from AuditLogger.

        Returns:
            str: Merkle leaf hash of the recorded evidence.
        """
        evidence = AuditEvidence.from_audit_entry(
            entry,
            chain_previous_hash=self._previous_hash,
        )
        evidence_hash = self.merkle.add_evidence(evidence)
        self._previous_hash = evidence_hash
        return evidence_hash

    def get_audit_summary(self) -> dict[str, Any]:
        """获取审计摘要"""
        return {'tree_info': self.merkle.get_tree_info(), 'latest_hash': self._previous_hash}

def create_merkle_auditor() -> MerkleAuditor:
    """创建 Merkle 审计器"""
    return MerkleAuditor()

def create_audit_chain_integrator() -> AuditChainIntegrator:
    """创建审计链集成器"""
    return AuditChainIntegrator()
__all__ = ['MerkleAuditor', 'AuditEvidence', 'MerkleNode', 'MerkleProof', 'AuditChainIntegrator', 'create_merkle_auditor', 'create_audit_chain_integrator']
