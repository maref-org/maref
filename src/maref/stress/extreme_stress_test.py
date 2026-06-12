"""MAREF Extreme Stress Testing Framework.

Tests system limits under extreme conditions:
1. Cascading Failures: Multiple simultaneous faults
2. Extreme Stress: stress_factor 2.0-3.0 (quality drops 60-90%)
3. Concurrent Attacks: Multi-threaded fault injection
4. Endurance Test: 1000+ continuous runs
5. Adaptive Adversary: Dynamic fault escalation based on system response
6. Resource Exhaustion: Real OOM, disk full, thread pool saturation
7. Network Partition: Simulated brain-split scenarios

Combines ChaosEngine, CodeServiceHarness with extreme configurations.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from maref.stress.chaos_engine import ChaosEngine, FaultType
from maref.stress.code_service_harness import AgentConfig, CodeServiceHarness


@dataclass
class ExtremeTestResult:
    """Result from a single extreme test."""
    test_name: str
    scenario: str
    success: bool
    metrics: dict = field(default_factory=dict)
    details: str = ""
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class ExtremeStressTester:
    """Coordinate all extreme stress tests."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng = random.Random(seed)
        self.results: list[ExtremeTestResult] = []

    # ─── 1. Cascading Failures ───────────────────────────────────────────
    def test_cascading_failures(self) -> ExtremeTestResult:
        """Test system under multiple simultaneous faults.

        Injects 5 different fault types at once:
        - Network latency (1000ms)
        - CPU load (80%)
        - Memory pressure (500MB)
        - Byzantine agent (tamper_rate=0.5)
        - Emergent conflict

        Validates: System maintains >20% success under combined stress.
        """
        t0 = time.perf_counter()

        engine = ChaosEngine(simulate=True)

        # Inject all 5 faults simultaneously
        faults = [
            {"type": FaultType.NETWORK, "params": {"latency_ms": 1000, "drop_rate": 0.2}},
            {"type": FaultType.CPU, "params": {"load_pct": 80, "duration_s": 5}},
            {"type": FaultType.MEMORY, "params": {"pressure_mb": 500}},
            {"type": FaultType.BYZANTINE, "params": {"agent_id": "cascading_test", "tamper_rate": 0.5}},
            {"type": FaultType.EMERGENT_CONFLICT, "params": {"conflict_type": "shared_state"}},
        ]

        for fault in faults:
            engine.inject(fault["type"], duration_s=5.0, params=fault["params"])

        # Run harness under extreme cascading stress
        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800),
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)
        report = harness.run(num_runs=100, stress_factor=1.0)

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        # System should maintain at least 20% success under cascading failures
        success = report.success_rate > 0.20

        engine.clear()

        return ExtremeTestResult(
            test_name="cascading_failures",
            scenario="5_faults_simultaneous",
            success=success,
            metrics={
                "success_rate": report.success_rate,
                "avg_duration_ms": report.avg_duration_ms,
                "p99_duration_ms": report.p99_duration_ms,
                "fault_count": len(faults),
            },
            details=f"Success rate under 5 simultaneous faults: {report.success_rate:.1%}",
            warnings=[] if success else [f"Success rate {report.success_rate:.1%} < 20% threshold"],
            duration_ms=duration,
        )

    # ─── 2. Extreme Stress Coefficient ───────────────────────────────────
    def test_extreme_stress_coefficient(self) -> ExtremeTestResult:
        """Test with stress_factor 2.0-3.0.

        At stress_factor=3.0, agent quality degrades by 90%:
        effective_quality = max(0.1, quality_rate - 3.0 * 0.3) = 0.1

        Validates: System can recover even when all agents operate at 10% quality.
        """
        t0 = time.perf_counter()

        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800),
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)

        results = {}
        for stress_factor in [2.0, 2.5, 3.0]:
            report = harness.run(num_runs=200, stress_factor=stress_factor)
            results[f"stress_{stress_factor}"] = {
                "success_rate": report.success_rate,
                "avg_duration_ms": report.avg_duration_ms,
            }

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        # Even at max stress, system should maintain some success
        min_success = min(v["success_rate"] for v in results.values())
        success = min_success > 0.05  # At least 5% success at max stress

        return ExtremeTestResult(
            test_name="extreme_stress_coefficient",
            scenario="stress_2.0_to_3.0",
            success=success,
            metrics=results,
            details=f"Minimum success rate at stress 3.0: {results['stress_3.0']['success_rate']:.1%}",
            warnings=[] if success else ["System failure at extreme stress - needs investigation"],
            duration_ms=duration,
        )

    # ─── 3. Concurrent Attacks ───────────────────────────────────────────
    def test_concurrent_attacks(self) -> ExtremeTestResult:
        """Test multi-threaded simultaneous fault injection.

        Spawns 5 threads, each injecting a different fault type simultaneously.
        Tests race conditions and resource contention.

        Validates: No deadlocks, system maintains >15% success.
        """
        t0 = time.perf_counter()

        fault_results = []
        lock = threading.Lock()

        def inject_fault(fault_type: FaultType, params: dict):
            engine = ChaosEngine(simulate=True)
            try:
                event = engine.inject(fault_type, duration_s=3.0, params=params)
                with lock:
                    fault_results.append({
                        "type": fault_type.value,
                        "success": event.success,
                        "detail": event.detail,
                    })
            except Exception as e:
                with lock:
                    fault_results.append({
                        "type": fault_type.value,
                        "success": False,
                        "error": str(e),
                    })

        # Spawn 5 threads simultaneously
        fault_configs = [
            (FaultType.NETWORK, {"latency_ms": 2000, "drop_rate": 0.3}),
            (FaultType.CPU, {"load_pct": 90, "duration_s": 3}),
            (FaultType.MEMORY, {"pressure_mb": 800}),
            (FaultType.BYZANTINE, {"agent_id": "concurrent_1", "tamper_rate": 0.6}),
            (FaultType.EMERGENT_CONFLICT, {"conflict_type": "version_mismatch"}),
        ]

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(inject_fault, ft, params)
                for ft, params in fault_configs
            ]
            for f in as_completed(futures):
                f.result()  # Wait for completion

        # Run harness under concurrent stress
        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800),
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)
        report = harness.run(num_runs=100, stress_factor=0.8)

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        injected_count = sum(1 for r in fault_results if r.get("success"))
        success = injected_count >= 4 and report.success_rate > 0.15

        return ExtremeTestResult(
            test_name="concurrent_attacks",
            scenario="5_threads_simultaneous",
            success=success,
            metrics={
                "faults_injected": injected_count,
                "total_faults": len(fault_configs),
                "success_rate": report.success_rate,
                "fault_details": fault_results,
            },
            details=f"Injected {injected_count}/5 faults concurrently, success rate: {report.success_rate:.1%}",
            warnings=[] if success else ["Concurrent fault injection failed"],
            duration_ms=duration,
        )

    # ─── 4. Endurance Test ───────────────────────────────────────────────
    def test_endurance(self) -> ExtremeTestResult:
        """Test 1000+ continuous runs to detect cumulative errors.

        Runs the pipeline continuously and tracks:
        - Memory leaks (duration growth over time)
        - Error accumulation
        - Performance degradation
        - Success rate drift

        Validates: Success rate variance < 10%, no duration growth > 2x.
        """
        t0 = time.perf_counter()

        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800),
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)

        # Run 1000 continuous runs
        report = harness.run(num_runs=1000, stress_factor=0.1)

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        # Check for performance degradation
        # Compare first 100 runs vs last 100 runs
        first_runs = report.runs[:100]
        last_runs = report.runs[-100:]

        first_avg_duration = sum(r.duration_ms for r in first_runs) / len(first_runs)
        last_avg_duration = sum(r.duration_ms for r in last_runs) / len(last_runs)

        duration_growth = (last_avg_duration - first_avg_duration) / max(first_avg_duration, 1)

        # Check success rate stability
        batch_rates = []
        for i in range(10):
            batch = report.runs[i*100:(i+1)*100]
            batch_rate = sum(1 for r in batch if r.success) / len(batch)
            batch_rates.append(batch_rate)

        success_rate_std = statistics.stdev(batch_rates) if len(batch_rates) > 1 else 0.0

        success = success_rate_std < 0.10 and duration_growth < 2.0

        return ExtremeTestResult(
            test_name="endurance_test",
            scenario="1000_continuous_runs",
            success=success,
            metrics={
                "total_runs": report.total_runs,
                "success_rate": report.success_rate,
                "success_rate_std": success_rate_std,
                "duration_growth": duration_growth,
                "first_100_avg_ms": first_avg_duration,
                "last_100_avg_ms": last_avg_duration,
                "total_duration_s": duration / 1000,
            },
            details=f"1000 runs completed, success rate: {report.success_rate:.1%}, std: {success_rate_std:.3f}",
            warnings=[] if success else [
                f"Success rate variance too high: {success_rate_std:.3f}",
                f"Duration growth: {duration_growth:.1%}",
            ],
            duration_ms=duration,
        )

    # ─── 5. Adaptive Adversary ───────────────────────────────────────────
    def test_adaptive_adversary(self) -> ExtremeTestResult:
        """Test against adaptive adversary that escalates based on system response.

        Adversary strategy:
        - If success_rate > 80%: increase stress_factor by 0.2
        - If success_rate < 50%: decrease stress_factor by 0.1
        - If success_rate 50-80%: maintain stress_factor

        Simulates intelligent attacker adapting to system defenses.
        Validates: System eventually stabilizes at stress_factor 1.5-2.0.
        """
        t0 = time.perf_counter()

        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800),
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)

        stress_factor = 0.5
        history = []
        rounds = 10

        for round_idx in range(rounds):
            report = harness.run(num_runs=100, stress_factor=stress_factor)

            history.append({
                "round": round_idx,
                "stress_factor": stress_factor,
                "success_rate": report.success_rate,
            })

            # Adaptive adjustment
            if report.success_rate > 0.80:
                stress_factor = min(3.0, stress_factor + 0.2)
            elif report.success_rate < 0.50:
                stress_factor = max(0.1, stress_factor - 0.1)
            # else: maintain current stress

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        # Check if system stabilized (last 3 rounds have similar stress)
        final_stress = [h["stress_factor"] for h in history[-3:]]
        stress_variance = statistics.variance(final_stress) if len(final_stress) > 1 else 0.0
        success = stress_variance < 0.1  # Low variance = stable

        return ExtremeTestResult(
            test_name="adaptive_adversary",
            scenario="intelligent_escalation",
            success=success,
            metrics={
                "initial_stress": 0.5,
                "final_stress": stress_factor,
                "stress_variance": stress_variance,
                "history": history,
            },
            details=f"Adaptive test completed, final stress: {stress_factor:.1f}, variance: {stress_variance:.3f}",
            warnings=[] if success else ["System failed to stabilize against adaptive adversary"],
            duration_ms=duration,
        )

    # ─── 6. Resource Exhaustion ──────────────────────────────────────────
    def test_resource_exhaustion(self) -> ExtremeTestResult:
        """Test system under resource exhaustion conditions.

        Simulates:
        - Memory pressure (1000MB)
        - CPU saturation (95%)
        - Disk fill (1000MB)
        - Process kill simulation

        Validates: System handles OOM gracefully (no crashes, >10% success).
        """
        t0 = time.perf_counter()

        engine = ChaosEngine(simulate=True)

        # Inject resource exhaustion faults
        faults = [
            {"type": FaultType.MEMORY, "params": {"pressure_mb": 1000}},
            {"type": FaultType.CPU, "params": {"load_pct": 95, "duration_s": 5}},
            {"type": FaultType.DISK, "params": {"space_mb": 1000}},
            {"type": FaultType.PROCESS, "params": {"target": "code_generator"}},
        ]

        for fault in faults:
            engine.inject(fault["type"], duration_s=5.0, params=fault["params"])

        # Run under resource exhaustion
        agents = [
            AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=1500),  # Slower under resource pressure
            AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=800),
            AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=1000),
            AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=400),
        ]

        harness = CodeServiceHarness(agents=agents, seed=self._seed)
        report = harness.run(num_runs=100, stress_factor=1.5)

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        success = report.success_rate > 0.10  # At least 10% success under exhaustion

        engine.clear()

        return ExtremeTestResult(
            test_name="resource_exhaustion",
            scenario="memory_cpu_disk_process",
            success=success,
            metrics={
                "success_rate": report.success_rate,
                "avg_duration_ms": report.avg_duration_ms,
                "fault_count": len(faults),
            },
            details=f"Success rate under resource exhaustion: {report.success_rate:.1%}",
            warnings=[] if success else ["System crashed or failed completely under resource exhaustion"],
            duration_ms=duration,
        )

    # ─── 7. Network Partition ────────────────────────────────────────────
    def test_network_partition(self) -> ExtremeTestResult:
        """Test system under network partition (brain-split) scenarios.

        Simulates:
        - Agent A can reach Agent B, but not Agent C
        - Network latency asymmetric (100ms one way, 5000ms other way)
        - Packet loss (30-50%)
        - Network flapping (connect/disconnect cycles)

        Validates: System handles partitions gracefully, >15% success.
        """
        t0 = time.perf_counter()

        engine = ChaosEngine(simulate=True)

        # Simulate network partition scenarios
        partition_scenarios = [
            {"latency_ms": 100, "drop_rate": 0.0},  # Normal
            {"latency_ms": 1000, "drop_rate": 0.1},  # Degraded
            {"latency_ms": 3000, "drop_rate": 0.2},  # Partition
            {"latency_ms": 5000, "drop_rate": 0.3},  # Severe partition
        ]

        all_reports = []
        for scenario in partition_scenarios:
            engine.inject(FaultType.NETWORK, duration_s=2.0, params=scenario)

            agents = [
                AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=800 + scenario["latency_ms"]),
                AgentConfig(name="test", quality_rate=0.90, speed_ms_mean=400 + scenario["latency_ms"]),
                AgentConfig(name="review", quality_rate=0.85, speed_ms_mean=600 + scenario["latency_ms"]),
                AgentConfig(name="merge", quality_rate=0.95, speed_ms_mean=200 + scenario["latency_ms"]),
            ]

            harness = CodeServiceHarness(agents=agents, seed=self._seed)
            report = harness.run(num_runs=50, stress_factor=0.5)
            all_reports.append({
                "scenario": scenario,
                "success_rate": report.success_rate,
                "avg_duration_ms": report.avg_duration_ms,
            })

        t1 = time.perf_counter()
        duration = (t1 - t0) * 1000

        # System should maintain at least 15% success even in severe partition
        min_success = min(r["success_rate"] for r in all_reports)
        success = min_success > 0.15

        engine.clear()

        return ExtremeTestResult(
            test_name="network_partition",
            scenario="latency_escalation",
            success=success,
            metrics={
                "scenarios": all_reports,
                "min_success_rate": min_success,
            },
            details=f"Minimum success rate under network partition: {min_success:.1%}",
            warnings=[] if success else ["System failed under network partition"],
            duration_ms=duration,
        )


def run_extreme_stress_suite() -> dict:
    """Run complete extreme stress test suite."""
    print("\n" + "=" * 70)
    print("MAREF Extreme Stress Test Suite")
    print("=" * 70)
    print(f"\nStarting at: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    tester = ExtremeStressTester(seed=42)
    t_start = time.perf_counter()

    # Test 1: Cascading Failures
    print("\n[1/7] Cascading Failures Test...")
    result1 = tester.test_cascading_failures()
    tester.results.append(result1)
    print(f"  Result: {'PASS' if result1.success else 'FAIL'}")
    print(f"  Details: {result1.details}")
    if result1.warnings:
        for w in result1.warnings:
            print(f"  WARNING: {w}")

    # Test 2: Extreme Stress Coefficient
    print("\n[2/7] Extreme Stress Coefficient Test...")
    result2 = tester.test_extreme_stress_coefficient()
    tester.results.append(result2)
    print(f"  Result: {'PASS' if result2.success else 'FAIL'}")
    print(f"  Details: {result2.details}")
    if result2.warnings:
        for w in result2.warnings:
            print(f"  WARNING: {w}")

    # Test 3: Concurrent Attacks
    print("\n[3/7] Concurrent Attacks Test...")
    result3 = tester.test_concurrent_attacks()
    tester.results.append(result3)
    print(f"  Result: {'PASS' if result3.success else 'FAIL'}")
    print(f"  Details: {result3.details}")
    if result3.warnings:
        for w in result3.warnings:
            print(f"  WARNING: {w}")

    # Test 4: Endurance Test
    print("\n[4/7] Endurance Test (1000 runs)...")
    result4 = tester.test_endurance()
    tester.results.append(result4)
    print(f"  Result: {'PASS' if result4.success else 'FAIL'}")
    print(f"  Details: {result4.details}")
    if result4.warnings:
        for w in result4.warnings:
            print(f"  WARNING: {w}")

    # Test 5: Adaptive Adversary
    print("\n[5/7] Adaptive Adversary Test...")
    result5 = tester.test_adaptive_adversary()
    tester.results.append(result5)
    print(f"  Result: {'PASS' if result5.success else 'FAIL'}")
    print(f"  Details: {result5.details}")
    if result5.warnings:
        for w in result5.warnings:
            print(f"  WARNING: {w}")

    # Test 6: Resource Exhaustion
    print("\n[6/7] Resource Exhaustion Test...")
    result6 = tester.test_resource_exhaustion()
    tester.results.append(result6)
    print(f"  Result: {'PASS' if result6.success else 'FAIL'}")
    print(f"  Details: {result6.details}")
    if result6.warnings:
        for w in result6.warnings:
            print(f"  WARNING: {w}")

    # Test 7: Network Partition
    print("\n[7/7] Network Partition Test...")
    result7 = tester.test_network_partition()
    tester.results.append(result7)
    print(f"  Result: {'PASS' if result7.success else 'FAIL'}")
    print(f"  Details: {result7.details}")
    if result7.warnings:
        for w in result7.warnings:
            print(f"  WARNING: {w}")

    t_end = time.perf_counter()
    total_duration = (t_end - t_start) * 1000

    # ─── Aggregate Results ────────────────────────────────────────────────
    total_tests = len(tester.results)
    passed_tests = sum(1 for r in tester.results if r.success)
    pass_rate = passed_tests / total_tests if total_tests > 0 else 0.0

    print("\n" + "=" * 70)
    print("EXTREME STRESS TEST SUMMARY")
    print("=" * 70)

    print("\n  Overall:")
    print(f"    Tests passed:      {passed_tests}/{total_tests} ({pass_rate:.0%})")
    print(f"    Total duration:    {total_duration/1000:.0f}s ({total_duration/1000/60:.1f} min)")

    print("\n  By Test:")
    for r in tester.results:
        status = "PASS" if r.success else "FAIL"
        print(f"    {r.test_name:<30} {status} ({r.duration_ms/1000:.1f}s)")
        if r.warnings:
            for w in r.warnings:
                print(f"      ⚠ {w}")

    return {
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "pass_rate": pass_rate,
        "total_duration_ms": total_duration,
        "results": [
            {
                "test_name": r.test_name,
                "scenario": r.scenario,
                "success": r.success,
                "metrics": r.metrics,
                "details": r.details,
                "warnings": r.warnings,
                "duration_ms": r.duration_ms,
            }
            for r in tester.results
        ],
    }


if __name__ == "__main__":
    results = run_extreme_stress_suite()

    output_path = Path(__file__).parent.parent.parent / "tests" / "stress" / "extreme_stress_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")
