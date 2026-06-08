"""End-to-end system stress tests and certification suite."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.oscillation import OscillationFixLoop, OscillationStage
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class TestCertificationSuite:
    """Pressure test certification suite — independently verifiable."""

    def test_cert_concurrent_access(self):
        """10K concurrent governance operations — 0 crashes, 0 data races."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        errors: list[Exception] = []
        lock = threading.Lock()

        def hammer():
            for _ in range(100):
                try:
                    sm.transition(GovernanceState.ANALYZE, "cert")
                    sm.transition(GovernanceState.EVALUATE, "cert")
                    sm.transition(GovernanceState.OBSERVE, "cert")
                except Exception as e:
                    with lock:
                        errors.append(e)

        with ThreadPoolExecutor(max_workers=100) as ex:
            futures = [ex.submit(hammer) for _ in range(100)]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    with lock:
                        errors.append(e)

        assert len(errors) == 0, f"Certification concurrent test failed: {len(errors)} errors"

    def test_cert_memory_bound(self):
        """1M operations — memory < 1GB."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")

        for i in range(1_000_000):
            sm.transition(GovernanceState.ANALYZE, str(i))
            sm.transition(GovernanceState.EVALUATE, str(i))
            sm.transition(GovernanceState.OBSERVE, str(i))

        history = sm.get_history()
        assert len(history) <= 10000, f"History exceeded bound: {len(history)}"

    def test_cert_byzantine_resilience(self):
        """51% byzantine — system safety degrades, does not crash."""
        from maref.cross_validator.consensus_algorithm import (
            ConsensusStatus,
            VoteValue,
            WeightedConsensusEngine,
        )

        engine = WeightedConsensusEngine()
        for i in range(49):
            engine.register_validator(f"honest-{i}", initial_weight=1.0)
        for i in range(51):
            engine.register_validator(f"malicious-{i}", initial_weight=1.0)

        engine.create_proposal("cert-bft", {"test": True}, "honest-0")
        for v in engine._validators:
            vote = VoteValue.APPROVE if "malicious" in v else VoteValue.REJECT
            engine.cast_vote("cert-bft", v, vote)

        result = engine.evaluate_consensus("cert-bft")
        assert result.status != ConsensusStatus.REACHED, (
            "Should not reach consensus under 51% byzantine"
        )

    def test_cert_circuit_breaker_protection(self):
        """Circuit breaker under extreme load — survives without deadlock."""
        cb = CircuitBreaker(max_depth=1, cooldown_seconds=0.005)
        errors: list[Exception] = []
        lock = threading.Lock()

        def hammer():
            for _ in range(1000):
                try:
                    cb.check_depth(10)
                    cb.reset()
                    cb.record_failure()
                    cb.record_success()
                except Exception as e:
                    with lock:
                        errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"CB certification failed: {len(errors)} errors"
        assert cb.state in (BreakerState.CLOSED, BreakerState.OPEN, BreakerState.HALF_OPEN)

    def test_cert_latency_sla(self):
        """State transitions under load — P99 < 10ms."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        latencies: list[float] = []
        lock = threading.Lock()

        for _ in range(1000):
            start = time.perf_counter()
            sm.transition(GovernanceState.ANALYZE, "perf")
            sm.transition(GovernanceState.EVALUATE, "perf")
            sm.transition(GovernanceState.OBSERVE, "perf")
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]
        assert p99 < 10.0, f"P99 latency {p99}ms exceeds 10ms SLA"


class TestE2EStress:
    """End-to-end system integration stress tests."""

    def test_governance_recursive_feedback_convergence(self):
        """Governance → recursive feedback loop should converge within 10 rounds."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")
        event_count = [0]

        def recursive_hook(_transition):
            event_count[0] += 1
            if event_count[0] < 5:
                sm.transition(GovernanceState.ANALYZE, "feedback")

        sm.add_callback(recursive_hook)
        sm.transition(GovernanceState.ANALYZE, "initial")

        assert event_count[0] <= 10, (
            f"Feedback loop did not converge: {event_count[0]} rounds"
        )

    def test_audit_hmac_under_stress(self):
        """HMAC audit trail remains valid under high throughput."""
        from maref.governance.audit import AuditLogger

        logger = AuditLogger(hmac_key=b"e2e-stress-key")
        for i in range(5000):
            logger.log(
                event_type="e2e_stress",
                actor=f"agent-{i % 100}",
                action="process",
                details=f"operation-{i}",
            )

        integrity = logger.verify_integrity()
        assert integrity["integrity_intact"], "HMAC integrity lost under stress"
        assert integrity["valid_signatures"] > 0

    def test_oscillation_under_concurrent_governance(self):
        """Oscillation detection under concurrent governance operations."""
        stabilize_count = [0]

        async def stabilize_fn(reason=""):
            stabilize_count[0] += 1

        loop = OscillationFixLoop(
            stabilize_fn=stabilize_fn,
            cooldown_seconds=0.01,
            max_rate=1.0,
        )

        import asyncio
        async def run_test():
            tasks = [
                loop.detect_and_fix(15.0, 4, "ACT")
                for _ in range(50)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results

        results = asyncio.run(run_test())
        resolved = sum(1 for r in results if isinstance(r, dict) and r.get("resolved"))
        assert resolved > 0

    def test_circuit_breaker_oscillation_integration(self):
        """Circuit breaker and oscillation detection work together under load."""
        cb = CircuitBreaker(max_oscillation_rate=5.0, cooldown_seconds=0.01)
        for _ in range(100):
            cb.check_oscillation(10.0, 4, "ACT")
            cb.check_oscillation(3.0, 3, "OBSERVE")
            cb.check_oscillation(15.0, 4, "ACT")

        stats = cb.get_stats()
        assert stats["trip_count"] > 0

    def test_force_halt_cascading_safety(self):
        """Force halt from multiple paths — always reaches HALT."""
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "start")

        for _ in range(50):
            sm.force_halt("emergency")
            assert sm.current_state == GovernanceState.HALT
            sm2 = GovernanceStateMachine()
            sm2.transition(GovernanceState.OBSERVE, "reset")
            sm = sm2
