"""
供应链安全管理模块

提供软件物料清单(SBOM)生成和漏洞扫描功能。
"""

from maref.supply_chain.sbom_generator import (
    SBOM,
    Component,
    ComponentType,
    LicenseType,
    SBOMGenerator,
    Vulnerability,
    VulnerabilitySeverity,
)
from maref.supply_chain.trust_verifier import (
    SupplyChainTrustReport,
    SupplyChainVerifier,
    register_supply_chain_verifier,
)
from maref.supply_chain.vulnerability_scanner import (
    ScanResult,
    ScanStatus,
    VulnerabilityDatabase,
    VulnerabilityMatch,
    VulnerabilityScanner,
    VulnerabilitySource,
)

__all__ = [
    # SBOM生成器
    "SBOMGenerator",
    "SBOM",
    "Component",
    "ComponentType",
    "LicenseType",
    "Vulnerability",
    "VulnerabilitySeverity",
    # 漏洞扫描器
    "VulnerabilityScanner",
    "ScanResult",
    "ScanStatus",
    "VulnerabilitySource",
    "VulnerabilityMatch",
    "VulnerabilityDatabase",
    # 供应链信任验证器
    "SupplyChainVerifier",
    "SupplyChainTrustReport",
    "register_supply_chain_verifier",
]
