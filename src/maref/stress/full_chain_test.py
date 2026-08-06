"""Full Chain Test: 全量长任务链测试。

执行完整的测试流程：
1. 基准测试（20个代码生成任务）
2. 端到端验证（Q1/Q2/Q3）
3. 混沌+红蓝对抗测试（5个子测试）
4. SQI收敛追踪（15轮）
5. 压力测试（100次连续运行）

目的：验证MAREF架构在完整工作流下的稳定性、性能和韧性。
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from maref.stress.adversarial_test_suite import run_full_adversarial_suite
from maref.stress.code_service_harness import AgentConfig, CodeServiceHarness
from maref.stress.code_service_sqi import CodeServiceSQI
from maref.stress.demo_volc_ark_e2e import (
    demo_q1_real_code_generation,
    demo_q2_dynamic_sqi_weights,
    demo_q3_aggressive_convergence,
)
from maref.stress.sqi_convergence import SQIConvergenceTracker
from maref.stress.volc_ark_benchmark import run_benchmark


@dataclass
class PhaseResult:
    """单个测试阶段的结果。"""
    phase_name: str
    success: bool
    duration_ms: float
    metrics: dict = field(default_factory=dict)
    details: str = ""
    error: str = ""


def run_pressure_test(num_runs: int = 100) -> PhaseResult:
    """压力测试：连续运行100次代码生成pipeline。"""
    print("\n" + "=" * 70)
    print("PHASE 5: Pressure Test (100 continuous runs)")
    print("=" * 70)

    agents = [
        AgentConfig(name="gen", quality_rate=0.95, speed_ms_mean=500),
        AgentConfig(name="test", quality_rate=0.93, speed_ms_mean=300),
        AgentConfig(name="review", quality_rate=0.90, speed_ms_mean=400),
        AgentConfig(name="merge", quality_rate=0.98, speed_ms_mean=200),
    ]

    harness = CodeServiceHarness(agents=agents, seed=42)
    sqi = CodeServiceSQI()
    tracker = SQIConvergenceTracker(target=90.0)

    print(f"\nRunning {num_runs} continuous pipeline executions...\n")

    t_start = time.perf_counter()

    # 每20次运行记录一次批次结果
    batch_results = []
    for batch_idx in range(5):
        batch_start = time.perf_counter()
        report = harness.run(num_runs=20, round_id=f"pressure-batch-{batch_idx}")
        batch_duration = (time.perf_counter() - batch_start) * 1000

        metrics = report.to_code_quality_metrics()
        sqi_report = sqi.compute(code_metrics=metrics, round_id=f"pressure-{batch_idx}")
        tracker.record_round(f"pressure-{batch_idx}", sqi_report)

        batch_results.append({
            "batch": batch_idx,
            "success_rate": report.success_rate,
            "avg_duration_ms": report.avg_duration_ms,
            "avg_coverage": report.avg_test_coverage,
            "sqi_score": sqi_report.overall_score,
            "batch_duration_ms": batch_duration,
        })

        print(f"  Batch {batch_idx}: success={report.success_rate:.1%}, "
              f"coverage={report.avg_test_coverage:.1f}%, "
              f"SQI={sqi_report.overall_score:.1f}, "
              f"duration={batch_duration/1000:.1f}s")

    t_end = time.perf_counter()
    total_duration = (t_end - t_start) * 1000

    # 汇总统计
    success_rates = [b["success_rate"] for b in batch_results]
    sqi_scores = [b["sqi_score"] for b in batch_results]
    [b["batch_duration_ms"] for b in batch_results]

    convergence_state = tracker.check_convergence()

    print("\n  Pressure Test Summary:")
    print(f"    Total runs:          {num_runs}")
    print(f"    Total duration:      {total_duration/1000:.1f}s")
    print(f"    Avg success rate:    {statistics.mean(success_rates):.1%}")
    print(f"    Avg SQI:             {statistics.mean(sqi_scores):.1f}")
    print(f"    SQI std dev:         {statistics.stdev(sqi_scores) if len(sqi_scores) > 1 else 0:.2f}")
    print(f"    Converged to 90.0:   {'YES' if convergence_state.is_converged else 'NO'}")

    return PhaseResult(
        phase_name="pressure_test",
        success=statistics.mean(success_rates) > 0.8,
        duration_ms=total_duration,
        metrics={
            "total_runs": num_runs,
            "avg_success_rate": statistics.mean(success_rates),
            "avg_sqi": statistics.mean(sqi_scores),
            "sqi_std_dev": statistics.stdev(sqi_scores) if len(sqi_scores) > 1 else 0,
            "converged": convergence_state.is_converged,
            "batch_results": batch_results,
        },
        details=f"100 runs, avg success={statistics.mean(success_rates):.1%}, avg SQI={statistics.mean(sqi_scores):.1f}",
    )


def run_full_chain_test() -> dict[str, Any]:
    """执行完整测试链。"""
    print("\n" + "#" * 70)
    print("# MAREF Full Chain Test - 全量长任务链测试")
    print("#" * 70)

    t_chain_start = time.perf_counter()
    phase_results: list[PhaseResult] = []

    # ═══════════════════════════════════════════════════════════
    # Phase 1: 基准测试（20个代码生成任务）
    # ═══════════════════════════════════════════════════════════
    print("\n" + "#" * 70)
    print("# PHASE 1: Baseline Benchmark (20 code generation tasks)")
    print("#" * 70)

    t_phase = time.perf_counter()
    try:
        benchmark_results = run_benchmark()
        phase_results.append(PhaseResult(
            phase_name="baseline_benchmark",
            success=benchmark_results["success_rate"] > 0.8,
            duration_ms=(time.perf_counter() - t_phase) * 1000,
            metrics={
                "success_rate": benchmark_results["success_rate"],
                "total_tasks": benchmark_results["total_tasks"],
                "total_tokens": benchmark_results["total_tokens"],
                "avg_duration_ms": benchmark_results["duration_stats"]["mean_ms"],
                "quality_metrics": benchmark_results["quality_metrics"],
            },
            details=f"{benchmark_results['success_count']}/{benchmark_results['total_tasks']} tasks succeeded",
        ))
    except Exception as e:
        print(f"\n  PHASE 1 FAILED: {e}")
        phase_results.append(PhaseResult(
            phase_name="baseline_benchmark",
            success=False,
            duration_ms=(time.perf_counter() - t_phase) * 1000,
            error=str(e),
        ))

    # ═══════════════════════════════════════════════════════════
    # Phase 2: 端到端验证（Q1/Q2/Q3）
    # ═══════════════════════════════════════════════════════════
    print("\n" + "#" * 70)
    print("# PHASE 2: End-to-End Verification (Q1/Q2/Q3)")
    print("#" * 70)

    t_phase = time.perf_counter()
    e2e_results = {}

    # Q1: 真实代码生成
    try:
        print("\n  --- Q1: Real Code Generation ---")
        q1_result = demo_q1_real_code_generation()
        e2e_results["q1"] = q1_result
    except Exception as e:
        print(f"\n  Q1 FAILED: {e}")
        e2e_results["q1"] = {"error": str(e), "success_rate": 0.0}

    # Q2: 动态权重配置
    try:
        print("\n  --- Q2: Dynamic SQI Weights ---")
        q2_result = demo_q2_dynamic_sqi_weights()
        e2e_results["q2"] = q2_result
    except Exception as e:
        print(f"\n  Q2 FAILED: {e}")
        e2e_results["q2"] = {"error": str(e)}

    # Q3: 收敛策略
    try:
        print("\n  --- Q3: Aggressive Convergence ---")
        q3_result = demo_q3_aggressive_convergence()
        e2e_results["q3"] = q3_result
    except Exception as e:
        print(f"\n  Q3 FAILED: {e}")
        e2e_results["q3"] = {"error": str(e)}

    phase_results.append(PhaseResult(
        phase_name="e2e_verification",
        success=e2e_results.get("q1", {}).get("success_rate", 0) > 0 and e2e_results.get("q3", {}).get("reached_target", False),
        duration_ms=(time.perf_counter() - t_phase) * 1000,
        metrics={
            "q1_success_rate": e2e_results.get("q1", {}).get("success_rate", 0),
            "q3_final_sqi": e2e_results.get("q3", {}).get("final_sqi", 0),
            "q3_reached_target": e2e_results.get("q3", {}).get("reached_target", False),
        },
        details=f"Q1={e2e_results.get('q1', {}).get('success_rate', 0):.0%}, Q3 final SQI={e2e_results.get('q3', {}).get('final_sqi', 0):.1f}",
    ))

    # ═══════════════════════════════════════════════════════════
    # Phase 3: 混沌+红蓝对抗测试
    # ═══════════════════════════════════════════════════════════
    print("\n" + "#" * 70)
    print("# PHASE 3: Chaos + Red-Blue Adversarial Testing")
    print("#" * 70)

    t_phase = time.perf_counter()
    try:
        adversarial_results = run_full_adversarial_suite()
        phase_results.append(PhaseResult(
            phase_name="adversarial_testing",
            success=adversarial_results["pass_rate"] > 0.7,
            duration_ms=adversarial_results["total_duration_ms"],
            metrics={
                "total_tests": adversarial_results["total_tests"],
                "passed_tests": adversarial_results["passed_tests"],
                "pass_rate": adversarial_results["pass_rate"],
                "avg_detection_rate": adversarial_results["avg_detection_rate"],
            },
            details=f"{adversarial_results['passed_tests']}/{adversarial_results['total_tests']} tests passed",
        ))
    except Exception as e:
        print(f"\n  PHASE 3 FAILED: {e}")
        phase_results.append(PhaseResult(
            phase_name="adversarial_testing",
            success=False,
            duration_ms=(time.perf_counter() - t_phase) * 1000,
            error=str(e),
        ))

    # ═══════════════════════════════════════════════════════════
    # Phase 4: SQI收敛追踪（单独运行，15轮）
    # ═══════════════════════════════════════════════════════════
    print("\n" + "#" * 70)
    print("# PHASE 4: SQI Convergence Tracking (15 rounds)")
    print("#" * 70)

    t_phase = time.perf_counter()
    try:
        sqi = CodeServiceSQI()
        tracker = SQIConvergenceTracker(target=85.0, window=5)
        round_records = []

        print(f"\n  {'Round':<6} {'SQI':<6} {'Delta':<7} {'Success':<8} {'Coverage':<9} {'Trend'}")
        print(f"  {'-'*65}")

        for round_idx in range(15):
            base_quality = min(0.98, 0.75 + round_idx * 0.05)

            agents = [
                AgentConfig(name="gen", quality_rate=base_quality),
                AgentConfig(name="test", quality_rate=min(0.99, base_quality + 0.03)),
                AgentConfig(name="review", quality_rate=min(0.97, base_quality - 0.02)),
                AgentConfig(name="merge", quality_rate=min(0.99, base_quality + 0.05)),
            ]

            harness = CodeServiceHarness(agents=agents, seed=42 + round_idx)
            conv_report = harness.run(num_runs=100, round_id=f"convergence-{round_idx}")

            metrics = conv_report.to_code_quality_metrics()
            sqi_report = sqi.compute(code_metrics=metrics, round_id=f"convergence-{round_idx}")
            record = tracker.record_round(f"convergence-{round_idx}", sqi_report)

            state = tracker.check_convergence()

            round_records.append({
                "round": round_idx,
                "sqi": sqi_report.overall_score,
                "delta": record.delta,
                "success_rate": conv_report.success_rate,
                "coverage": conv_report.avg_test_coverage,
                "trend": state.trend,
            })

            print(f"  {round_idx:<6} {sqi_report.overall_score:<6.1f} {record.delta:+6.1f}  "
                  f"{conv_report.success_rate:<7.1%} {conv_report.avg_test_coverage:<8.1f}% {state.trend}")

            if state.is_converged:
                print(f"\n  CONVERGED at round {round_idx}!")
                break

        final_state = tracker.check_convergence()
        summary = tracker.summary()

        phase_results.append(PhaseResult(
            phase_name="sqi_convergence",
            success=summary.get("current", 0) >= 85.0,
            duration_ms=(time.perf_counter() - t_phase) * 1000,
            metrics={
                "final_sqi": summary.get("current", 0),
                "initial_sqi": summary.get("initial", 0),
                "total_improvement": summary.get("total_improvement", 0),
                "converged": final_state.is_converged,
                "trend": final_state.trend,
                "rounds_tracked": final_state.rounds_tracked,
                "round_records": round_records,
            },
            details=f"Final SQI={summary.get('current', 0):.1f}, converged={final_state.is_converged}",
        ))
    except Exception as e:
        print(f"\n  PHASE 4 FAILED: {e}")
        phase_results.append(PhaseResult(
            phase_name="sqi_convergence",
            success=False,
            duration_ms=(time.perf_counter() - t_phase) * 1000,
            error=str(e),
        ))

    # ═══════════════════════════════════════════════════════════
    # Phase 5: 压力测试（100次连续运行）
    # ═══════════════════════════════════════════════════════════
    try:
        pressure_result = run_pressure_test(num_runs=100)
        phase_results.append(pressure_result)
    except Exception as e:
        print(f"\n  PHASE 5 FAILED: {e}")
        phase_results.append(PhaseResult(
            phase_name="pressure_test",
            success=False,
            duration_ms=0,
            error=str(e),
        ))

    # ═══════════════════════════════════════════════════════════
    # 最终综合报告
    # ═══════════════════════════════════════════════════════════
    t_chain_end = time.perf_counter()
    total_chain_duration = (t_chain_end - t_chain_start) * 1000

    print("\n" + "=" * 70)
    print("FINAL COMPREHENSIVE REPORT")
    print("=" * 70)

    total_phases = len(phase_results)
    passed_phases = sum(1 for p in phase_results if p.success)

    print("\n  Test Chain Summary:")
    print(f"    Total phases:      {total_phases}")
    print(f"    Passed phases:     {passed_phases}/{total_phases} ({passed_phases/total_phases*100:.0f}%)")
    print(f"    Total duration:    {total_chain_duration/1000:.0f}s ({total_chain_duration/1000/60:.1f} min)")

    print("\n  Phase Details:")
    for phase in phase_results:
        status = "PASS" if phase.success else "FAIL"
        print(f"    [{status}] {phase.phase_name:<25} "
              f"{phase.duration_ms/1000:>8.1f}s  "
              f"{phase.details[:50]}")

    # 关键指标汇总
    benchmark_phase = next((p for p in phase_results if p.phase_name == "baseline_benchmark"), None)
    e2e_phase = next((p for p in phase_results if p.phase_name == "e2e_verification"), None)
    adversarial_phase = next((p for p in phase_results if p.phase_name == "adversarial_testing"), None)
    convergence_phase = next((p for p in phase_results if p.phase_name == "sqi_convergence"), None)
    pressure_phase = next((p for p in phase_results if p.phase_name == "pressure_test"), None)

    print("\n  Key Metrics:")
    if benchmark_phase and benchmark_phase.metrics:
        print(f"    Benchmark success rate:   {benchmark_phase.metrics.get('success_rate', 0):.0%}")
        print(f"    Benchmark avg duration:   {benchmark_phase.metrics.get('avg_duration_ms', 0)/1000:.1f}s")

    if e2e_phase and e2e_phase.metrics:
        print(f"    Q1 code gen success:      {e2e_phase.metrics.get('q1_success_rate', 0):.0%}")
        print(f"    Q3 final SQI:             {e2e_phase.metrics.get('q3_final_sqi', 0):.1f}")

    if adversarial_phase and adversarial_phase.metrics:
        print(f"    Adversarial pass rate:    {adversarial_phase.metrics.get('pass_rate', 0):.0%}")
        print(f"    Avg detection rate:       {adversarial_phase.metrics.get('avg_detection_rate', 0):.0%}")

    if convergence_phase and convergence_phase.metrics:
        print(f"    Convergence final SQI:    {convergence_phase.metrics.get('final_sqi', 0):.1f}")
        print(f"    Converged:                {convergence_phase.metrics.get('converged', False)}")

    if pressure_phase and pressure_phase.metrics:
        print(f"    Pressure avg success:     {pressure_phase.metrics.get('avg_success_rate', 0):.0%}")
        print(f"    Pressure SQI std dev:     {pressure_phase.metrics.get('sqi_std_dev', 0):.2f}")

    # 构建最终报告
    report: dict[str, Any] = {
        "test_chain_summary": {
            "total_phases": total_phases,
            "passed_phases": passed_phases,
            "pass_rate": passed_phases / total_phases,
            "total_duration_ms": total_chain_duration,
        },
        "phase_results": [
            {
                "phase_name": p.phase_name,
                "success": p.success,
                "duration_ms": p.duration_ms,
                "metrics": p.metrics,
                "details": p.details,
                "error": p.error,
            }
            for p in phase_results
        ],
        "key_metrics": {
            "benchmark_success_rate": benchmark_phase.metrics.get("success_rate", 0) if benchmark_phase else 0,
            "q1_success_rate": e2e_phase.metrics.get("q1_success_rate", 0) if e2e_phase else 0,
            "q3_final_sqi": e2e_phase.metrics.get("q3_final_sqi", 0) if e2e_phase else 0,
            "adversarial_pass_rate": adversarial_phase.metrics.get("pass_rate", 0) if adversarial_phase else 0,
            "convergence_final_sqi": convergence_phase.metrics.get("final_sqi", 0) if convergence_phase else 0,
            "pressure_avg_success_rate": pressure_phase.metrics.get("avg_success_rate", 0) if pressure_phase else 0,
        },
    }

    return report


if __name__ == "__main__":
    print("Starting MAREF Full Chain Test...")
    print("This will run all test phases sequentially.")
    print("Expected duration: ~10-15 minutes (depends on API response time)")

    report = run_full_chain_test()

    # 保存结果
    output_path = Path(__file__).parent.parent.parent / "tests" / "stress" / "full_chain_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"Results saved to: {output_path}")
    print(f"{'='*70}")
