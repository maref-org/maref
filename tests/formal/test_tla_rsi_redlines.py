"""P5.3 TLA+ constitutional red lines completeness tests.

Validates that the TLA+ specification covers all 5 RSI red lines
(RL-001~005) with formal invariants, including the newly added
RSI-RL-002 (Gray Code FSM agent autonomy).
"""

from __future__ import annotations

from pathlib import Path

import pytest

TLA_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "formal"
    / "MAREF_ConstitutionalRedLines.tla"
)
CFG_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "formal"
    / "MAREF_ConstitutionalRedLinesMC.cfg"
)


@pytest.fixture(scope="module")
def tla_content() -> str:
    return TLA_PATH.read_text()


@pytest.fixture(scope="module")
def cfg_content() -> str:
    return CFG_PATH.read_text()


class TestRSIRedLineCoverage:
    """All 7 RSI red lines must have formal invariants."""

    def test_rl001_resource_bound(self, tla_content: str) -> None:
        assert "RSIRL001_ResourceBoundInv" in tla_content

    def test_rl002_agent_autonomy(self, tla_content: str) -> None:
        assert "RSIRL002_AgentAutonomyInv" in tla_content

    def test_rl003_gate_requirement(self, tla_content: str) -> None:
        assert "RSIRL003_GateRequirementInv" in tla_content

    def test_rl004_human_authority(self, tla_content: str) -> None:
        assert "RSIRL004_HumanAuthorityInv" in tla_content

    def test_rl005_logging_requirement(self, tla_content: str) -> None:
        assert "RSIRL005_LoggingRequirementInv" in tla_content

    def test_rl006_security_dim_protection(self, tla_content: str) -> None:
        assert "RSIRL006_SecurityDimProtectionInv" in tla_content

    def test_rl007_max_files_per_round(self, tla_content: str) -> None:
        assert "RSIRL007_MaxFilesPerRoundInv" in tla_content


class TestGrayCodeFSM:
    """RSI-RL-002 Gray Code FSM formalization."""

    def test_gray_code_states_defined(self, tla_content: str) -> None:
        assert "GrayCodeStates" in tla_content

    def test_valid_transition_defined(self, tla_content: str) -> None:
        assert "ValidGrayCodeTransition" in tla_content

    def test_agent_state_transition_action(self, tla_content: str) -> None:
        assert "AgentStateTransition" in tla_content

    def test_agent_state_in_vars(self, tla_content: str) -> None:
        assert "agentState" in tla_content

    @staticmethod
    def _to_gray(i: int) -> int:
        """Convert integer to Gray code bit representation."""
        return i ^ (i >> 1)

    def test_gray_code_transition_logic(self) -> None:
        """Verify 2-bit Gray Code transitions have Hamming distance = 1."""

        def hamming_gray(a: int, b: int) -> int:
            return bin(self._to_gray(a) ^ self._to_gray(b)).count("1")

        for i in range(4):
            for delta in [1, 3]:
                target = (i + delta) % 4
                assert hamming_gray(i, target) == 1, (
                    f"Gray Code transition {i}->{target} has "
                    f"Hamming distance {hamming_gray(i, target)}"
                )

    def test_invalid_transition_blocked(self) -> None:
        """Non-adjacent transitions have Hamming distance > 1."""

        def hamming_gray(a: int, b: int) -> int:
            return bin(self._to_gray(a) ^ self._to_gray(b)).count("1")

        assert hamming_gray(0, 2) == 2
        assert hamming_gray(1, 3) == 2


class TestTLCConfig:
    """TLC model checker configuration includes all invariants."""

    def test_cfg_has_rl_invariants(self, cfg_content: str) -> None:
        for inv in [
            "RSIRL002_AgentAutonomyInv",
            "RSIRL006_SecurityDimProtectionInv",
            "RSIRL007_MaxFilesPerRoundInv",
        ]:
            assert inv in cfg_content, f"{inv} missing from TLC config"

    def test_cfg_has_base_invariants(self, cfg_content: str) -> None:
        for inv in [
            "TypeInvariant",
            "RedLineImmutabilityInv",
            "SafetyGateIntegrityInv",
            "AuditTrailCompletenessInv",
            "ConstitutionSupremacyInv",
            "HumanConstitutionSoleAuthorityInv",
        ]:
            assert inv in cfg_content, f"{inv} missing from TLC config"


class TestNoPlaceholderNotes:
    """RSI-RL-002 should no longer have placeholder text."""

    def test_no_placeholder(self, tla_content: str) -> None:
        assert "Here we reference it as a constraint" not in tla_content
