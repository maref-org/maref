"""
MAREF Compliance Sidecar Performance Benchmarks

Measures sidecar intercept latency and memory usage against targets:
  - Intercept latency: < 5ms P99
  - Memory usage:     < 50MB RSS

Run: pytest tests/benchmark/test_compliance_sidecar_benchmark.py -v -m benchmark
"""

from __future__ import annotations

import os
import time

import pytest

from sidecar.compliance.decision_tree import DecisionTree, PolicyContext
from sidecar.compliance.unified import UnifiedSidecar

pytestmark = [pytest.mark.benchmark, pytest.mark.slow]

DECISION_TREE_LATENCY_TARGET_MS = 1.0
SIDECAR_CHECK_TARGET_MS = 5.0
MEMORY_TARGET_MB = 50

# ── Decision Tree Latency ──────────────────────────────────────


class TestDecisionTreeLatency:
    """Verify 4-level policy decision tree meets < 1ms P99 latency."""

    def test_decision_tree_best_case(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="bench-agent",
            action="read",
            agent_phase="OLD_YANG",
        )
        latencies = []
        for _ in range(1000):
            t0 = time.perf_counter_ns()
            tree.evaluate(ctx)
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]
        p100 = latencies[-1]

        print("\n  Decision tree latency (best case):")
        print(f"    P50:  {p50:.4f}ms")
        print(f"    P99:  {p99:.4f}ms")
        print(f"    Max:  {p100:.4f}ms")

        assert p99 < DECISION_TREE_LATENCY_TARGET_MS, (
            f"P99 {p99:.4f}ms exceeds target {DECISION_TREE_LATENCY_TARGET_MS}ms"
        )

    def test_decision_tree_worst_case(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="bench-agent",
            action="execute",
            action_type="tool_execution",
            data_residency="US",
            model_backend="EU",
            cross_border=False,
            current_entropy=3.5,
            eval_score=30.0,
            has_critical_findings=True,
            agent_phase="OLD_YIN",
        )
        latencies = []
        for _ in range(1000):
            t0 = time.perf_counter_ns()
            tree.evaluate(ctx)
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]
        p100 = latencies[-1]

        print("\n  Decision tree latency (worst case, 6 rules checked):")
        print(f"    P50:  {p50:.4f}ms")
        print(f"    P99:  {p99:.4f}ms")
        print(f"    Max:  {p100:.4f}ms")

        assert p99 < DECISION_TREE_LATENCY_TARGET_MS, (
            f"P99 {p99:.4f}ms exceeds target {DECISION_TREE_LATENCY_TARGET_MS}ms"
        )

    def test_decision_tree_all_decision_levels(self):
        tree = DecisionTree()
        contexts = [
            ("ALLOW", PolicyContext(agent_id="a", action="r", agent_phase="OLD_YANG")),
            ("WARN", PolicyContext(agent_id="a", action="r", data_residency="US", model_backend="EU", cross_border=False, agent_phase="OLD_YANG")),
            ("THROTTLE", PolicyContext(agent_id="a", action="r", current_entropy=3.5, agent_phase="OLD_YANG")),
            ("BLOCK", PolicyContext(agent_id="a", action="r", has_critical_findings=True, agent_phase="OLD_YANG")),
        ]
        for name, ctx in contexts:
            decision = tree.evaluate(ctx)
            print(f"  {name}: level={decision.decision} rule={decision.rule_id}")

    def test_many_agents_concurrent(self):
        """Simulate 100 agents checking actions concurrently."""
        tree = DecisionTree()
        agents = [
            PolicyContext(
                agent_id=f"agent-{i}",
                action=f"action-{i % 10}",
                action_type="tool_execution" if i % 2 == 0 else "read",
                agent_phase="OLD_YANG" if i < 80 else "OLD_YIN",
                has_critical_findings=(i >= 95),
            )
            for i in range(100)
        ]
        latencies = []
        for ctx in agents:
            t0 = time.perf_counter_ns()
            tree.evaluate(ctx)
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]
        total = sum(latencies)

        print("\n  100 agents, 100 checks:")
        print(f"    Total: {total:.2f}ms")
        print(f"    Avg:   {total/100:.4f}ms")
        print(f"    P99:   {p99:.4f}ms")
        print(f"    Throughput: {100/(total/1000):.0f} checks/sec")

        assert total < 100, f"Total latency {total:.2f}ms exceeds 100ms for 100 agents"


# ── UnifiedSidecar Latency ─────────────────────────────────────


class TestUnifiedSidecarLatency:
    """Verify UnifiedSidecar.check_action meets < 5ms P99 target."""

    def test_sidecar_check_action_allow(self):
        sc = UnifiedSidecar(agent_id="bench", phase="OLD_YANG")
        latencies = []
        for _ in range(500):
            t0 = time.perf_counter_ns()
            sc.check_action("read", "tool_execution")
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\n  Sidecar check_action (ALLOW):")
        print(f"    P50:  {p50:.3f}ms")
        print(f"    P99:  {p99:.3f}ms")

        assert p99 < SIDECAR_CHECK_TARGET_MS, (
            f"P99 {p99:.3f}ms exceeds target {SIDECAR_CHECK_TARGET_MS}ms"
        )

    def test_sidecar_check_action_block(self):
        sc = UnifiedSidecar(agent_id="bench", phase="OLD_YIN")
        latencies = []
        for _ in range(500):
            t0 = time.perf_counter_ns()
            sc.check_action("execute", "tool_execution")
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\n  Sidecar check_action (BLOCK):")
        print(f"    P99:  {p99:.3f}ms")

        assert p99 < SIDECAR_CHECK_TARGET_MS, (
            f"P99 {p99:.3f}ms exceeds target {SIDECAR_CHECK_TARGET_MS}ms"
        )

    def test_sidecar_concurrent_checks(self):
        instances = [UnifiedSidecar(agent_id=f"a{i}", phase="OLD_YANG") for i in range(50)]
        latencies = []
        for sc in instances:
            t0 = time.perf_counter_ns()
            sc.check_action("read", "tool_execution")
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)
            sc.check_action("write", "self_modify")
            latencies.append((time.perf_counter_ns() - t0) / 1_000_000)

        latencies.sort()
        p99 = latencies[int(len(latencies) * 0.99)]
        throughput = len(latencies) / (sum(latencies) / 1000)

        print("\n  50 sidecar instances, 100 checks:")
        print(f"    P99:        {p99:.3f}ms")
        print(f"    Throughput: {throughput:.0f} checks/sec")
        print(f"    Total:      {sum(latencies):.1f}ms")

        assert throughput > 1000, f"Throughput {throughput:.0f} checks/sec below 1000 target"


# ── Memory Usage ───────────────────────────────────────────────


class TestMemoryUsage:
    """Verify sidecar memory stays under 50MB target."""

    def get_rss_mb(self) -> float:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

    def test_sidecar_single_instance_memory(self):
        rss_before = self.get_rss_mb()
        sc = UnifiedSidecar(agent_id="mem-bench", phase="OLD_YANG")
        for _ in range(1000):
            sc.check_action("read", "tool_execution")
        rss_after = self.get_rss_mb()
        delta = rss_after - rss_before
        print("\n  Memory (1 instance, 1000 checks):")
        print(f"    RSS before: {rss_before:.1f}MB")
        print(f"    RSS after:  {rss_after:.1f}MB")
        print(f"    Delta:      {delta:.1f}MB")
        assert delta < MEMORY_TARGET_MB, (
            f"Memory delta {delta:.1f}MB exceeds target {MEMORY_TARGET_MB}MB"
        )

    def test_sidecar_many_instances(self):
        rss_before = self.get_rss_mb()
        instances = [
            UnifiedSidecar(agent_id=f"mem-{i}", phase="OLD_YANG")
            for i in range(100)
        ]
        for sc in instances:
            sc.check_action("read", "tool_execution")
        rss_after = self.get_rss_mb()
        delta = rss_after - rss_before
        per_instance = delta / 100
        print("\n  Memory (100 instances, 100 checks):")
        print(f"    RSS before:     {rss_before:.1f}MB")
        print(f"    RSS after:      {rss_after:.1f}MB")
        print(f"    Delta:          {delta:.1f}MB")
        print(f"    Per instance:   {per_instance:.3f}MB")
        assert delta < MEMORY_TARGET_MB, (
            f"Memory delta {delta:.1f}MB exceeds target {MEMORY_TARGET_MB}MB for 100 instances"
        )

    def test_audit_log_memory(self):
        import sys
        sc = UnifiedSidecar(agent_id="mem", phase="OLD_YANG")
        sizes_before = sys.getsizeof(sc._audit_log)
        for i in range(10000):
            sc.check_action(f"action-{i}", "tool_execution")
        sizes_after = sys.getsizeof(sc._audit_log)
        print("\n  Audit log (10000 entries):")
        print(f"    Object size: {sizes_after / 1024:.1f}KB")
        assert sizes_after < 1024 * 1024, (
            f"Audit log {sizes_after} bytes exceeds 1MB for 10000 entries"
        )


# ── Deterministic Decision Verification ────────────────────────


class TestDeterministicDecisions:
    """Verify decision tree is deterministic: same input → same output."""

    def test_deterministic_same_ctx(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="det",
            action="execute",
            action_type="tool_execution",
            has_critical_findings=True,
            agent_phase="OLD_YANG",
        )
        results = [tree.evaluate(ctx).decision for _ in range(100)]
        assert all(d == results[0] for d in results), "Decision tree not deterministic!"

    def test_deterministic_warn_cross_border(self):
        tree = DecisionTree()
        ctx = PolicyContext(
            agent_id="det",
            action="store",
            data_residency="US",
            model_backend="EU",
            cross_border=False,
            agent_phase="OLD_YANG",
        )
        results = [tree.evaluate(ctx).decision for _ in range(100)]
        assert all(d == results[0] for d in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "benchmark"])
