"""Quick Q3 convergence test - code only mode."""
from maref.stress.code_service_harness import AgentConfig, CodeServiceHarness
from maref.stress.code_service_sqi import CodeServiceSQI
from maref.stress.sqi_convergence import SQIConvergenceTracker

sqi = CodeServiceSQI()
tracker = SQIConvergenceTracker()

print("Round | SQI   | Delta  | Success | Coverage | Strategy")
print("-" * 62)

for round_idx in range(15):
    base_quality = min(0.98, 0.75 + round_idx * 0.05)
    agents = [
        AgentConfig(name="gen", quality_rate=base_quality, speed_ms_mean=500),
        AgentConfig(name="test", quality_rate=min(0.99, base_quality + 0.03), speed_ms_mean=300),
        AgentConfig(name="review", quality_rate=min(0.97, base_quality - 0.02), speed_ms_mean=400),
        AgentConfig(name="merge", quality_rate=min(0.99, base_quality + 0.05), speed_ms_mean=200),
    ]
    harness = CodeServiceHarness(agents=agents, seed=42 + round_idx)
    report = harness.run(num_runs=100, round_id=f"round-{round_idx}")
    metrics = report.to_code_quality_metrics()
    # Code-only mode: no harness data passed
    sqi_report = sqi.compute(code_metrics=metrics, round_id=f"round-{round_idx}")
    record = tracker.record_round(f"round-{round_idx}", sqi_report)
    delta = record.delta
    strategy = "aggressive" if round_idx < 10 else "refinement"
    print(
        f"{round_idx:5d} | {sqi_report.overall_score:5.1f} | {delta:+6.1f} | "
        f"{report.success_rate:.2%}   | {report.avg_test_coverage:.0f}%    | {strategy}"
    )
    if sqi_report.overall_score >= 75.0 and round_idx >= 3:
        print(f"TARGET 75.0 reached at round {round_idx}!")
        break

state = tracker.check_convergence()
print(f"\nConverged: {state.is_converged}, Score: {state.current_score:.1f}, Trend: {state.trend}")
print(f"Improvement: {state.current_score - tracker._history[0].overall_score:.1f}")
