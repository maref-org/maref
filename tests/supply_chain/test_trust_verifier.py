"""Tests for SupplyChainVerifier — recursive trust propagation.

Covers:
- Clean SBOM (no vulnerabilities) → high trust, attestation valid
- CRITICAL vulnerability lowers trust by 40
- Untrusted components appear in untrusted list
- Dependencies propagate trust (parent vulnerability affects dependent)
- Attestation invalid when untrusted components exist
- Empty SBOM returns valid attestation
- Report to_dict() contains all fields
- VerifierEntry metadata registration
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from maref.supply_chain.sbom_generator import (
    Component,
    ComponentType,
    SBOM,
    Vulnerability,
    VulnerabilitySeverity,
)
from maref.supply_chain.trust_verifier import (
    SEVERITY_PENALTY,
    SupplyChainTrustReport,
    SupplyChainVerifier,
    register_supply_chain_verifier,
)
from maref.supply_chain.vulnerability_scanner import (
    ScanResult,
    ScanStatus,
    VulnerabilityMatch,
    VulnerabilitySource,
)


def _make_component(
    name: str,
    bom_ref: str,
    dependencies: list[str] | None = None,
) -> Component:
    """构造测试用 Component."""
    return Component(
        name=name,
        version="1.0.0",
        component_type=ComponentType.LIBRARY,
        purl=f"pkg:pypi/{name}@1.0.0",
        bom_ref=bom_ref,
        dependencies=dependencies or [],
    )


def _make_vuln(vuln_id: str, severity: VulnerabilitySeverity) -> Vulnerability:
    """构造测试用 Vulnerability."""
    return Vulnerability(
        id=vuln_id,
        source_name="test-db",
        description="Test vulnerability",
        severity=severity,
        cvss_score=7.5,
    )


def _make_scan_result(
    matches: list[VulnerabilityMatch],
    components_scanned: int = 0,
) -> ScanResult:
    """构造测试用 ScanResult（跳过真实 HTTP 扫描）."""
    return ScanResult(
        scan_id="test-scan-001",
        status=ScanStatus.COMPLETED,
        start_time=datetime.datetime(2026, 1, 1),
        end_time=datetime.datetime(2026, 1, 1, 0, 0, 5),
        components_scanned=components_scanned,
        vulnerabilities_found=len(matches),
        matches=matches,
    )


def _make_match(
    component: Component,
    vuln: Vulnerability,
) -> VulnerabilityMatch:
    """构造测试用 VulnerabilityMatch."""
    return VulnerabilityMatch(
        component=component,
        vulnerability=vuln,
        source=VulnerabilitySource.OSV,
        confidence=0.95,
    )


def _make_verifier_with_scan(scan_result: ScanResult) -> SupplyChainVerifier:
    """构造 SupplyChainVerifier，scan_sbom 被 mock 为返回指定结果."""
    mock_scanner = MagicMock()
    mock_scanner.scan_sbom.return_value = scan_result
    return SupplyChainVerifier(vuln_scanner=mock_scanner)


class TestSupplyChainVerifier:
    def test_clean_sbom_high_trust(self) -> None:
        """无漏洞的 SBOM → 所有组件信任分 > threshold, attestation_valid=True."""
        components = [
            _make_component("lib-a", "ref-a"),
            _make_component("lib-b", "ref-b"),
        ]
        sbom = SBOM(components=components)
        scan_result = _make_scan_result(matches=[], components_scanned=2)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        assert report.attestation_valid is True
        assert report.untrusted == []
        assert report.vulnerabilities_found == 0
        # 无漏洞时信任分应保持初始值 70.0
        for bom_ref in ("ref-a", "ref-b"):
            assert report.propagated_trust[bom_ref] >= 30.0

    def test_critical_vuln_lowers_trust(self) -> None:
        """含 CRITICAL 漏洞的组件 → 信任分下降 40."""
        comp_a = _make_component("lib-a", "ref-a")
        sbom = SBOM(components=[comp_a])
        match = _make_match(comp_a, _make_vuln("CVE-2026-001", VulnerabilitySeverity.CRITICAL))
        scan_result = _make_scan_result(matches=[match], components_scanned=1)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        # 初始 70.0 - 40.0 = 30.0（恰好等于阈值，不算 untrusted）
        assert report.component_trust["ref-a"] == 30.0
        assert report.vulnerabilities_found == 1

    def test_untrusted_components_listed(self) -> None:
        """信任分低于阈值的组件出现在 untrusted 列表."""
        comp_a = _make_component("lib-a", "ref-a")
        sbom = SBOM(components=[comp_a])
        # CRITICAL (-40) + HIGH (-25) = -65 → 70 - 65 = 5 < 30
        match1 = _make_match(comp_a, _make_vuln("CVE-001", VulnerabilitySeverity.CRITICAL))
        match2 = _make_match(comp_a, _make_vuln("CVE-002", VulnerabilitySeverity.HIGH))
        scan_result = _make_scan_result(matches=[match1, match2], components_scanned=1)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        assert "ref-a" in report.untrusted
        assert report.attestation_valid is False

    def test_dependencies_propagate_trust(self) -> None:
        """父组件有漏洞时，依赖它的子组件信任分也下降（传播）."""
        # B 依赖 A；A 有 CRITICAL 漏洞
        comp_a = _make_component("lib-a", "ref-a")
        comp_b = _make_component("lib-b", "ref-b", dependencies=["ref-a"])
        sbom = SBOM(components=[comp_a, comp_b])
        match = _make_match(comp_a, _make_vuln("CVE-001", VulnerabilitySeverity.CRITICAL))
        scan_result = _make_scan_result(matches=[match], components_scanned=2)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        # A 的初始信任 70 - 40 = 30
        assert report.component_trust["ref-a"] == 30.0
        # B 的传播后信任应低于初始 70（因 A 的信任下降通过边 A→B 传播）
        # 注意：TrustPropagation 算法中，incoming 边的 source trust 影响target
        # 边方向是 A→B（依赖项→依赖者），所以 A 的低信任会拉低 B
        assert report.propagated_trust["ref-b"] < 70.0

    def test_attestation_invalid_when_untrusted(self) -> None:
        """有 untrusted 组件时 attestation_valid=False."""
        comp_a = _make_component("lib-a", "ref-a")
        sbom = SBOM(components=[comp_a])
        match = _make_match(comp_a, _make_vuln("CVE-001", VulnerabilitySeverity.CRITICAL))
        match2 = _make_match(comp_a, _make_vuln("CVE-002", VulnerabilitySeverity.HIGH))
        scan_result = _make_scan_result(matches=[match, match2], components_scanned=1)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        assert report.attestation_valid is False
        assert len(report.untrusted) > 0

    def test_empty_sbom_returns_valid(self) -> None:
        """空 SBOM → attestation_valid=True, 无组件."""
        sbom = SBOM(components=[])
        scan_result = _make_scan_result(matches=[], components_scanned=0)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        assert report.attestation_valid is True
        assert report.untrusted == []
        assert report.component_trust == {}
        assert report.propagated_trust == {}
        assert report.vulnerabilities_found == 0

    def test_report_to_dict(self) -> None:
        """to_dict() 返回完整字段."""
        comp_a = _make_component("lib-a", "ref-a")
        sbom = SBOM(components=[comp_a])
        scan_result = _make_scan_result(matches=[], components_scanned=1)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)
        d = report.to_dict()

        assert "component_trust" in d
        assert "propagated_trust" in d
        assert "untrusted" in d
        assert "attestation_valid" in d
        assert "vulnerabilities_found" in d
        assert "trust_threshold" in d
        assert "propagation_iterations" in d
        assert d["attestation_valid"] is True
        assert d["trust_threshold"] == SupplyChainVerifier.DEFAULT_TRUST_THRESHOLD

    def test_multiple_vulnerabilities_accumulate(self) -> None:
        """多个漏洞的扣分累加，最低降到 0.0."""
        comp_a = _make_component("lib-a", "ref-a")
        sbom = SBOM(components=[comp_a])
        # CRITICAL(-40) + CRITICAL(-40) + HIGH(-25) = -105 → max(0, 70-105) = 0
        matches = [
            _make_match(comp_a, _make_vuln("CVE-001", VulnerabilitySeverity.CRITICAL)),
            _make_match(comp_a, _make_vuln("CVE-002", VulnerabilitySeverity.CRITICAL)),
            _make_match(comp_a, _make_vuln("CVE-003", VulnerabilitySeverity.HIGH)),
        ]
        scan_result = _make_scan_result(matches=matches, components_scanned=1)
        verifier = _make_verifier_with_scan(scan_result)

        report = verifier.verify(sbom)

        assert report.component_trust["ref-a"] == 0.0
        assert "ref-a" in report.untrusted


class TestRegisterSupplyChainVerifier:
    def test_registers_verifier_entry(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry, VerifierStatus

        registry = VerifierRegistry()
        register_supply_chain_verifier(registry)

        entry = registry.get("supply_chain_trust_verifier")
        assert entry is not None
        assert entry.model == "SupplyChainVerifier v1"
        assert entry.methodology == "recursive_trust_propagation"
        assert entry.status == VerifierStatus.ACTIVE
        assert entry.accuracy == 0.88

    def test_registered_verifier_listed_active(self) -> None:
        from maref.governance.verifier_registry import VerifierRegistry

        registry = VerifierRegistry()
        register_supply_chain_verifier(registry)

        active = registry.list_active()
        names = [v.name for v in active]
        assert "supply_chain_trust_verifier" in names


class TestSeverityPenalty:
    def test_critical_penalty_is_40(self) -> None:
        assert SEVERITY_PENALTY[VulnerabilitySeverity.CRITICAL] == 40.0

    def test_high_penalty_is_25(self) -> None:
        assert SEVERITY_PENALTY[VulnerabilitySeverity.HIGH] == 25.0

    def test_unknown_penalty_is_zero(self) -> None:
        assert SEVERITY_PENALTY[VulnerabilitySeverity.UNKNOWN] == 0.0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
