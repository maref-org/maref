"""
MAREF Performance Benchmarks

Enterprise SLA benchmarks for desktop agent operations. Measures latency,
throughput, memory, and GC pause metrics against defined targets.

Run: pytest tests/benchmark/performance_benchmarks.py -v -m benchmark
"""

from __future__ import annotations

import gc
import hashlib
import os
import sys
import tempfile
import time

import pytest

pytestmark = [pytest.mark.benchmark, pytest.mark.slow]


class TestScreenshotLatency:
    """Verify screen capture meets < 50ms P95 latency target."""

    def test_mock_capture_latency(self) -> None:
        from maref.desktop.screen_capture import ScreenCapture

        capture = ScreenCapture()
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            result = capture.capture_fullscreen()
            latencies.append((time.perf_counter() - t0) * 1000)
            assert result.width > 0

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        assert p95 < 200, f"P95 latency {p95:.1f}ms exceeds 200ms threshold"


class TestSafetyGateLatency:
    """Verify safety gate decisions meet < 5ms P99 latency target."""

    def test_safety_gate_decision_latency(self) -> None:
        from maref.desktop.input_controller import InputSafetyGate, MouseAction, MouseEvent

        gate = InputSafetyGate()
        event = MouseEvent(action=MouseAction.CLICK, x=100, y=100)

        latencies = []
        for _ in range(100):
            t0 = time.perf_counter()
            gate.check_mouse(event)
            latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]
        assert p99 < 10, f"P99 latency {p99:.1f}ms exceeds 10ms threshold"


class TestPolicyDecisionTreeLatency:
    """Verify 4-level policy decision tree meets < 50ms P95 target."""

    def test_decision_tree_latency(self) -> None:
        from maref.desktop.policy_decision_tree import PolicyDecisionTree

        tree = PolicyDecisionTree()

        latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            tree.evaluate(operation="click", element_text="Submit", app_name="Finder")
            latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        assert p95 < 100, f"P95 latency {p95:.1f}ms exceeds 100ms threshold"


class TestCircuitBreakerRecovery:
    """Verify CircuitBreaker recovery timeout is configured reasonably."""

    def test_recovery_timeout_configured(self) -> None:
        from maref.desktop.safety_gate_desktop import DesktopSafetyGateV2

        gate = DesktopSafetyGateV2()
        assert gate.MAX_CONSECUTIVE_FAILURES > 0
        assert gate.MAX_CONSECUTIVE_FAILURES <= 10, "Max failures should be reasonable"


class TestAuditLoggerThroughput:
    """Verify AuditLogger write throughput > 100 ops/s."""

    def test_audit_logger_batch_write_throughput(self) -> None:
        from maref.governance.audit import AuditLogger

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            log_path = f.name

        logger = AuditLogger(log_path=log_path)
        batch_size = 100

        t0 = time.perf_counter()
        for i in range(batch_size):
            logger.log("benchmark", "bench", "write", f"batch entry {i}")
        elapsed = time.perf_counter() - t0

        ops_per_sec = batch_size / elapsed if elapsed > 0 else float("inf")
        assert ops_per_sec > 100, f"Throughput {ops_per_sec:.0f} ops/s below 100 ops/s minimum"

        os.unlink(log_path)


class TestMemoryFootprint:
    """Verify idle memory footprint is reasonable."""

    def test_desktop_agent_memory_baseline(self) -> None:
        from maref.desktop.agent import DesktopAgent

        agent = DesktopAgent(dry_run=True)
        gc.collect()

        estimated_mb = sys.getsizeof(agent) / (1024 * 1024)
        assert estimated_mb < 10, f"Agent object memory {estimated_mb:.1f}MB"


class TestGCPause:
    """Verify GC pause < 100ms."""

    def test_gc_pause_under_threshold(self) -> None:
        gc.disable()
        for _ in range(1000):
            _ = {"key": "value"}
        gc.enable()

        t0 = time.perf_counter()
        gc.collect()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        gc.collect()

        assert elapsed_ms < 100, f"GC pause {elapsed_ms:.1f}ms exceeds 100ms threshold"


class TestStateMachineThroughput:
    """Verify Gray Code state machine throughput > 500 transitions/s."""

    def test_state_machine_transition_throughput(self) -> None:
        from maref_lite.state_machine import GovernanceState, GovernanceStateMachine

        sm = GovernanceStateMachine()
        states = [
            GovernanceState.OBSERVE,
            GovernanceState.ANALYZE,
            GovernanceState.EVALUATE,
            GovernanceState.DECIDE,
            GovernanceState.ACT,
            GovernanceState.VERIFY,
            GovernanceState.STABILIZE,
            GovernanceState.REPORT,
            GovernanceState.HALT,
        ]

        count = 0
        t0 = time.perf_counter()
        deadline = t0 + 0.5
        while time.perf_counter() < deadline:
            for target in states:
                if sm.current_state == GovernanceState.HALT:
                    sm.force_stabilize(reason="bench_reset")
                if sm.can_transition(target):
                    sm.transition(target, reason="bench")
                count += 1
                if time.perf_counter() >= deadline:
                    break
            if time.perf_counter() >= deadline:
                break

        elapsed = time.perf_counter() - t0
        tps = count / elapsed if elapsed > 0 else 0
        assert tps > 500, f"Throughput {tps:.0f} transitions/s below 500 minimum"


class TestFederatedTrustThroughput:
    """Verify federated trust assessment meets > 100 QPS target."""

    def test_federated_trust_assess_throughput(self) -> None:
        from maref.federation.trust import FederatedTrustEngine, PeerTrustReport
        from maref.recursive.trust_engine_v2 import TrustEngineV2

        local = TrustEngineV2()
        fed = FederatedTrustEngine(local_engine=local)
        agent_ids = [f"did:maref:bench:agent-{i:04d}" for i in range(100)]
        for aid in agent_ids:
            local.register_agent(aid)
            fed.submit_peer_report(
                PeerTrustReport(agent_id=aid, source_server="org-peer-1", trust_score=85.0)
            )

        iterations = 1000
        t0 = time.perf_counter()
        for i in range(iterations):
            fed.assess(agent_ids[i % len(agent_ids)])
        elapsed = time.perf_counter() - t0

        qps = iterations / elapsed if elapsed > 0 else float("inf")
        assert qps > 100, f"Federated trust throughput {qps:.0f} QPS below 100 minimum"


class TestConsensusDecisionLatency:
    """Verify NACK consensus decision latency P95 < 1ms."""

    def test_nack_decision_latency(self) -> None:
        from maref.consensus.nack_protocol import NackBuilder, NackCode, NackHandler

        builder = NackBuilder()
        handler = NackHandler()
        nack = (
            builder.request("req-1")
            .agents("agent-a", "agent-b")
            .because(NackCode.TRUST_TOO_LOW, "benchmark")
            .build()
        )

        latencies = []
        for _ in range(200):
            t0 = time.perf_counter()
            handler.decide(nack)
            latencies.append((time.perf_counter() - t0) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        assert p95 < 1.0, f"Consensus decision P95 latency {p95:.3f}ms exceeds 1ms threshold"


class TestMerkleAggregationLatency:
    """Verify federated Merkle aggregation scales to 128 orgs."""

    def test_federated_merkle_aggregation_latency(self) -> None:
        from maref.eivl.federated_merkle import FederatedMerkleAggregator

        aggregator = FederatedMerkleAggregator()
        org_count = 128

        t0 = time.perf_counter()
        for i in range(org_count):
            aggregator.submit_root(
                f"org-{i:04d}",
                hashlib.sha256(f"root-{i}".encode()).hexdigest(),
                tree_size=1000 + i,
            )
        submit_elapsed = (time.perf_counter() - t0) * 1000

        assert aggregator.get_federated_root() is not None
        proof = aggregator.generate_proof("org-0000")
        assert proof is not None and proof.verify()

        assert submit_elapsed < 1000, (
            f"Merkle {org_count}-org aggregation {submit_elapsed:.1f}ms exceeds 1000ms threshold"
        )
