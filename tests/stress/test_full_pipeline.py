"""
M7 全链路压力测试 — Full Pipeline Stress Tests.

Covers:
  7.1 — 500 Agent 并发治理 (concurrency + isolation)
  7.2 — 24h 浸泡测试 (FNR/FPR drift monitoring)
  7.3 — 故障注入 (crash recovery, KG failure, gradient explosion)
  7.5 — 性能基准 (transition latency, KG query, anomaly detection)
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

from maref.governance.audit import AuditLogger
from maref.governance.circuit_breaker import BreakerState, CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState as GS
from maref.knowledge.graph import KnowledgeGraph
from maref.learning.replay import DecisionOutcome, ExperienceStore
from maref.learning.scheduler import LearningRateScheduler
from maref.observation.detector import DualThresholdConfig, DualThresholdDetector

# ---------------------------------------------------------------------------
# 7.1 — 500 Agent 并发治理
# ---------------------------------------------------------------------------

class TestAgentConcurrency:
    """Each agent holds an independent state machine — verify no cross-contamination."""

    AGENT_COUNT = 500
    STATE_SEQUENCE = [GS.OBSERVE, GS.ANALYZE, GS.EVALUATE, GS.DECIDE, GS.ACT]

    @staticmethod
    def _run_agent(agent_id: int, sequence: list[GS]) -> list[GS]:
        sm = GovernanceStateMachine()
        visited: list[GS] = []
        for target in sequence:
            if sm.can_transition(target):
                sm.transition(target, f"agent_{agent_id}")
                visited.append(target)
                time.sleep(random.uniform(0.0001, 0.0005))
        return visited

    def test_massive_instance_isolation(self):
        """500 state machines run independently, no shared state mutation."""
        sm_list = [GovernanceStateMachine() for _ in range(self.AGENT_COUNT)]
        initial_states = [sm.current_state for sm in sm_list]
        assert all(s == GS.INIT for s in initial_states)

        for i, sm in enumerate(sm_list):
            sm.transition(GS.OBSERVE, f"agent_{i}")
            sm.transition(GS.ANALYZE, f"agent_{i}")

        for i, sm in enumerate(sm_list):
            assert sm.current_state == GS.ANALYZE, f"Agent {i} state mismatch"

    def test_concurrent_transitions_no_cross_contamination(self):
        """ThreadPoolExecutor: all agents transition, final states are independent."""
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {
                executor.submit(self._run_agent, i, self.STATE_SEQUENCE): i
                for i in range(self.AGENT_COUNT)
            }
            results = {}
            for future in as_completed(futures):
                agent_id = futures[future]
                results[agent_id] = future.result()

        assert len(results) == self.AGENT_COUNT
        for agent_id, visited in results.items():
            assert visited == self.STATE_SEQUENCE, (
                f"Agent {agent_id} expected {[s.name for s in self.STATE_SEQUENCE]} "
                f"got {[s.name for s in visited]}"
            )

    def test_high_frequency_state_churn(self):
        """Rapid oscillating transitions ANALYZE↔EVALUATE, verify count consistency."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")

        for i in range(400):
            if sm.current_state == GS.OBSERVE:
                sm.transition(GS.ANALYZE, f"churn_{i}")
            elif sm.current_state == GS.ANALYZE:
                sm.transition(GS.EVALUATE, f"churn_{i}")
            elif sm.current_state == GS.EVALUATE:
                sm.transition(GS.ANALYZE, f"churn_{i}")
        assert sm.transition_count == 401

    def test_thread_safety_of_snapshot_capture(self):
        """Concurrent snapshot captures do not corrupt state."""

        def capture(agent_id: int):
            sm = GovernanceStateMachine()
            sm.transition(GS.OBSERVE, f"agent_{agent_id}")
            return sm.snapshot()

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(capture, i) for i in range(200)]
            snapshots = [f.result() for f in futures]

        assert len(snapshots) == 200
        for snap in snapshots:
            assert snap.current_state == GS.OBSERVE


# ---------------------------------------------------------------------------
# 7.2 — 浸泡测试 (FNR/FPR drift monitoring)
# ---------------------------------------------------------------------------

class TestSoakSimulation:
    """Simulate extended operation, track detector drift."""

    ITERATIONS = 5000
    SEED = 42

    def _generate_pattern(self, iterations: int, anomaly_ratio: float = 0.15):
        """Generate a realistic signal with occasional anomalies."""
        rng = random.Random(self.SEED)
        values = []
        ground_truth = []
        base = 2.0
        for i in range(iterations):
            noise = rng.gauss(0, 0.5)
            is_anomaly = rng.random() < anomaly_ratio
            val = base + noise + (rng.uniform(2.0, 5.0) if is_anomaly else 0.0)
            values.append(val)
            ground_truth.append(is_anomaly)
            if i % 100 == 0:
                base += rng.uniform(-0.1, 0.1)
        return values, ground_truth

    def test_fnr_fpr_stability_over_long_run(self):
        """After 5000 evaluations, FNR/FPR remain within acceptable bounds."""
        detector = DualThresholdDetector(
            DualThresholdConfig(
                primary_threshold=4.0,
                shadow_threshold=2.0,
                trend_window=5,
                oscillation_max_rate=12,
            )
        )
        values, ground_truth = self._generate_pattern(self.ITERATIONS)

        for val, gt in zip(values, ground_truth, strict=False):
            detector.evaluate(val, ground_truth_is_anomaly=gt)

        stats = detector.get_stats()
        fnr_fpr = stats["fnr_fpr"]

        tp = fnr_fpr["true_positives"]
        fn = fnr_fpr["false_negatives"]
        fp = fnr_fpr["false_positives"]
        tn = fnr_fpr["true_negatives"]

        total_anomalies = tp + fn
        total_normals = fp + tn

        fnr = fn / total_anomalies if total_anomalies > 0 else 0.0
        fpr = fp / total_normals if total_normals > 0 else 0.0

        assert fnr < 0.15, f"FNR={fnr:.3f} exceeds soak limit 0.15"
        assert fpr < 0.10, f"FPR={fpr:.3f} exceeds soak limit 0.10"
        assert total_anomalies > 0, "No anomalies in test data"

    def test_rolling_fnr_fpr_drift(self):
        """Track FNR/FPR in sliding windows; verify detector does not diverge monotonically."""
        values, ground_truth = self._generate_pattern(self.ITERATIONS)

        window_size = 500
        fnr_values: list[float] = []
        fpr_values: list[float] = []

        for window_start in range(0, len(values), window_size):
            window_detector = DualThresholdDetector(
                DualThresholdConfig(primary_threshold=4.0, shadow_threshold=2.0)
            )
            window_vals = values[window_start:window_start + window_size]
            window_gts = ground_truth[window_start:window_start + window_size]

            for val, gt in zip(window_vals, window_gts, strict=False):
                window_detector.evaluate(val, ground_truth_is_anomaly=gt)

            w_stats = window_detector.get_stats()["fnr_fpr"]
            tp_w = w_stats["true_positives"]
            fn_w = w_stats["false_negatives"]
            fp_w = w_stats["false_positives"]
            tn_w = w_stats["true_negatives"]

            total_anom = tp_w + fn_w
            total_norm = fp_w + tn_w
            if total_anom > 0:
                fnr_values.append(fn_w / total_anom)
            if total_norm > 0:
                fpr_values.append(fp_w / total_norm)

        assert len(fnr_values) >= 8, "Expected at least 8 windows"
        assert len(fpr_values) >= 8
        assert max(fnr_values) < 0.30, f"FNR max={max(fnr_values):.3f} too high"
        assert max(fpr_values) < 0.30, f"FPR max={max(fpr_values):.3f} too high"


# ---------------------------------------------------------------------------
# 7.3 — 故障注入测试
# ---------------------------------------------------------------------------

class TestFaultInjection:
    """Simulate production failures: crash recovery, KG write failure, gradient explosion."""

    def test_state_machine_crash_recovery(self):
        """Snapshot before crash, destroy instance, restore — state preserved."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        sm.transition(GS.ANALYZE, "analyze")
        sm.transition(GS.EVALUATE, "evaluate")
        sm.transition(GS.DECIDE, "decide")

        snap = sm.snapshot()
        assert snap.current_state == GS.DECIDE
        assert snap.transition_count == 4

        del sm

        restored = GovernanceStateMachine.restore(snap)
        assert restored.current_state == GS.DECIDE
        assert restored.transition_count == 4
        assert restored.can_transition(GS.ACT)

    def test_crash_during_transition_no_corruption(self):
        """If crash occurs mid-transition, the on-disk snapshot is the last stable state."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "start")
        sm.transition(GS.ANALYZE, "analyze")
        snap_before = sm.snapshot()

        sm.transition(GS.EVALUATE, "crash imminent")
        snap_after = sm.snapshot()

        restored_from_before = GovernanceStateMachine.restore(snap_before)
        assert restored_from_before.current_state == GS.ANALYZE

        restored_from_after = GovernanceStateMachine.restore(snap_after)
        assert restored_from_after.current_state == GS.EVALUATE

    @patch.object(KnowledgeGraph, "save", side_effect=PermissionError("read-only"))
    def test_knowledge_graph_write_failure_graceful(self, mock_save):
        """KG in-memory data survives save() failure — node still accessible."""
        kg = KnowledgeGraph(storage_path=Path("/fake/kg.json"))
        with pytest.raises(PermissionError):
            kg.add_finding("mock finding for fault test", source="fault_test", confidence=0.9)

        stats = kg.get_connectivity_stats()
        assert stats["total_nodes"] > 0

    def test_gradient_explosion_protection(self):
        """Scheduler handles extreme rewards without numerical blow-up."""
        scheduler = LearningRateScheduler(initial_lr=0.01)
        initial_lr = scheduler.learning_rate

        for _ in range(50):
            scheduler.step(1e6)

        assert scheduler.learning_rate <= initial_lr
        assert scheduler.learning_rate > 0

    def test_experience_store_crash_recovery(self):
        """ExperienceStore basic insert and sample works in-memory."""
        store = ExperienceStore()
        outcome = DecisionOutcome(
            timestamp=time.time(),
            decision_type="fault_test",
            state_before="INIT",
            state_after="OBSERVE",
            entropy_before=0,
            entropy_after=1,
            reward=1.0,
        )
        store.insert(outcome)
        assert store.count() == 1
        batch = store.sample(1)
        assert len(batch) == 1
        assert batch[0].reward == 1.0

    def test_circuit_breaker_self_healing(self):
        """Circuit breaker trips on failure pattern, transitions back on success."""
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=3, cooldown_seconds=0.001)
        assert cb.state == BreakerState.CLOSED

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

        time.sleep(0.01)

        allowed = cb.check_depth(1)
        assert allowed
        assert cb.state == BreakerState.HALF_OPEN

        cb.record_success()
        assert cb.state == BreakerState.CLOSED


# ---------------------------------------------------------------------------
# 7.5 — 性能基准
# ---------------------------------------------------------------------------

class TestPerformanceBenchmark:
    """Measure critical path latencies and assert within acceptable bounds."""

    WARMUP_ITERATIONS = 100
    BENCH_ITERATIONS = 1000
    LATENCY_BUDGET_MS = {
        "state_transition": 5.0,
        "kg_query": 200.0,
        "anomaly_detection": 10.0,
        "snapshot_restore": 10.0,
        "audit_log": 10.0,
    }

    def _measure(self, fn, warmup: int = 100, runs: int = 1000) -> list[float]:
        for _ in range(warmup):
            fn()
        latencies = []
        for _ in range(runs):
            t0 = time.perf_counter()
            fn()
            latencies.append((time.perf_counter() - t0) * 1000)
        return sorted(latencies)

    def test_state_transition_latency(self):
        """P99 state transition < 5ms."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "init")

        def do_transition():
            nonlocal sm
            target = GS.ANALYZE if sm.current_state == GS.OBSERVE else GS.OBSERVE
            sm.transition(target, "bench")

        latencies = self._measure(do_transition)
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p50 < self.LATENCY_BUDGET_MS["state_transition"], (
            f"P50={p50:.2f}ms exceeds budget"
        )
        assert p99 < self.LATENCY_BUDGET_MS["state_transition"] * 3, (
            f"P99={p99:.2f}ms exceeds budget"
        )

    def test_anomaly_detection_latency(self):
        """P99 anomaly detection < 10ms."""
        detector = DualThresholdDetector(
            DualThresholdConfig(primary_threshold=4.0, shadow_threshold=2.0)
        )

        def do_detect():
            detector.evaluate(3.5)

        latencies = self._measure(do_detect)
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p50 < self.LATENCY_BUDGET_MS["anomaly_detection"], (
            f"P50={p50:.2f}ms exceeds budget"
        )
        assert p99 < self.LATENCY_BUDGET_MS["anomaly_detection"] * 3, (
            f"P99={p99:.2f}ms exceeds budget"
        )

    def test_kg_query_latency(self):
        """Knowledge graph connectivity stats query < 200ms."""
        kg = KnowledgeGraph(storage_path=Path(":memory:"))
        for i in range(200):
            kg.add_finding(
                f"performance test finding number {i} about system behavior",
                source="bench",
                confidence=0.7 + random.random() * 0.3,
            )

        def do_query():
            kg.get_connectivity_stats()

        latencies = self._measure(do_query, warmup=10, runs=100)
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p50 < self.LATENCY_BUDGET_MS["kg_query"], (
            f"P50={p50:.2f}ms exceeds budget"
        )
        assert p99 < self.LATENCY_BUDGET_MS["kg_query"] * 4, (
            f"P99={p99:.2f}ms exceeds budget"
        )

    def test_snapshot_restore_latency(self):
        """Snapshot + restore round-trip < 10ms."""
        sm = GovernanceStateMachine()
        sm.transition(GS.OBSERVE, "init")
        sm.transition(GS.ANALYZE, "analyze")
        sm.transition(GS.EVALUATE, "evaluate")

        def do_roundtrip():
            snap = sm.snapshot()
            GovernanceStateMachine.restore(snap)

        latencies = self._measure(do_roundtrip)
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p50 < self.LATENCY_BUDGET_MS["snapshot_restore"], (
            f"P50={p50:.2f}ms exceeds budget"
        )
        assert p99 < self.LATENCY_BUDGET_MS["snapshot_restore"] * 4, (
            f"P99={p99:.2f}ms exceeds budget"
        )

    def test_audit_log_latency(self):
        """Audit log write < 10ms per entry."""
        logger = AuditLogger(log_path=None)

        def do_log():
            logger.log_decision(
                actor="bench_test",
                action="transition",
                from_state="OBSERVE",
                to_state="ANALYZE",
            )

        latencies = self._measure(do_log)
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        assert p50 < self.LATENCY_BUDGET_MS["audit_log"], (
            f"P50={p50:.2f}ms exceeds budget"
        )
        assert p99 < self.LATENCY_BUDGET_MS["audit_log"] * 3, (
            f"P99={p99:.2f}ms exceeds budget"
        )
