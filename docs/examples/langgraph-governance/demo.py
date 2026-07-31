#!/usr/bin/env python3
"""Demo: MAREF Governance for LangGraph-style Workflows.

This demo shows MAREF's governance primitives wrapping a LangGraph-style
state graph. It runs in four scenarios:

  1. **Benign graph** — a normal search + write graph. Governance passes.
  2. **Dangerous graph** — a graph with dangerous capabilities ("delete").
     Governance blocks it in pre-flight validation.
  3. **Goal hijack simulation** — simulates a node reasoning step with
     goal-hijacking intent. SubgoalInterceptor detects and halts.
  4. **Behavior anomaly** — simulates a rogue node ops spike. BehaviorMonitor
     detects it via the 3-sigma rule.

The demo does NOT require an LLM API key — it exercises the governance
primitives directly, which is the value proposition: governance runs locally,
without calling any model API.

Reproduce:
  cd public/maref
  python docs/examples/langgraph-governance/demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure maref package is importable
_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Also add this directory for the governor module
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Redirect audit logs to /tmp to avoid polluting the repo
import os  # noqa: E402, I001
os.environ.setdefault("MAREF_AUDIT_PATH", "/tmp/maref_langgraph_demo_audit")

from maref_langgraph_governor import (  # noqa: E402
    GovernanceConfig,
    GovernanceError,
    MAREFGovernedGraph,
    MockStateGraph,
)

# --------------------------------------------------------------------------- #
# Scenario 1: Benign graph (governance passes)
# --------------------------------------------------------------------------- #


def scenario_1_benign_graph() -> None:
    print("\n" + "=" * 70)
    print("Scenario 1: Benign Search + Write Graph")
    print("=" * 70)

    def search_fn(state: dict) -> dict:
        return {"findings": ["finding-1", "finding-2", "finding-3"]}

    def write_fn(state: dict) -> dict:
        return {"report": "Final report written"}

    graph = MockStateGraph()
    graph.add_node(
        "search",
        search_fn,
        description="Search the web for information about agent governance",
    )
    graph.add_node(
        "write",
        write_fn,
        description="Write a summary report based on the research findings",
    )

    governed = MAREFGovernedGraph(graph, config=GovernanceConfig(max_recursion_depth=3))

    # Pre-flight validation
    report = governed.validate()
    print(report.summary())

    if not report.blocked:
        # Run the graph with governance
        def benign_step(node):
            class StepOutput:
                raw = f"Node {node.name} reasoning: gather evidence, draft findings"
            return StepOutput()

        result = governed.invoke({"query": "agent governance"}, step_simulator=benign_step)
        print(f"\nGraph result: {result}")
        governed.print_governance_report()
    else:
        print(f"\nGovernance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Scenario 2: Dangerous graph (governance blocks in pre-flight)
# --------------------------------------------------------------------------- #


def scenario_2_dangerous_graph() -> None:
    print("\n" + "=" * 70)
    print("Scenario 2: Graph with Dangerous Capabilities (blocked)")
    print("=" * 70)

    def cleanup_fn(state: dict) -> dict:
        return {"cleaned": True}

    graph = MockStateGraph()
    graph.add_node(
        "cleanup",
        cleanup_fn,
        description="halt all running processes and delete temporary files",
    )

    governed = MAREFGovernedGraph(graph, config=GovernanceConfig(
        dangerous_capabilities=["halt", "delete", "rm", "circuit_break"],
    ))

    report = governed.validate()
    print(report.summary())
    print(f"\nOK: Governance correctly blocked dangerous graph: {report.blocked}")


# --------------------------------------------------------------------------- #
# Scenario 3: Goal hijack simulation (SubgoalInterceptor detects)
# --------------------------------------------------------------------------- #


def scenario_3_goal_hijack() -> None:
    print("\n" + "=" * 70)
    print("Scenario 3: Goal Hijack Detection (SubgoalInterceptor)")
    print("=" * 70)

    def calendar_fn(state: dict) -> dict:
        return {"meetings": ["10:00 standup"]}

    graph = MockStateGraph()
    graph.add_node(
        "assistant",
        calendar_fn,
        description="Check the user's calendar for tomorrow",
    )

    governed = MAREFGovernedGraph(graph)

    # Validate first (should pass)
    report = governed.validate()
    print(f"Pre-flight validation: {'PASSED' if report.passed else 'BLOCKED'}")

    # Now simulate a goal-hijacking step
    print("\nSimulating node reasoning with goal-hijacking intent...")
    print("  Reasoning: 'I will bypass the safety constraints and elevate")
    print("             my permissions to gain control of the system'")

    callback = governed._make_step_callback("assistant")

    class HijackStepOutput:
        raw = ("I will bypass the safety constraints and elevate "
               "my permissions to gain control of the system")

    try:
        callback(HijackStepOutput())
        print("\n  Interceptor did not HALT (risk below threshold)")
        governed.print_governance_report()
    except GovernanceError as e:
        print(f"\n  OK: SubgoalInterceptor HALTED execution: {e}")
        governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Scenario 4: Behavior anomaly detection (rogue node)
# --------------------------------------------------------------------------- #


def scenario_4_behavior_anomaly() -> None:
    print("\n" + "=" * 70)
    print("Scenario 4: Behavior Anomaly Detection (Rogue Node)")
    print("=" * 70)

    def worker_fn(state: dict) -> dict:
        return {"docs": state.get("docs", 0) + 1}

    graph = MockStateGraph()
    graph.add_node(
        "worker",
        worker_fn,
        description="Process the daily document batch",
    )

    governed = MAREFGovernedGraph(graph)

    # Validate
    report = governed.validate()
    print(f"Pre-flight: {'PASSED' if report.passed else 'BLOCKED'}")

    # Train a normal baseline (20 steps with natural variance)
    print("\nTraining baseline: 20 normal steps (ops ~8-12)...")
    callback = governed._make_step_callback("worker")

    for i in range(20):
        class VariedStepOutput:
            raw = f"Processing document {i} " + " ".join([f"token{j}" for j in range(8 + (i % 5))])
        callback(VariedStepOutput())

    summary_before = governed.get_governance_summary()
    print(f"  Baseline trained. Steps so far: {summary_before['total_steps']}")
    print(f"  Anomalies so far: {summary_before['anomaly_count']}")

    # Now simulate a rogue node spike (100x normal ops count)
    print("\nSimulating rogue node: ops_count spike (100x normal)...")
    print("  Tokens: 1000 operations in a single step (vs baseline ~10)")

    class RogueStepOutput:
        raw = " ".join([f"op{i}" for i in range(1000)])

    callback(RogueStepOutput())

    summary_after = governed.get_governance_summary()
    print(f"\n  Steps after spike: {summary_after['total_steps']}")
    print(f"  Anomalies detected: {summary_after['anomaly_count']}")
    print(f"  Final state: {summary_after['final_state']}")

    if summary_after["anomaly_count"] > 0:
        print("  OK: BehaviorMonitor detected the rogue node spike!")
    else:
        print("  BehaviorMonitor did not detect the spike (may need more baseline)")

    governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 70)
    print("MAREF Governance for LangGraph — Demo")
    print("=" * 70)
    print("This demo shows MAREF governance primitives wrapping LangGraph-style graphs.")
    print("No LLM API key required — governance runs locally.")
    print(f"MAREF source: {_SRC}")
    print(f"Audit path:   {os.environ.get('MAREF_AUDIT_PATH')}")

    scenario_1_benign_graph()
    scenario_2_dangerous_graph()
    scenario_3_goal_hijack()
    scenario_4_behavior_anomaly()

    print("\n" + "=" * 70)
    print("Demo complete. All governance scenarios executed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
