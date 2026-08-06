"""
EIVL (External Immutable Verification Layer) 模块

提供基于 WASM 的隔离执行环境、Merkle 审计链、跨组织根聚合与
跨实例审计日志。
"""
from __future__ import annotations

from maref.eivl.audit_reconciler import (
    AuditReconciler,
    MerkleSnapshot,
    ReconciliationReport,
)
from maref.eivl.federated_audit_log import (
    AuditEventType,
    FederatedAuditEntry,
    FederatedAuditLog,
)
from maref.eivl.federated_merkle import (
    FederatedMerkleAggregator,
    FederatedProof,
    OrgRootEntry,
)
from maref.eivl.federated_store import FederatedAuditStore
from maref.eivl.merkle_auditor import (
    AuditChainIntegrator,
    AuditEvidence,
    MerkleAuditor,
    MerkleNode,
    MerkleProof,
    create_audit_chain_integrator,
    create_merkle_auditor,
)
from maref.eivl.wasm_sandbox import (
    CapabilityViolation,
    EIVLVerifier,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTimeout,
    MemoryLimitExceeded,
    ResourceLimits,
    SandboxCapabilities,
    SandboxError,
    WasmSandboxExecutor,
    create_eivl_verifier,
    create_wasm_sandbox,
)

__all__ = [
    # WASM sandbox
    "WasmSandboxExecutor",
    "EIVLVerifier",
    "ExecutionResult",
    "ExecutionStatus",
    "ResourceLimits",
    "SandboxCapabilities",
    "SandboxError",
    "MemoryLimitExceeded",
    "ExecutionTimeout",
    "CapabilityViolation",
    "create_wasm_sandbox",
    "create_eivl_verifier",
    # Merkle audit chain
    "MerkleAuditor",
    "AuditEvidence",
    "MerkleNode",
    "MerkleProof",
    "AuditChainIntegrator",
    "create_merkle_auditor",
    "create_audit_chain_integrator",
    # Federated Merkle aggregation
    "FederatedMerkleAggregator",
    "FederatedProof",
    "OrgRootEntry",
    "FederatedAuditStore",
    # Audit reconciliation
    "AuditReconciler",
    "ReconciliationReport",
    "MerkleSnapshot",
    # Federated audit log
    "FederatedAuditLog",
    "FederatedAuditEntry",
    "AuditEventType",
]
