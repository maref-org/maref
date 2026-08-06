"""Phase 1: Single-Axis Calibration (R71-R76)."""

from maref.stress import ResilienceTracker, StressHarness, StressLevel


def run_phase1() -> ResilienceTracker:
    tracker = ResilienceTracker()
    harness = StressHarness()

    rounds = [
        ("R71", "agent_concurrency", [100, 250, 500, 750, 1000]),
        ("R72", "churn_rate", [10, 50, 100, 500, 1000]),
        ("R73", "fault_rate", [1, 5, 10, 20, 50]),
        ("R74", "recursion_depth", [1, 2, 3, 4, 5, 6, 8]),
        ("R75", "oscillation_rate", [5, 10, 15, 20, 50, 100]),
        ("R76", "data_volume", [1_000, 10_000, 100_000, 500_000, 1_000_000]),
    ]

    for round_id, axis, values in rounds:
        for v in values:
            rid = f"{round_id}-{axis}={v}"
            harness.set_level(StressLevel.L1)
            harness.set_axis(axis, float(v))
            harness.set_duration(0.3)
            result = harness.run(rid)
            tracker.record_round(rid, result.resilience_score, result.to_dict())
            status = "PASS" if result.passed else f"FAIL({len(result.errors)} errors)"
            print(
                f"  {rid:30s} score={result.resilience_score:6.2f}  "
                f"p50={result.latency_p50:7.2f}ms  p99={result.latency_p99:7.2f}ms  "
                f"healer={result.healer_success_rate:.2f}  {status}"
            )

    return tracker


if __name__ == "__main__":
    t = run_phase1()
    w = t.worst()
    b = t.best()
    print(f"\nPhase 1 complete. {t.count} results.")
    if w:
        print(f"Worst: {w.round_id} score={w.resilience_score}")
    if b:
        print(f"Best:  {b.round_id} score={b.resilience_score}")
    print(f"Trend: {t.trend(window=10)}")
