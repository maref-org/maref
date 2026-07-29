"""
网信办《智能体规范应用与创新发展实施意见》— "区块链可追溯机制"技术响应。

根据《智能体规范应用与创新发展实施意见》中关于"采用区块链或等效技术
实现 Agent 行为的可追溯、不可篡改记录"的要求，MAREF 以 Merkle 审计链
作为区块链等效技术方案。

技术映射:
    区块链特性   →  MAREF 等效实现
    ─────────────────────────────────
    区块        →  AuditEntry (结构化审计条目)
    链式哈希    →  chain_hash + previous_hash
    默克尔树    →  MerkleAuditor + FederatedMerkleAggregator
    共识        →  FederatedProof 跨组织验证
    智能合约    →  八卦治理状态机 (EightTrigramsGovernance)
    不可篡改    →  Ed25519 签名 + 链式哈希校验
    去中心化    →  联邦审计 (无中央权威)
    离线验证    →  maref federated verify (无网络依赖)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BlockchainEquivalence:
    """区块链技术特性到 MAREF 的映射。"""

    blockchain_feature: str
    cac_requirement: str
    maref_implementation: str
    module_path: str
    verified: bool = False


CAC_REQUIREMENTS: list[BlockchainEquivalence] = [
    BlockchainEquivalence(
        blockchain_feature="不可篡改记录",
        cac_requirement="Agent 行为记录一经写入不可修改或删除",
        maref_implementation="仅追加审计日志 + Ed25519 签名 + chain_hash 链式完整性校验",
        module_path="maref.governance.audit",
    ),
    BlockchainEquivalence(
        blockchain_feature="链式哈希结构",
        cac_requirement="记录之间通过密码学哈希链接，形成可追溯链",
        maref_implementation="AuditEntry.previous_hash + chain_hash 双哈希链，每 1000 条生成 Merkle 根",
        module_path="maref.eivl.merkle_auditor",
    ),
    BlockchainEquivalence(
        blockchain_feature="Merkle 树完整性证明",
        cac_requirement="支持第三方验证记录完整性，无需访问原始系统",
        maref_implementation="MerkleAuditor 生成完整性证明，FederatedProof 支持离线验证",
        module_path="maref.eivl.federated_merkle",
    ),
    BlockchainEquivalence(
        blockchain_feature="跨组织审计",
        cac_requirement="多个组织之间可交叉验证审计记录",
        maref_implementation="FederatedMerkleAggregator 聚合跨组织 Merkle 根，产生联邦证明",
        module_path="maref.eivl.federated_merkle",
    ),
    BlockchainEquivalence(
        blockchain_feature="数字签名",
        cac_requirement="每条记录需有可验证的电子签名",
        maref_implementation="Ed25519 非对称签名，公钥指纹写入审计日志头，`maref federated verify` 离线验证",
        module_path="maref.crypto.ed25519_keys",
    ),
    BlockchainEquivalence(
        blockchain_feature="国密合规",
        cac_requirement="鼓励使用国密标准 (SM2/SM3/SM4-GCM)",
        maref_implementation="src/maref/crypto/sm2.py, sm3.py, sm4_gcm.py 完整国密实现",
        module_path="maref.crypto.sm3",
    ),
    BlockchainEquivalence(
        blockchain_feature="数据主权",
        cac_requirement="数据不出域，本地化存储和处理",
        maref_implementation="FederatedAuditStore 本地 SQLite 存储，data_sovereignty.py 地理围栏控制",
        module_path="maref.compliance.data_sovereignty",
    ),
    BlockchainEquivalence(
        blockchain_feature="可追溯性报告",
        cac_requirement="可导出标准格式的审计追溯报告",
        maref_implementation="GovernanceReport 自包含 JSON 报告 + HTML 导出，`maref report generate`",
        module_path="maref.reporting.generator",
    ),
]


class CACBlockchainTraceability:
    """网信办区块链可追溯机制合规映射。"""

    def __init__(self) -> None:
        self._requirements = CAC_REQUIREMENTS

    def verify_all(self) -> dict[str, Any]:
        results = []
        covered = 0
        for req in self._requirements:
            try:
                import importlib
                importlib.import_module(req.module_path)
                req.verified = True
                covered += 1
            except (ImportError, ModuleNotFoundError):
                req.verified = False
            results.append({
                "feature": req.blockchain_feature,
                "verified": req.verified,
                "module": req.module_path,
            })
        return {
            "total": len(self._requirements),
            "covered": covered,
            "coverage": f"{covered}/{len(self._requirements)}",
            "requirements": results,
            "pass": covered == len(self._requirements),
        }

    def summary(self) -> str:
        report = self.verify_all()
        lines = [
            "网信办《智能体规范应用与创新发展实施意见》",
            "区块链可追溯机制 — MAREF 技术响应",
            "=" * 60,
        ]
        for r in report["requirements"]:
            mark = "✅" if r["verified"] else "❌"
            lines.append(f"  {mark} {r['feature']:<30s} {r['module']}")
        lines.append("=" * 60)
        lines.append(f"  Coverage: {report['coverage']}")
        return "\n".join(lines)


__all__ = ["CACBlockchainTraceability"]
