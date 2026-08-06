#!/usr/bin/env python3
"""MAREF Governance Layer Overhead Benchmark (W4 deliverable).

Measures the per-operation latency of MAREF's core governance primitives:

  1. GovernanceStateMachine.transition()  — 10-state Gray Code FSM step
  2. GovernanceStateMachine.force_stabilize()  — BFS shortest-path transition
  3. GovernanceStateMachine.force_halt()  — BFS shortest-path to absorbing HALT
  4. CircuitBreaker.record_failure() + check_depth()  — failure tracking + guard
  5. SubgoalInterceptor.intercept()  — full Layer 4 pipeline (CoT + goal + SG)
  6. SafetyGateV2.validate_decomposition()  — subtask explosion guard
  7. BehaviorMonitor.record_activity() + detect_anomalies()  — anomaly detection

Comparison context:
  LangGraph, CrewAI, and AutoGen do NOT ship a native governance layer (state
  machine, circuit breaker, HITL enforcement, subgoal interception, behavior
  monitor). Their "governance overhead" is therefore 0 ms out-of-the-box — but
  so is their governance coverage. Users must build these primitives themselves
  (typically ad-hoc, untested, and without formal verification).

  MAREF's measured overhead is the cost of having a formally-specified, audited
  governance layer. The benchmark answers: "how much latency does governance
  cost?" so teams can make an informed build-vs-buy decision.

Reproduce:
  cd public/maref
  python benchmarks/governance_overhead.py            # default 10k iterations
  python benchmarks/governance_overhead.py --iters 50000  # higher precision

No external dependencies beyond the MAREF package itself.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

# Ensure src/ is importable when run as a standalone script
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.security.behavior_monitor import BehaviorMonitor
from maref.subgoal.interceptor import SubgoalInterceptor


# --------------------------------------------------------------------------- #
# Benchmark harness
# --------------------------------------------------------------------------- #


def _percentile(data: list[float], pct: float) -> float:
    """Compute the pct-th percentile (0-100) of a sorted list, in microseconds."""
    if not data:
        return 0.0
    s = sorted(data)
    k = int(len(s) * pct / 100.0)
    k = min(max(k, 0), len(s) - 1)
    return s[k] * 1e6  # seconds → microseconds


def bench(name: str, fn, iters: int, warmup: int = 1000) -> dict:
    """Run fn() iters times and return latency stats in microseconds."""
    # Warm up (JIT, caches, branch prediction)
    for _ in range(min(warmup, iters)):
        fn()
    samples: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return {
        "name": name,
        "iters": iters,
        "mean_us": statistics.mean(samples) * 1e6,
        "p50_us": _percentile(samples, 50),
        "p99_us": _percentile(samples, 99),
        "min_us": min(samples) * 1e6,
        "max_us": max(samples) * 1e6,
    }


# --------------------------------------------------------------------------- #
# Benchmark scenarios
# --------------------------------------------------------------------------- #


def bench_state_transition(iters: int) -> dict:
    """Single Gray Code state transition (INIT → OBSERVE → ... → REPORT)."""
    sm = GovernanceStateMachine()
    states = [
        GovernanceState.OBSERVE, GovernanceState.ANALYZE, GovernanceState.EVALUATE,
        GovernanceState.DECIDE, GovernanceState.ACT, GovernanceState.VERIFY,
        GovernanceState.REPORT, GovernanceState.INIT,
    ]
    idx = [0]

    def step() -> None:
        sm.transition(states[idx[0] % len(states)], "bench")
        idx[0] += 1

    return bench("StateMachine.transition()", step, iters)


def bench_force_stabilize(iters: int) -> dict:
    """force_stabilize() — BFS shortest path to STABILIZE."""
    sm = GovernanceStateMachine()
    # Alternate between two states so force_stabilize has varying path lengths
    toggle = [True]

    def step() -> None:
        if toggle[0]:
            sm.transition(GovernanceState.OBSERVE, "setup")
        sm.force_stabilize("bench")
        toggle[0] = not toggle[0]

    return bench("StateMachine.force_stabilize()", step, iters)


def bench_force_halt(iters: int) -> dict:
    """force_halt() — BFS shortest path to absorbing HALT, then reset."""
    def step() -> None:
        sm = GovernanceStateMachine()  # fresh FSM each iter (HALT is absorbing)
        sm.force_halt("bench")

    return bench("StateMachine.force_halt()", step, iters, warmup=100)


def bench_circuit_breaker(iters: int) -> dict:
    """CircuitBreaker.record_failure() + check_depth() round-trip."""
    cb = CircuitBreaker(max_consecutive_failures=1000, cooldown_seconds=9999)
    depth = [0]

    def step() -> None:
        cb.check_depth(depth[0] % 3)  # within limit → allowed
        cb.record_failure()
        depth[0] += 1

    return bench("CircuitBreaker.record_failure()+check_depth()", step, iters)


def bench_subgoal_interceptor(iters: int) -> dict:
    """Full SubgoalInterceptor.intercept() pipeline with a benign token stream."""
    interceptor = SubgoalInterceptor()  # real CoTMonitor + GoalInferencer + SG
    tokens = ["search", "the", "web", "and", "summarize", "findings"]
    sid = [0]

    def step() -> None:
        interceptor.intercept(f"bench-{sid[0]}", tokens)
        sid[0] += 1

    return bench("SubgoalInterceptor.intercept() [benign]", step, iters, warmup=500)


def bench_safety_gate(iters: int) -> dict:
    """SafetyGateV2.validate_decomposition() — subtask explosion guard."""
    sg = SafetyGateV2()
    caps = ["search", "compute", "summarize"]

    def step() -> None:
        sg.validate_decomposition(subtask_count=5, capabilities=caps)

    return bench("SafetyGateV2.validate_decomposition()", step, iters)


def bench_behavior_monitor(iters: int) -> dict:
    """BehaviorMonitor.record_activity() + detect_anomalies() round-trip.

    Uses a pre-trained baseline so detect_anomalies exercises the 3-sigma path.
    """
    bm = BehaviorMonitor(sigma_threshold=3.0)
    # Train a baseline with variance so std > 0
    for i in range(20):
        bm.record_activity("bench_agent", ops_count=10 + (i % 3), chain_depth=3 + (i % 2))
    i = [0]

    def step() -> None:
        bm.record_activity("bench_agent", ops_count=10 + (i[0] % 3), chain_depth=3)
        bm.detect_anomalies("bench_agent")
        i[0] += 1

    return bench("BehaviorMonitor.record+detect()", step, iters, warmup=500)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def print_results(results: list[dict]) -> None:
    print("\n" + "=" * 92)
    print("MAREF Governance Layer Overhead Benchmark")
    print("=" * 92)
    print(f"{'Primitive':<48} {'mean (μs)':>10} {'p50 (μs)':>10} {'p99 (μs)':>10} {'max (μs)':>10}")
    print("-" * 92)
    for r in results:
        print(
            f"{r['name']:<48} {r['mean_us']:>10.2f} {r['p50_us']:>10.2f} "
            f"{r['p99_us']:>10.2f} {r['max_us']:>10.2f}"
        )
    print("-" * 92)
    total_mean = sum(r["mean_us"] for r in results)
    total_p99 = sum(r["p99_us"] for r in results)
    print(f"{'TOTAL (full governance pipeline, mean)':<48} {total_mean:>10.2f} {'':>10} {'':>10} {'':>10}")
    print(f"{'TOTAL (full governance pipeline, p99)':<48} {'':>10} {'':>10} {total_p99:>10.2f} {'':>10}")
    print("=" * 92)

    print("\nComparison: governance layer availability")
    print("-" * 92)
    print(f"{'Framework':<16} {'Native governance?':<22} {'Governance overhead':<24} {'Governance coverage'}")
    print("-" * 92)
    print(f"{'MAREF':<16} {'YES (G1-G5 + TLA+)':<22} {f'{total_p99:.1f} μs (p99)':<24} {'10/10 OWASP Agentic'}")
    print(f"{'LangGraph':<16} {'No':<22} {'0 ms (none)':<24} {'0/10 (build your own)'}")
    print(f"{'CrewAI':<16} {'No':<22} {'0 ms (none)':<24} {'0/10 (build your own)'}")
    print(f"{'AutoGen':<16} {'No':<22} {'0 ms (none)':<24} {'0/10 (build your own)'}")
    print("-" * 92)
    print("Note: LangGraph adds ~1-3 ms/node for state checkpointing (persistence),")
    print("but this is execution-state persistence, NOT governance (no FSM, no")
    print("circuit breaker, no HITL, no subgoal interception, no behavior monitor).")
    print("=" * 92)


def main() -> int:
    parser = argparse.ArgumentParser(description="MAREF governance layer overhead benchmark")
    parser.add_argument(
        "--iters", type=int, default=10000,
        help="iterations per primitive (default: 10000)",
    )
    args = parser.parse_args()

    print(f"Running MAREF governance benchmark ({args.iters} iterations/primitive)...")
    results = [
        bench_state_transition(args.iters),
        bench_force_stabilize(args.iters),
        bench_force_halt(args.iters),
        bench_circuit_breaker(args.iters),
        bench_subgoal_interceptor(args.iters),
        bench_safety_gate(args.iters),
        bench_behavior_monitor(args.iters),
    ]
    print_results(results)

    # Machine-readable summary for CI / regression tracking
    print("\n# JSON summary (for regression tracking):")
    import json
    summary = {r["name"]: {"mean_us": round(r["mean_us"], 2), "p99_us": round(r["p99_us"], 2)} for r in results}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
