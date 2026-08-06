"""Tests for ConstitutionGuard RL-008 ~ RL-012 extensions.

Covers:
- RL-008: Output sanitization (steganography detection)
- RL-009: Data localization violation
- RL-010: Identity verification (enum registration)
- RL-011: Supply chain attestation
- RL-012: Jurisdiction compliance (sanctions)
- InvariantCode enum has 12 members
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from maref.evolution.constitution_guard import (
    ConstitutionGuard,
    InvariantCode,
)
from maref.supply_chain.sbom_generator import (
    SBOM,
    Component,
    ComponentType,
)


def _make_component(name: str, bom_ref: str) -> Component:
    return Component(
        name=name,
        version="1.0.0",
        component_type=ComponentType.LIBRARY,
        purl=f"pkg:pypi/{name}@1.0.0",
        bom_ref=bom_ref,
    )


class TestInvariantCodeEnum:
    def test_enum_has_12_members(self) -> None:
        """InvariantCode 枚举含 12 个成员（RL-001 ~ RL-012）."""
        members = list(InvariantCode)
        assert len(members) == 12

    def test_rl008_value(self) -> None:
        assert (
            InvariantCode.RL_008_OUTPUT_SANITIZATION_REQUIRED.value
            == "output_sanitization_required"
        )

    def test_rl009_value(self) -> None:
        assert InvariantCode.RL_009_DATA_LOCALIZATION.value == "data_localization_violation"

    def test_rl010_value(self) -> None:
        assert InvariantCode.RL_010_IDENTITY_VERIFICATION.value == "identity_verification_required"

    def test_rl011_value(self) -> None:
        assert (
            InvariantCode.RL_011_SUPPLY_CHAIN_ATTESTATION.value
            == "supply_chain_attestation_required"
        )

    def test_rl012_value(self) -> None:
        assert (
            InvariantCode.RL_012_JURISDICTION_COMPLIANCE.value
            == "jurisdiction_compliance_violation"
        )


class TestValidateOutput:
    def test_rl008_clean_output_passes(self) -> None:
        """清洁文本 → validate_output allowed=True."""
        guard = ConstitutionGuard()
        result = guard.validate_output("agent-1", "Hello, normal message.")
        assert result.allowed is True
        assert result.violations == []

    def test_rl008_stego_output_fails(self) -> None:
        """含 U+02B9 → allowed=False, invariant_codes 含 RL-008."""
        guard = ConstitutionGuard()
        result = guard.validate_output("agent-1", "hello\u02b9world")
        assert result.allowed is False
        assert InvariantCode.RL_008_OUTPUT_SANITIZATION_REQUIRED in result.invariant_codes
        assert len(result.violations) == 1
        assert "RL-008" in result.violations[0]

    def test_rl008_zero_width_detected(self) -> None:
        """含零宽字符 → 违反 RL-008."""
        guard = ConstitutionGuard()
        result = guard.validate_output("agent-1", "a\u200bb")
        assert result.allowed is False
        assert InvariantCode.RL_008_OUTPUT_SANITIZATION_REQUIRED in result.invariant_codes

    def test_rl008_disabled_guard_passes(self) -> None:
        """guard 禁用时 → allowed=True（即使有 stego）."""
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_output("agent-1", "evil\u02b9")
        assert result.allowed is True


class TestValidateDeployment:
    def test_rl009_data_localization_violation(self) -> None:
        """EU 要求数据主权, data_residency=US → 违反 RL-009."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "EU", "US")
        assert result.allowed is False
        assert InvariantCode.RL_009_DATA_LOCALIZATION in result.invariant_codes

    def test_rl009_data_localization_pass(self) -> None:
        """EU 要求数据主权, data_residency=EU → 通过."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "EU", "EU")
        assert result.allowed is True

    def test_rl012_sanctioned_jurisdiction(self) -> None:
        """RU 制裁辖区 → 违反 RL-012."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "RU", "RU")
        assert result.allowed is False
        assert InvariantCode.RL_012_JURISDICTION_COMPLIANCE in result.invariant_codes

    def test_rl012_iran_sanctioned(self) -> None:
        """IR 制裁辖区 → 违反 RL-012."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "IR", "IR")
        assert result.allowed is False
        assert InvariantCode.RL_012_JURISDICTION_COMPLIANCE in result.invariant_codes

    def test_rl009_and_rl012_both_triggered(self) -> None:
        """RU 制裁 + 数据主权, data_residency=US → 同时违反 RL-009 和 RL-012."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "RU", "US")
        assert result.allowed is False
        assert InvariantCode.RL_009_DATA_LOCALIZATION in result.invariant_codes
        assert InvariantCode.RL_012_JURISDICTION_COMPLIANCE in result.invariant_codes

    def test_normal_jurisdiction_passes(self) -> None:
        """正常管辖区(US, 无数据主权要求) → 通过."""
        guard = ConstitutionGuard()
        result = guard.validate_deployment("agent-1", "US", "US")
        assert result.allowed is True
        assert result.violations == []

    def test_disabled_guard_passes(self) -> None:
        """guard 禁用时 → allowed=True."""
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_deployment("agent-1", "RU", "US")
        assert result.allowed is True


class TestValidateIdentity:
    def test_rl010_identity_not_proven_fails(self) -> None:
        """identity_proven=False → 违反 RL-010."""
        guard = ConstitutionGuard()
        result = guard.validate_identity("agent-1", identity_proven=False)
        assert result.allowed is False
        assert InvariantCode.RL_010_IDENTITY_VERIFICATION in result.invariant_codes
        assert "RL-010" in result.violations[0]

    def test_rl010_identity_proven_passes(self) -> None:
        """identity_proven=True → 通过."""
        guard = ConstitutionGuard()
        result = guard.validate_identity("agent-1", identity_proven=True)
        assert result.allowed is True
        assert result.violations == []

    def test_rl010_disabled_guard_passes(self) -> None:
        """guard 禁用时 → allowed=True（即使 identity 未验证）."""
        guard = ConstitutionGuard(enabled=False)
        result = guard.validate_identity("agent-1", identity_proven=False)
        assert result.allowed is True


class TestValidateSupplyChain:
    @patch("maref.supply_chain.trust_verifier.SupplyChainVerifier")
    def test_rl011_untrusted_supply_chain(
        self,
        mock_verifier_class: MagicMock,
    ) -> None:
        """含漏洞的 SBOM → 违反 RL-011（mock SupplyChainVerifier）."""
        mock_report = MagicMock()
        mock_report.attestation_valid = False
        mock_report.untrusted = ["comp-a", "comp-b"]
        mock_verifier_class.return_value.verify.return_value = mock_report

        guard = ConstitutionGuard()
        sbom = SBOM(components=[_make_component("lib", "comp-a")])
        result = guard.validate_supply_chain("agent-1", sbom)

        assert result.allowed is False
        assert InvariantCode.RL_011_SUPPLY_CHAIN_ATTESTATION in result.invariant_codes
        assert "RL-011" in result.violations[0]

    @patch("maref.supply_chain.trust_verifier.SupplyChainVerifier")
    def test_rl011_clean_supply_chain(
        self,
        mock_verifier_class: MagicMock,
    ) -> None:
        """无漏洞 SBOM → 通过（mock SupplyChainVerifier）."""
        mock_report = MagicMock()
        mock_report.attestation_valid = True
        mock_report.untrusted = []
        mock_verifier_class.return_value.verify.return_value = mock_report

        guard = ConstitutionGuard()
        sbom = SBOM(components=[_make_component("lib", "comp-a")])
        result = guard.validate_supply_chain("agent-1", sbom)

        assert result.allowed is True

    def test_disabled_guard_passes(self) -> None:
        """guard 禁用时 → allowed=True."""
        guard = ConstitutionGuard(enabled=False)
        sbom = SBOM(components=[])
        result = guard.validate_supply_chain("agent-1", sbom)
        assert result.allowed is True


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
