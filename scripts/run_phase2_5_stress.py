"""Phases 2-5: Real component stress testing (R77-R100)."""
import random

from maref.governance import CircuitBreaker, GovernanceState, GovernanceStateMachine
from maref.recursive.resilience_v2 import ResilienceEvaluatorV2
from maref.stress import ResilienceTracker, StressHarness, StressLevel


def run_phase23(rounds, harness, tracker):
    """Phases 2+3: Threshold discovery + dual-axis pressure."""
    axes_configs = [
        ("R77", {"agent_concurrency": 400, "churn_rate": 100}, [400, 500, 600, 700, 800], "agent_concurrency"),
        ("R78", {"recursion_depth": 3}, [5, 10, 15, 20, 25], "fault_rate"),
        ("R79", {}, [10, 15, 20, 25, 30], "oscillation_rate"),
        ("R80", {"agent_concurrency": 100}, [10, 25, 50, 75, 100], None),
        ("R81", {"agent_concurrency": 200, "churn_rate": 100}, [1], None),
        ("R82", {"agent_concurrency": 500, "churn_rate": 500, "fault_rate": 30}, [1], None),
        ("R83", {"agent_concurrency": 500, "churn_rate": 300}, [1], None),
        ("R84", {"agent_concurrency": 500, "fault_rate": 10}, [1], None),
        ("R85", {"churn_rate": 200, "recursion_depth": 3}, [1], None),
        ("R86", {"churn_rate": 200, "oscillation_rate": 20}, [1], None),
        ("R87", {"fault_rate": 20, "data_volume": 100000}, [1], None),
        ("R88", {"agent_concurrency": 100, "churn_rate": 50}, [1], None),
    ]

    for rid, base_axes, values, vary_axis in axes_configs:
        for v in values:
            label = f"{rid}-{vary_axis}={v}" if vary_axis else f"{rid}-run"
            harness.set_level(StressLevel.L1)
            for ax, val in base_axes.items():
                harness.set_axis(ax, float(val))
            if vary_axis:
                harness.set_axis(vary_axis, float(v))
            harness.set_duration(0.5 if rid.startswith("R8") else 0.3)
            result = harness.run(label)
            tracker.record_round(label, result.resilience_score, result.to_dict())
            cb = "OPEN" if result.cb_state != "CLOSED" else "OK"
            print(f"  {label:35s} score={result.resilience_score:6.2f}  p99={result.latency_p99:7.2f}ms  "
                  f"CB={cb}  heal={result.healer_success_rate:.2f}  errors={len(result.errors)}")

    return tracker


def run_phase45(harness, tracker):
    """Phases 4+5: Multi-axis chaos + endurance."""
    rounds = [
        ("R89-三日蚀", {"agent_concurrency": 250, "churn_rate": 300, "fault_rate": 10}, 2.0),
        ("R90-递归风暴", {"churn_rate": 300, "fault_rate": 20, "recursion_depth": 3}, 1.0),
        ("R91-政策地震", {"churn_rate": 200, "fault_rate": 10, "oscillation_rate": 30, "data_volume": 500000}, 1.0),
        ("R92-全面战争", {"agent_concurrency": 500, "churn_rate": 200, "fault_rate": 15,
                          "recursion_depth": 2, "oscillation_rate": 15, "data_volume": 200000}, 1.0),
        ("R93-降级链", {"agent_concurrency": 500, "churn_rate": 300, "fault_rate": 30}, 0.5),
        ("R94-恢复链", {"agent_concurrency": 500, "churn_rate": 100, "oscillation_rate": 10}, 0.5),
        ("R96-快热冲击", {"agent_concurrency": 1000, "churn_rate": 1000, "fault_rate": 50}, 0.2),
        ("R97-脉冲L1", {"agent_concurrency": 100, "churn_rate": 10, "fault_rate": 1}, 0.3),
        ("R97-脉冲L5", {"agent_concurrency": 1000, "churn_rate": 1000, "fault_rate": 50}, 0.3),
        ("R97-脉冲L1b", {"agent_concurrency": 100, "churn_rate": 10, "fault_rate": 1}, 0.3),
        ("R97-脉冲L5b", {"agent_concurrency": 1000, "churn_rate": 1000, "fault_rate": 50}, 0.3),
        ("R98-fuzz", {"agent_concurrency": 100, "fault_rate": 100}, 0.5),
    ]

    for rid, axes, duration in rounds:
        harness.set_level(StressLevel.L1)
        for ax, val in axes.items():
            harness.set_axis(ax, float(val))
        harness.set_duration(duration)
        result = harness.run(rid)
        tracker.record_round(rid, result.resilience_score, result.to_dict())
        deg = ",".join(result.degradation_plans[:3]) if result.degradation_plans else "none"
        print(f"  {rid:35s} score={result.resilience_score:6.2f}  p99={result.latency_p99:7.2f}ms  "
              f"CB={result.cb_state}  heal={result.healer_success_rate:.2f}  degrade=[{deg}]  errors={len(result.errors)}")

    return tracker


def run_r95_soak(harness, tracker, hours: float = 0.5):
    """R95: Soak test (scaled to practical duration)."""
    harness.set_level(StressLevel.L1)
    harness.set_axis("agent_concurrency", 250)
    harness.set_axis("churn_rate", 50)
    harness.set_axis("fault_rate", 5)
    harness.set_axis("recursion_depth", 1)
    harness.set_duration(hours * 60)
    print(f"  R95-soak starting {hours}h run...")
    result = harness.run("R95-soak")
    tracker.record_round("R95-soak", result.resilience_score, result.to_dict())
    print(f"  R95-soak score={result.resilience_score:.2f}  p99={result.latency_p99:.2f}ms  "
          f"churn={result.metadata.get('churn_count',0)}  errors={len(result.errors)}")
    return tracker


def run_r99_random_search(harness, tracker, samples: int = 50):
    """R99: Random search for worst-case stress combination."""
    axes = ["agent_concurrency", "churn_rate", "fault_rate", "recursion_depth",
            "oscillation_rate", "data_volume"]
    levels = {
        "agent_concurrency": [100, 500, 1000],
        "churn_rate": [10, 300, 1000],
        "fault_rate": [1, 15, 50],
        "recursion_depth": [1, 3, 5],
        "oscillation_rate": [5, 25, 100],
        "data_volume": [1000, 100000, 1000000],
    }

    for i in range(samples):
        combo = {ax: random.choice(levels[ax]) for ax in axes}
        rid = f"R99-search-{i}"
        harness.set_level(StressLevel.L1)
        for ax, val in combo.items():
            harness.set_axis(ax, float(val))
        harness.set_duration(0.2)
        result = harness.run(rid)
        tracker.record_round(rid, result.resilience_score, result.to_dict())
        if i % 10 == 0 or i == samples - 1:
            print(f"  R99 [{i+1}/{samples}] latest score={result.resilience_score:.2f}")

    worst = tracker.worst()
    if worst:
        print(f"  R99 worst: {worst.round_id} score={worst.resilience_score}")
    return tracker


def run_r98_fuzz(tracker):
    """R98: Fuzz core API endpoints."""
    from maref.governance import AuditLogger
    from maref.governance.constants import compute_valid_transitions

    errors = 0
    total = 0

    for i in range(10000):
        try:
            sm = GovernanceStateMachine()
            sm.transition(GovernanceState.INIT, "fuzz")
            sm.snapshot()
            sm.force_stabilize("fuzz")
            sm.force_halt("fuzz")
            cb = CircuitBreaker()
            cb.check_depth(i % 10)
            cb.record_failure()
            cb.get_stats()
            cb.reset()
            compute_valid_transitions()
            AuditLogger()
            r = ResilienceEvaluatorV2()
            r.evaluate({"survival_rate": random.random(), "recovery_time_ms": random.uniform(1, 10000)})
            total += 1
        except Exception:
            errors += 1

    score = (1.0 - errors / max(total, 1)) * 100.0
    tracker.record_round("R98-fuzz", score, {"total": total, "errors": errors})
    print(f"  R98-fuzz: {total} operations, {errors} errors, score={score:.2f}")
    return tracker


if __name__ == "__main__":
    tracker = ResilienceTracker()
    harness = StressHarness()

    print("=== Phase 2+3: Threshold Discovery + Dual-Axis ===")
    tracker = run_phase23(None, harness, tracker)

    print("\n=== Phase 4+5: Multi-Axis Chaos + Endurance ===")
    tracker = run_phase45(harness, tracker)

    print("\n=== R95: Soak Test ===")
    tracker = run_r95_soak(harness, tracker, hours=0.1)

    print("\n=== R98: Fuzz Test ===")
    tracker = run_r98_fuzz(tracker)

    print("\n=== R99: Random Search ===")
    tracker = run_r99_random_search(harness, tracker, samples=50)

    print(f"\n{'='*60}")
    print(f"Phases 2-5 complete. Total records: {tracker.count}")
    w = tracker.worst()
    b = tracker.best()
    if w:
        print(f"Worst: {w.round_id} score={w.resilience_score}")
    if b:
        print(f"Best:  {b.round_id} score={b.resilience_score}")
    print(f"Trend: {tracker.trend(window=10)}")
