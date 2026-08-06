"""Tests for cross-dimensional TLA+ invariants (P3.1)."""

from pathlib import Path

from maref.recursive.tla_replay import TLAInvariantCheck, TLAReplayRunner

SPEC_PATH = Path(__file__).parent.parent.parent / "src" / "formal" / "MAREF_ConstitutionalRedLines.tla"
CFG_PATH = SPEC_PATH.with_suffix(".cfg")


class TestCrossDimTLAInvariants:
    def test_spec_file_exists(self):
        assert SPEC_PATH.exists(), f"TLA+ spec not found: {SPEC_PATH}"

    def test_spec_contains_cross_dim_section(self):
        text = SPEC_PATH.read_text()
        assert "CrossDimSecurityInv" in text
        assert "MaxFilesPerRoundInv" in text
        assert "CrossImpactMonitoringInv" in text
        assert "WeightAdjustmentBoundInv" in text

    def test_spec_contains_protected_dim(self):
        text = SPEC_PATH.read_text()
        assert "ProtectedDim" in text

    def test_spec_contains_file_count_max(self):
        text = SPEC_PATH.read_text()
        assert "FileCountMax" in text

    def test_spec_contains_max_adjustment(self):
        text = SPEC_PATH.read_text()
        assert "MaxAdjustment" in text

    def test_replay_runner_can_instantiate_from_spec(self):
        runner = TLAReplayRunner(spec_path=str(SPEC_PATH))
        report = runner.generate_report()
        assert report.total_checks > 0
        assert report.spec_path == str(SPEC_PATH)

    def test_replay_runner_finds_cross_dim_invariants(self):
        runner = TLAReplayRunner(spec_path=str(SPEC_PATH))
        names = [inv["name"] for inv in runner.invariants]
        assert "CrossDimSecurityInv" in names
        assert "MaxFilesPerRoundInv" in names
        assert "CrossImpactMonitoringInv" in names
        assert "WeightAdjustmentBoundInv" in names

    def test_replay_runner_run_check(self):
        runner = TLAReplayRunner(spec_path=str(SPEC_PATH))
        result = runner.run_check("CrossDimSecurityInv")
        assert result.passed
        assert result.invariant_name == "CrossDimSecurityInv"

    def test_replay_runner_run_all_contains_new_invariants(self):
        runner = TLAReplayRunner(spec_path=str(SPEC_PATH))
        results = runner.run_all()
        result_names = [r.invariant_name for r in results]
        assert "CrossDimSecurityInv" in result_names
        assert "MaxFilesPerRoundInv" in result_names
        assert "CrossImpactMonitoringInv" in result_names
        assert "WeightAdjustmentBoundInv" in result_names

    def test_cfg_file_exists(self):
        cfg = SPEC_PATH.parent / "MAREF_CrossDimModel.cfg"
        assert cfg.exists(), f"TLA+ cfg not found: {cfg}"

    def test_all_old_invariants_still_present(self):
        text = SPEC_PATH.read_text()
        assert "RedLineImmutabilityInv" in text
        assert "SafetyGateIntegrityInv" in text
        assert "AuditTrailCompletenessInv" in text
        assert "ConstitutionSupremacyInv" in text
        assert "HumanConstitutionSoleAuthorityInv" in text
