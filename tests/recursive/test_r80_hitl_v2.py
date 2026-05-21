from __future__ import annotations

from maref.recursive.hitl_v2 import (
    AdversarialAuditor,
    AuditScope,
    ChainReactionBreaker,
    DecisionNode,
    FrequencyMatcher,
    ObservableProcess,
    ProcessTelemetry,
)


class TestAdversarialAuditor:
    def test_schedule_audit(self) -> None:
        auditor = AdversarialAuditor()
        window = auditor.schedule_unannounced_audit("agent_a", min_delay_s=0.1, max_delay_s=1.0)
        assert window.target == "agent_a"
        assert window.scheduled_at > 0

    def test_execute_audit(self) -> None:
        auditor = AdversarialAuditor()
        report = auditor.execute_audit("agent_a")
        assert report.target == "agent_a"
        assert 0.0 <= report.score <= 1.0
        assert len(report.injection_results) > 0

    def test_adversarial_coverage(self) -> None:
        auditor = AdversarialAuditor()
        scope = AuditScope(target="agent_a", injection_vector_count=5)
        auditor.execute_audit("agent_a", scope)
        coverage = auditor.adversarial_coverage()
        assert 0.0 <= coverage <= 1.0

    def test_pending_audits(self) -> None:
        auditor = AdversarialAuditor()
        auditor.schedule_unannounced_audit("agent_a", min_delay_s=10, max_delay_s=20)
        pending = auditor.pending_audits()
        assert len(pending) == 0


class TestFrequencyMatcher:
    def test_optimal_frequency(self) -> None:
        matcher = FrequencyMatcher()
        freq = matcher.optimal_frequency(0.5, 0.5, 1.0)
        assert freq > 0

    def test_high_risk_more_frequent(self) -> None:
        matcher = FrequencyMatcher()
        freq_high = matcher.optimal_frequency(0.9, 0.9, 1.0)
        freq_low = matcher.optimal_frequency(0.2, 0.2, 1.0)
        assert freq_high < freq_low

    def test_adaptive_interval_improving(self) -> None:
        matcher = FrequencyMatcher(base_interval_s=100.0)
        interval = matcher.adaptive_interval("improving", 0.01)
        assert interval > 100.0

    def test_adaptive_interval_declining(self) -> None:
        matcher = FrequencyMatcher(base_interval_s=100.0)
        interval = matcher.adaptive_interval("declining", 0.01)
        assert interval < 100.0

    def test_adaptive_interval_high_errors(self) -> None:
        matcher = FrequencyMatcher(base_interval_s=100.0)
        interval = matcher.adaptive_interval("stable", 0.15)
        assert interval < 100.0

    def test_adaptive_interval_bounds(self) -> None:
        matcher = FrequencyMatcher(base_interval_s=10.0)
        interval = matcher.adaptive_interval("improving", 0.001)
        assert interval >= 60.0
        interval = matcher.adaptive_interval("declining", 0.5)
        assert interval <= 86400.0


class TestObservableProcess:
    def test_instrument(self) -> None:
        observable = ObservableProcess()
        telemetry = observable.instrument("proc_1")
        assert telemetry.process_id == "proc_1"
        assert isinstance(telemetry, ProcessTelemetry)

    def test_record_decision(self) -> None:
        observable = ObservableProcess()
        observable.instrument("proc_1")
        node = DecisionNode(step=1, decision="choose_option_a", chosen="option_a")
        observable.record_decision("proc_1", node)
        telemetry = observable.get_telemetry("proc_1")
        assert telemetry is not None
        assert len(telemetry.decisions) == 1

    def test_replay(self) -> None:
        observable = ObservableProcess()
        observable.instrument("proc_1")
        node = DecisionNode(step=1, decision="step_1", chosen="a")
        observable.record_decision("proc_1", node)
        replay = observable.replay("proc_1")
        assert replay is not None
        assert len(replay.steps) == 1

    def test_replay_unknown_process(self) -> None:
        observable = ObservableProcess()
        assert observable.replay("unknown") is None

    def test_list_processes(self) -> None:
        observable = ObservableProcess()
        observable.instrument("proc_a")
        observable.instrument("proc_b")
        processes = observable.list_processes()
        assert "proc_a" in processes
        assert "proc_b" in processes


class TestChainReactionBreaker:
    def test_detect_chain(self) -> None:
        breaker = ChainReactionBreaker(max_chain_length=3)
        for i in range(5):
            breaker.record_event("chain_1", "agent_a", f"event_{i}")
        assert breaker.detect_chain("chain_1")

    def test_no_chain_short(self) -> None:
        breaker = ChainReactionBreaker(max_chain_length=10)
        breaker.record_event("chain_1", "agent_a", "event_0")
        breaker.record_event("chain_1", "agent_a", "event_1")
        assert not breaker.detect_chain("chain_1")

    def test_break_chain(self) -> None:
        breaker = ChainReactionBreaker(max_chain_length=3)
        for i in range(5):
            breaker.record_event("chain_1", "agent_a", f"event_{i}")
        assert breaker.detect_chain("chain_1")
        assert breaker.break_chain("chain_1", 2)
        assert breaker.is_broken("chain_1")
        assert breaker.chain_length("chain_1") == 2

    def test_break_already_broken(self) -> None:
        breaker = ChainReactionBreaker()
        breaker.record_event("c1", "a", "e")
        breaker.break_chain("c1", 0)
        assert not breaker.break_chain("c1", 0)

    def test_active_chains(self) -> None:
        breaker = ChainReactionBreaker(max_chain_length=3)
        breaker.record_event("chain_a", "agent_1", "e1")
        breaker.record_event("chain_a", "agent_1", "e2")
        breaker.record_event("chain_b", "agent_2", "e1")
        active = breaker.active_chains()
        assert len(active) == 2
        assert active["chain_a"] == 2
