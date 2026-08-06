from __future__ import annotations

from maref.recursive.chaos_injector import ChaosInjector, ChaosType
from maref.recursive.chaos_resilience import ChaosResilience, ResilienceReport
from maref.recursive.meta_governance import MetaGovernance


class TestChaosInjector:
    def test_inject_creates_event(self) -> None:
        injector = ChaosInjector()
        event = injector.inject(ChaosType.CB_OSCILLATION)
        assert event.injected is True
        assert event.chaos_type == ChaosType.CB_OSCILLATION

    def test_inject_with_target_and_params(self) -> None:
        injector = ChaosInjector()
        event = injector.inject(ChaosType.AGENT_CRASH, "governance_agent", {"severity": 9})
        assert event.target == "governance_agent"
        assert event.params == {"severity": 9}

    def test_events_accumulates(self) -> None:
        injector = ChaosInjector()
        injector.inject(ChaosType.CB_OSCILLATION)
        injector.inject(ChaosType.HALT_STORM)
        assert len(injector.events) == 2

    def test_events_of_type_filters(self) -> None:
        injector = ChaosInjector()
        injector.inject(ChaosType.CB_OSCILLATION)
        injector.inject(ChaosType.HALT_STORM)
        injector.inject(ChaosType.CB_OSCILLATION)
        oscillations = injector.events_of_type(ChaosType.CB_OSCILLATION)
        assert len(oscillations) == 2

    def test_clear_resets(self) -> None:
        injector = ChaosInjector()
        injector.inject(ChaosType.HALT_STORM)
        injector.clear()
        assert len(injector.events) == 0

    def test_chaos_type_enum(self) -> None:
        assert ChaosType.CB_OSCILLATION.value == "cb_oscillation"
        assert ChaosType.HALT_STORM.value == "halt_storm"


class TestChaosResilience:
    def test_run_stress_suite_returns_report(self) -> None:
        meta = MetaGovernance(depth=0)
        cr = ChaosResilience()
        report = cr.run_stress_suite(meta)
        assert isinstance(report, ResilienceReport)

    def test_resilience_score_in_range(self) -> None:
        meta = MetaGovernance(depth=0)
        cr = ChaosResilience()
        score = cr.resilience_score(meta)
        assert 0.0 <= score <= 100.0

    def test_report_includes_survival_rate(self) -> None:
        meta = MetaGovernance(depth=0)
        cr = ChaosResilience()
        report = cr.run_stress_suite(meta)
        assert report.survival_rate > 0.0
