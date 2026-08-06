from __future__ import annotations

from maref.stress.stress_result import StressResult


class TestStressResult:
    def test_default_construction(self):
        r = StressResult(round_id="r1", stress_level="L1")
        assert r.round_id == "r1"
        assert r.stress_level == "L1"
        assert r.latency_p50 == 0.0
        assert r.cb_state == "CLOSED"
        assert r.passed is True
        assert r.errors == []
        assert r.metadata == {}

    def test_passed_true_when_no_errors(self):
        r = StressResult(round_id="r1", stress_level="L1")
        assert r.passed is True

    def test_passed_false_when_has_errors(self):
        r = StressResult(round_id="r1", stress_level="L1", errors=["timeout"])
        assert r.passed is False

    def test_to_dict_includes_all_fields(self):
        r = StressResult(
            round_id="r2",
            stress_level="L3",
            axes_applied={"agent_concurrency": 500.0},
            latency_p50=10.0,
            latency_p99=50.0,
            latency_p99_9=100.0,
            cb_state="HALF_OPEN",
            meta_cb_state="CLOSED",
            healer_success_rate=0.85,
            healer_strategy_rates={"test_failure": 1.0},
            oscillation_detected=True,
            oscillation_resolved=True,
            revert_rate=0.1,
            ab_test_pass_rate=0.9,
            resilience_score=0.75,
            degradation_plans=["scale_down"],
            duration_s=30.0,
            errors=["warn"],
            metadata={"env": "test"},
        )
        d = r.to_dict()
        assert d["round_id"] == "r2"
        assert d["stress_level"] == "L3"
        assert d["latency_p50"] == 10.0
        assert d["cb_state"] == "HALF_OPEN"
        assert d["healer_success_rate"] == 0.85
        assert d["oscillation_detected"] is True
        assert d["resilience_score"] == 0.75
        assert d["errors"] == ["warn"]
        assert d["degradation_plans"] == ["scale_down"]

    def test_to_dict_custom_timestamp(self):
        r = StressResult(round_id="r3", stress_level="L1", timestamp=123456.0)
        d = r.to_dict()
        assert d["timestamp"] == 123456.0

    def test_passed_with_empty_errors_list(self):
        r = StressResult(round_id="r4", stress_level="L2", errors=[])
        assert r.passed is True
