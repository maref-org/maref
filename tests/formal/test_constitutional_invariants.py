"""Tests for constitutional TLA+ invariants (P5.3)."""

from pathlib import Path

from maref.recursive.tla_replay import TLAReplayRunner

SPEC_PATH = Path(__file__).parent.parent.parent / "src" / "formal" / "MAREF_ConstitutionalRedLines.tla"


class TestConstitutionalTLAInvariants:
    def test_spec_file_exists(self):
        assert SPEC_PATH.exists()

    def test_contains_constitutional_section(self):
        text = SPEC_PATH.read_text()
        assert "CONSTITUTIONAL INVARIANTS" in text

    def test_contains_rl001(self):
        text = SPEC_PATH.read_text()
        assert "RSIRL001_ResourceBoundInv" in text

    def test_contains_rl003(self):
        text = SPEC_PATH.read_text()
        assert "RSIRL003_GateRequirementInv" in text

    def test_contains_rl004(self):
        text = SPEC_PATH.read_text()
        assert "RSIRL004_HumanAuthorityInv" in text

    def test_contains_rl005(self):
        text = SPEC_PATH.read_text()
        assert "RSIRL005_LoggingRequirementInv" in text

    def test_tla_replay_runner_parses_invariants(self):
        runner = TLAReplayRunner(spec_path=str(SPEC_PATH))
        invariants = runner.invariants
        names = [inv["name"] for inv in invariants]
        assert "RSIRL001_ResourceBoundInv" in names
        assert "RSIRL003_GateRequirementInv" in names

    def test_backward_compatible_with_original(self):
        text = SPEC_PATH.read_text()
        assert "RedLineImmutability" in text
        assert "SafetyGateIntegrity" in text
        assert "AuditTrailCompleteness" in text
        assert "ConstitutionSupremacy" in text
        assert "HumanConstitutionSoleAuthority" in text

    def test_backward_compatible_with_cross_dim(self):
        text = SPEC_PATH.read_text()
        assert "CrossDimSecurityInv" in text
        assert "MaxFilesPerRoundInv" in text
        assert "CrossImpactMonitoringInv" in text
        assert "WeightAdjustmentBoundInv" in text
