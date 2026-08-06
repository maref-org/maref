from __future__ import annotations

from maref.metacognition.models import ProbeType
from maref.metacognition.stealth_probe import ProbeAnalyst, StealthProbe


class TestStealthProbe:
    def test_inject_honeypot(self) -> None:
        probe = StealthProbe(seed=42)
        result = probe.inject_honeypot("session-1", "code_review")
        assert result.probe_type == ProbeType.HONEYPOT
        assert result.session_id == "session-1"
        assert result.capability_tested == "code_review"
        assert result.expected_positive
        assert 0 <= result.confidence <= 1

    def test_inject_honeypot_unknown_capability(self) -> None:
        probe = StealthProbe(seed=42)
        result = probe.inject_honeypot("session-1", "unknown_cap")
        assert result.capability_tested == "unknown_cap"

    def test_counterfactual_test(self) -> None:
        probe = StealthProbe(seed=42)
        direct, inverted = probe.counterfactual_test("session-1", test_pair_index=0)
        assert direct.probe_type == ProbeType.COUNTERFACTUAL
        assert inverted.probe_type == ProbeType.COUNTERFACTUAL
        assert direct.session_id == "session-1"
        assert inverted.session_id == "session-1"
        assert direct.expected_positive
        assert not inverted.expected_positive

    def test_get_session_probes_empty(self) -> None:
        probe = StealthProbe()
        assert probe.get_session_probes("unknown") == []

    def test_get_session_probes_after_injection(self) -> None:
        probe = StealthProbe(seed=42)
        probe.inject_honeypot("session-1", "math_reasoning")
        probe.counterfactual_test("session-1", test_pair_index=1)
        results = probe.get_session_probes("session-1")
        assert len(results) == 3

    def test_different_seeds_different_results(self) -> None:
        p1 = StealthProbe(seed=1)
        p2 = StealthProbe(seed=2)
        r1 = p1.inject_honeypot("s1", "code_review")
        r2 = p2.inject_honeypot("s1", "code_review")
        assert r1.response_time != r2.response_time or r1.response_hides_capability != r2.response_hides_capability


class TestProbeAnalyst:
    def test_empty_analyst(self) -> None:
        analyst = ProbeAnalyst()
        assert analyst.hiding_ratio() == 0.0
        assert analyst.average_confidence() == 0.0

    def test_hiding_ratio(self) -> None:
        probe = StealthProbe(seed=42)
        analyst = ProbeAnalyst()
        for _ in range(10):
            result = probe.inject_honeypot("s1", "code_review")
            analyst.add_result(result)
        ratio = analyst.hiding_ratio()
        assert 0 <= ratio <= 1

    def test_capability_hiding_rate(self) -> None:
        probe = StealthProbe(seed=42)
        analyst = ProbeAnalyst()
        for _ in range(5):
            analyst.add_result(probe.inject_honeypot("s1", "code_review"))
        rate = analyst.capability_hiding_rate("code_review")
        assert 0 <= rate <= 1
        assert analyst.capability_hiding_rate("nonexistent") == 0.0
