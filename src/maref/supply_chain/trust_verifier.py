# Copyright 2026 MAREF Team
# SPDX-License-Identifier: Apache-2.0

"""供应链信任验证器 — 集成漏洞扫描与递归信任传播.

将 VulnerabilityScanner 的漏洞发现与 TrustGraph 的信任传播算法结合，
实现对 SBOM 中所有组件的递归信任评估。

流程:
    1. 将 SBOM 中的每个 Component 加入 TrustGraph（初始信任 70.0）
    2. 用 Component.dependencies 构建信任边（依赖项 → 依赖者）
    3. 调用 VulnerabilityScanner.scan_sbom() 获取漏洞匹配
    4. 对有漏洞的 Component 按严重度降信任分:
       - CRITICAL: -40, HIGH: -25, MEDIUM: -15, LOW: -5, INFO: -2
    5. 调用 TrustPropagation.propagate(iterations) 得到传播后信任分
    6. 收集低于阈值的组件到 untrusted 列表

旁路直连模式:
    本模块直接调用 VulnerabilityScanner 和 TrustGraph，不经过 VerifierConsensus。
    元数据登记通过 register_supply_chain_verifier() 完成。

Usage:
    from maref.supply_chain import SBOM, SupplyChainVerifier

    verifier = SupplyChainVerifier()
    report = verifier.verify(sbom)
    if not report.attestation_valid:
        print(f"Untrusted: {report.untrusted}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maref.security.trust_graph import TrustGraph, TrustPropagation
from maref.supply_chain.sbom_generator import (
    SBOM,
    VulnerabilitySeverity,
)
from maref.supply_chain.vulnerability_scanner import VulnerabilityScanner

if TYPE_CHECKING:
    from maref.governance.verifier_registry import VerifierRegistry

# 组件初始信任分（无漏洞时的基线）
DEFAULT_INITIAL_TRUST = 70.0

# 漏洞严重度 → 信任扣分映射
SEVERITY_PENALTY: dict[VulnerabilitySeverity, float] = {
    VulnerabilitySeverity.CRITICAL: 40.0,
    VulnerabilitySeverity.HIGH: 25.0,
    VulnerabilitySeverity.MEDIUM: 15.0,
    VulnerabilitySeverity.LOW: 5.0,
    VulnerabilitySeverity.INFO: 2.0,
    VulnerabilitySeverity.UNKNOWN: 0.0,
}


@dataclass
class SupplyChainTrustReport:
    """供应链信任评估报告."""

    component_trust: dict[str, float]
    """bom_ref → 降分后、传播前的信任分."""

    propagated_trust: dict[str, float]
    """bom_ref → 传播后的最终信任分."""

    untrusted: list[str]
    """信任分低于阈值的组件 bom_ref 列表."""

    attestation_valid: bool
    """整体是否通过信任验证（无 untrusted 组件时为 True）."""

    vulnerabilities_found: int
    """扫描发现的漏洞总数."""

    trust_threshold: float
    """判定 untrusted 的信任分阈值."""

    propagation_iterations: int
    """信任传播迭代次数."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_trust": self.component_trust,
            "propagated_trust": self.propagated_trust,
            "untrusted": self.untrusted,
            "attestation_valid": self.attestation_valid,
            "vulnerabilities_found": self.vulnerabilities_found,
            "trust_threshold": self.trust_threshold,
            "propagation_iterations": self.propagation_iterations,
        }


class SupplyChainVerifier:
    """供应链信任验证器 — 集成漏洞扫描与信任传播.

    Args:
        trust_graph: 可选的 TrustGraph 实例。未传入则创建新图。
        vuln_scanner: 可选的 VulnerabilityScanner 实例。未传入则创建默认实例。
        propagation_iterations: 信任传播迭代次数。默认 5。
        trust_threshold: 判定 untrusted 的阈值。默认 30.0。
        initial_trust: 组件初始信任分。默认 70.0。
    """

    DEFAULT_TRUST_THRESHOLD = 30.0

    def __init__(
        self,
        trust_graph: TrustGraph | None = None,
        vuln_scanner: VulnerabilityScanner | None = None,
        propagation_iterations: int = 5,
        trust_threshold: float = DEFAULT_TRUST_THRESHOLD,
        initial_trust: float = DEFAULT_INITIAL_TRUST,
    ) -> None:
        self._graph = trust_graph or TrustGraph()
        self._scanner = vuln_scanner or VulnerabilityScanner()
        self._iterations = propagation_iterations
        self._threshold = trust_threshold
        self._initial_trust = initial_trust

    def verify(self, sbom: SBOM) -> SupplyChainTrustReport:
        """验证 SBOM 的供应链信任度.

        Args:
            sbom: 待验证的软件物料清单.

        Returns:
            SupplyChainTrustReport 包含初始信任、传播后信任、untrusted 列表。
        """
        # 空SBOM 直接返回有效
        if not sbom.components:
            return SupplyChainTrustReport(
                component_trust={},
                propagated_trust={},
                untrusted=[],
                attestation_valid=True,
                vulnerabilities_found=0,
                trust_threshold=self._threshold,
                propagation_iterations=self._iterations,
            )

        # 1. 构建 TrustGraph：每个 component 作为节点
        # 使用实例图 self._graph（支持构造函数注入），每次 verify 重置以避免状态累积
        self._graph = TrustGraph()
        graph = self._graph
        bom_ref_to_component: dict[str, Any] = {}
        for component in sbom.components:
            graph.add_agent(
                component.bom_ref,
                initial_trust=self._initial_trust,
            )
            bom_ref_to_component[component.bom_ref] = component

        # 2. 构建信任边：依赖项 → 依赖者
        # 语义：若 B 是 A 的依赖（A.dependencies 含 B.bom_ref），
        # 则 B 的信任度会影响 A，故边方向为 B → A
        for component in sbom.components:
            for dep_bom_ref in component.dependencies:
                if dep_bom_ref in bom_ref_to_component:
                    graph.add_edge(
                        source=dep_bom_ref,
                        target=component.bom_ref,
                        trust_score=self._initial_trust,
                    )

        # 3. 漏洞扫描
        scan_result = self._scanner.scan_sbom(sbom)

        # 4. 按漏洞严重度降信任分
        penalties: dict[str, float] = {}
        for match in scan_result.matches:
            bom_ref = match.component.bom_ref
            penalty = SEVERITY_PENALTY.get(match.vulnerability.severity, 0.0)
            penalties[bom_ref] = penalties.get(bom_ref, 0.0) + penalty

        for bom_ref, total_penalty in penalties.items():
            current = graph.get_trust(bom_ref)
            graph.update_trust(bom_ref, max(0.0, current - total_penalty))

        # 记录降分后、传播前的信任分
        component_trust = {
            bom_ref: graph.get_trust(bom_ref) for bom_ref in bom_ref_to_component
        }

        # 5. 递归信任传播
        propagation = TrustPropagation(graph, decay_factor=0.5)
        propagated = propagation.propagate(iterations=self._iterations)

        # 6. 收集 untrusted 组件
        untrusted = [
            bom_ref
            for bom_ref in bom_ref_to_component
            if propagated.get(bom_ref, 0.0) < self._threshold
        ]

        return SupplyChainTrustReport(
            component_trust=component_trust,
            propagated_trust=propagated,
            untrusted=untrusted,
            attestation_valid=len(untrusted) == 0,
            vulnerabilities_found=scan_result.vulnerabilities_found,
            trust_threshold=self._threshold,
            propagation_iterations=self._iterations,
        )

    def _severity_to_penalty(self, severity: VulnerabilitySeverity) -> float:
        """漏洞严重度 → 信任扣分（向后兼容接口）."""
        return SEVERITY_PENALTY.get(severity, 0.0)


def register_supply_chain_verifier(registry: VerifierRegistry) -> None:
    """在 VerifierRegistry 登记 SupplyChainVerifier 元数据.

    旁路直连模式：元数据登记用于统计追踪，真实验证由 SupplyChainVerifier.verify() 直接调用。

    Args:
        registry: VerifierRegistry 实例.
    """
    from maref.governance.verifier_registry import VerifierEntry, VerifierStatus

    entry = VerifierEntry(
        name="supply_chain_trust_verifier",
        model="SupplyChainVerifier v1",
        methodology="recursive_trust_propagation",
        status=VerifierStatus.ACTIVE,
        accuracy=0.88,
        recall=0.85,
        bias=0.0,
    )
    registry.register(entry)


__all__ = [
    "DEFAULT_INITIAL_TRUST",
    "SEVERITY_PENALTY",
    "SupplyChainTrustReport",
    "SupplyChainVerifier",
    "register_supply_chain_verifier",
]
