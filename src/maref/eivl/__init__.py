"""
EIVL (External Immutable Verification Layer) 模块

提供基于 WASM 的隔离执行环境和 Merkle 审计链。
"""

from maref.eivl.wasm_sandbox import (
    EIVLVerifier,
    ExecutionResult,
    ExecutionStatus,
    ResourceLimits,
    SandboxCapabilities,
    SandboxError,
    MemoryLimitExceeded,
    ExecutionTimeout,
    CapabilityViolation,
    WasmSandboxExecutor,
    create_eivl_verifier,
    create_wasm_sandbox,
)
from maref.eivl.merkle_auditor import (
    AuditChainIntegrator,
    AuditEvidence,
    MerkleAuditor,
    MerkleNode,
    MerkleProof,
    create_audit_chain_integrator,
    create_merkle_auditor,
)

__all__ = [
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
    "MerkleAuditor",
    "AuditEvidence",
    "MerkleNode",
    "MerkleProof",
    "AuditChainIntegrator",
    "create_merkle_auditor",
    "create_audit_chain_integrator",
]