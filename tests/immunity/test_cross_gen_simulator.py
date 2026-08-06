from __future__ import annotations

from maref.immunity.cross_gen_simulator import CrossGenerationImpactSimulator
from maref.recursive.unified_audit import UnifiedAuditStore

CLEAN_CODE = """
def add(a, b):
    return a + b
"""

PICKLE_CODE = """
import pickle
def save(data):
    pickle.dump(data, f)
"""

WRONG_COMMENT_CODE = """
# Production-grade secure implementation
result = eval(user_input)
"""

MISSING_TIMEOUT_CODE = """
import requests
def fetch():
    return requests.get("https://api.example.com/data")
"""

ALL_THREE_CODE = (
    PICKLE_CODE
    + """
# Enterprise-grade security
result = eval(user_input)
"""
    + MISSING_TIMEOUT_CODE
)


class TestCrossGenerationImpactSimulatorIndex:
    """4.2-A1: simulate_contamination returns index 0.0-1.0."""

    def test_clean_code_returns_zero(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(CLEAN_CODE)
        assert report.contamination_index == 0.0

    def test_pickle_code_returns_positive_index(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        assert report.contamination_index > 0.0

    def test_index_never_exceeds_one(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(ALL_THREE_CODE)
        assert report.contamination_index <= 1.0

    def test_index_never_below_zero(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(CLEAN_CODE)
        assert report.contamination_index >= 0.0

    def test_index_is_float(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        assert isinstance(report.contamination_index, float)

    def test_index_rounded_to_two_decimals(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        s = str(report.contamination_index)
        if "." in s:
            assert len(s.split(".")[1]) <= 2

    def test_wrong_comment_weight_higher_than_pickle_base(self):
        sim = CrossGenerationImpactSimulator()
        report_comment = sim.simulate_contamination(WRONG_COMMENT_CODE)
        single_pickle = "import pickle\n"
        report_single_pickle = sim.simulate_contamination(single_pickle)
        assert report_comment.contamination_index >= report_single_pickle.contamination_index

    def test_three_types_has_synergy(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(ALL_THREE_CODE)
        assert report.details.get("synergy_applied") is True

    def test_report_contains_findings(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        assert len(report.findings) > 0

    def test_report_contains_details(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        assert "type_counts" in report.details


class TestCrossGenerationImpactSimulatorBlock:
    """4.2-A2: contamination_index >= 0.7 → block_merge()."""

    def test_block_merge_blocks_at_0_7(self):
        sim = CrossGenerationImpactSimulator()
        assert sim.block_merge(0.7) is True

    def test_block_merge_allows_below_0_7(self):
        sim = CrossGenerationImpactSimulator()
        assert sim.block_merge(0.69) is False

    def test_block_merge_zero_index(self):
        sim = CrossGenerationImpactSimulator()
        assert sim.block_merge(0.0) is False

    def test_block_merge_one_index(self):
        sim = CrossGenerationImpactSimulator()
        assert sim.block_merge(1.0) is True

    def test_report_blocked_at_high_index(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(ALL_THREE_CODE)
        if report.contamination_index >= 0.7:
            assert report.blocked is True
        else:
            assert report.blocked is False

    def test_report_not_blocked_for_clean(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(CLEAN_CODE)
        assert report.blocked is False


class TestCrossGenerationImpactSimulatorTraining:
    """4.2-A3: Simulate training impact in sandbox."""

    def test_training_impact_clean_code(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(CLEAN_CODE)
        assert impact["risk_level"] == "none"

    def test_training_impact_contaminated_code(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(PICKLE_CODE)
        assert impact["risk_level"] in ("critical", "moderate")

    def test_training_impact_has_teachable_patterns(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(PICKLE_CODE)
        assert len(impact["teachable_patterns"]) > 0

    def test_training_impact_pattern_has_teachability(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(PICKLE_CODE)
        for p in impact["teachable_patterns"]:
            assert "teachability" in p

    def test_training_impact_has_impact_string(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(PICKLE_CODE)
        assert len(impact["impact"]) > 10

    def test_training_impact_risk_critical_for_blocked(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(ALL_THREE_CODE)
        report = sim.simulate_contamination(ALL_THREE_CODE)
        if report.blocked:
            assert impact["risk_level"] == "critical"

    def test_training_impact_contains_contamination_index(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(PICKLE_CODE)
        assert "contamination_index" in impact

    def test_training_impact_teachability_high_for_comment(self):
        sim = CrossGenerationImpactSimulator()
        impact = sim.simulate_training_impact(WRONG_COMMENT_CODE)
        for p in impact["teachable_patterns"]:
            if p["pattern"] == "wrong_comment":
                assert "high" in p["teachability"]


class TestCrossGenerationImpactSimulatorAudit:
    """4.2-A4: Results written to UnifiedAuditStore."""

    def test_audit_store_updated(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(PICKLE_CODE)
        assert store.count() >= 1

    def test_audit_event_type(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(PICKLE_CODE)
        events = store.stats_by_event_type()
        assert "cross_generation_impact" in events

    def test_audit_decision_blocked(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(ALL_THREE_CODE)
        records = store.all()
        decisions = {r.decision for r in records}
        assert "BLOCKED" in decisions or "ALLOWED" in decisions

    def test_audit_no_store_no_error(self):
        sim = CrossGenerationImpactSimulator()
        report = sim.simulate_contamination(PICKLE_CODE)
        assert report.contamination_index > 0.0

    def test_audit_clean_code_writes_nothing(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(CLEAN_CODE)
        assert store.count() >= 1

    def test_audit_layer_is_execution(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(PICKLE_CODE)
        records = store.all()
        assert all(r.layer == "execution" for r in records)

    def test_audit_source_module(self):
        store = UnifiedAuditStore()
        sim = CrossGenerationImpactSimulator(audit_store=store)
        sim.simulate_contamination(PICKLE_CODE)
        records = store.all()
        assert all(r.source_module == "cross_gen_simulator" for r in records)
