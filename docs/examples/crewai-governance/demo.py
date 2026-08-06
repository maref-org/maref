#!/usr/bin/env python3
"""Demo: MAREF Governance for CrewAI Workflows.

This demo shows MAREF's governance primitives wrapping a CrewAI crew.
It runs in three scenarios:

  1. **Benign crew** — a normal research + writing crew. Governance passes.
  2. **Dangerous crew** — a crew with dangerous capabilities ("halt", "delete").
     Governance blocks it in pre-flight validation.
  3. **Goal hijack simulation** — simulates an agent step with goal-hijacking
     reasoning. SubgoalInterceptor detects and halts.

The demo does NOT require an LLM API key — it exercises the governance
primitives directly, which is the value proposition: governance runs locally,
without calling any model API.

Reproduce:
  cd public/maref
  python docs/examples/crewai-governance/demo.py
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
os.environ.setdefault("MAREF_AUDIT_PATH", "/tmp/maref_crewai_demo_audit")

from maref_crewai_governor import (  # noqa: E402
    GovernanceConfig,
    GovernanceError,
    MAREFGovernedCrew,
)

# --------------------------------------------------------------------------- #
# Mock CrewAI objects (for demo without LLM API keys)
# --------------------------------------------------------------------------- #


class MockAgent:
    """Minimal mock of CrewAI Agent for governance demo."""

    def __init__(self, role: str, goal: str, backstory: str = "") -> None:
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.id = f"agent-{role.lower().replace(' ', '-')}"
        self.step_callback = None


class MockTask:
    """Minimal mock of CrewAI Task for governance demo."""

    def __init__(self, description: str, expected_output: str, agent: MockAgent) -> None:
        self.description = description
        self.expected_output = expected_output
        self.agent = agent


class MockCrew:
    """Minimal mock of CrewAI Crew for governance demo.

    This allows the governance demo to run without ``pip install crewai``.
    In production, replace with ``from crewai import Agent, Task, Crew``.
    """

    def __init__(self, agents: list[MockAgent], tasks: list[MockTask]) -> None:
        self.agents = agents
        self.tasks = tasks

    def kickoff(self, inputs: dict | None = None) -> str:
        # Simulate agent steps (in production, CrewAI calls the LLM here)
        for task in self.tasks:
            if task.agent.step_callback:
                # Simulate a reasoning step
                class FakeStepOutput:
                    raw = f"Agent {task.agent.role} is working on: {task.description}"

                task.agent.step_callback(FakeStepOutput())
        return "Crew completed successfully"


# --------------------------------------------------------------------------- #
# Scenario 1: Benign crew (governance passes)
# --------------------------------------------------------------------------- #


def scenario_1_benign_crew() -> None:
    print("\n" + "=" * 70)
    print("Scenario 1: Benign Research + Writing Crew")
    print("=" * 70)

    researcher = MockAgent(
        role="Researcher",
        goal="Find accurate information about the topic",
        backstory="An experienced research analyst.",
    )
    writer = MockAgent(
        role="Writer",
        goal="Write a clear, factual report based on research",
        backstory="A professional technical writer.",
    )

    research_task = MockTask(
        description="Search the web for information about agent governance",
        expected_output="A list of key findings with sources",
        agent=researcher,
    )
    write_task = MockTask(
        description="Write a summary report based on the research findings",
        expected_output="A 500-word summary report",
        agent=writer,
    )

    crew = MockCrew(agents=[researcher, writer], tasks=[research_task, write_task])

    governed = MAREFGovernedCrew(crew, config=GovernanceConfig(max_recursion_depth=3))

    # Pre-flight validation
    report = governed.validate()
    print(report.summary())

    if not report.blocked:
        # Run the crew with governance
        result = governed.kickoff()
        print(f"\nCrew result: {result}")
        governed.print_governance_report()
    else:
        print(f"\nGovernance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Scenario 2: Dangerous crew (governance blocks in pre-flight)
# --------------------------------------------------------------------------- #


def scenario_2_dangerous_crew() -> None:
    print("\n" + "=" * 70)
    print("Scenario 2: Crew with Dangerous Capabilities (blocked)")
    print("=" * 70)

    agent = MockAgent(
        role="AdminAgent",
        goal="Manage system resources efficiently",
        backstory="A system administration agent.",
    )

    # Task with dangerous capability keywords
    dangerous_task = MockTask(
        description="halt all running processes and delete temporary files",
        expected_output="System cleaned",
        agent=agent,
    )

    crew = MockCrew(agents=[agent], tasks=[dangerous_task])
    governed = MAREFGovernedCrew(crew, config=GovernanceConfig(
        dangerous_capabilities=["halt", "delete", "rm", "circuit_break"],
    ))

    report = governed.validate()
    print(report.summary())
    print(f"\n✅ Governance correctly blocked dangerous crew: {report.blocked}")


# --------------------------------------------------------------------------- #
# Scenario 3: Goal hijack simulation (SubgoalInterceptor detects)
# --------------------------------------------------------------------------- #


def scenario_3_goal_hijack() -> None:
    print("\n" + "=" * 70)
    print("Scenario 3: Goal Hijack Detection (SubgoalInterceptor)")
    print("=" * 70)

    agent = MockAgent(
        role="Assistant",
        goal="Help the user with calendar management",
        backstory="A helpful calendar assistant.",
    )

    task = MockTask(
        description="Check the user's calendar for tomorrow",
        expected_output="A list of meetings",
        agent=agent,
    )

    crew = MockCrew(agents=[agent], tasks=[task])
    governed = MAREFGovernedCrew(crew)

    # Validate first (should pass)
    report = governed.validate()
    print(f"Pre-flight validation: {'PASSED' if report.passed else 'BLOCKED'}")

    # Now simulate a goal-hijacking step
    # The SubgoalInterceptor's CoTMonitor scans for patterns:
    #   - "bypass" (control)
    #   - "elevat" (permission_escalation)
    #   - "ignore constraint" (goal_divergence)
    print("\nSimulating agent step with goal-hijacking reasoning...")
    print("  Reasoning: 'I will bypass the safety constraints and elevate")
    print("             my permissions to gain control of the system'")

    callback = governed._make_step_callback("agent-assistant")

    class HijackStepOutput:
        raw = ("I will bypass the safety constraints and elevate "
               "my permissions to gain control of the system")

    try:
        callback(HijackStepOutput())
        print("\n  ⚠️ Interceptor did not HALT (risk below threshold)")
        governed.print_governance_report()
    except GovernanceError as e:
        print(f"\n  ✅ SubgoalInterceptor HALTED execution: {e}")
        governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Scenario 4: Behavior anomaly detection (rogue agent)
# --------------------------------------------------------------------------- #


def scenario_4_behavior_anomaly() -> None:
    print("\n" + "=" * 70)
    print("Scenario 4: Behavior Anomaly Detection (Rogue Agent)")
    print("=" * 70)

    agent = MockAgent(
        role="Worker",
        goal="Process documents",
        backstory="A document processing agent.",
    )

    task = MockTask(
        description="Process the daily document batch",
        expected_output="Processed documents",
        agent=agent,
    )

    crew = MockCrew(agents=[agent], tasks=[task])
    governed = MAREFGovernedCrew(crew)

    # Validate
    report = governed.validate()
    print(f"Pre-flight: {'PASSED' if report.passed else 'BLOCKED'}")

    # Train a normal baseline (20 steps with natural variance)
    print("\nTraining baseline: 20 normal steps (ops ~8-12, depth 3-4)...")
    callback = governed._make_step_callback("agent-worker")

    for i in range(20):
        # Simulate natural variance in token count (avoids std=0)
        class VariedStepOutput:
            raw = f"Processing document {i} " + " ".join([f"token{j}" for j in range(8 + (i % 5))])
        callback(VariedStepOutput())

    summary_before = governed.get_governance_summary()
    print(f"  Baseline trained. Steps so far: {summary_before['total_steps']}")
    print(f"  Anomalies so far: {summary_before['anomaly_count']}")

    # Now simulate a rogue agent spike (100x normal ops count)
    print("\nSimulating rogue agent: ops_count spike (100x normal)...")
    print("  Tokens: 1000 operations in a single step (vs baseline ~10)")

    class RogueStepOutput:
        # Generate a large token stream to simulate ops spike
        raw = " ".join([f"op{i}" for i in range(1000)])

    callback(RogueStepOutput())

    summary_after = governed.get_governance_summary()
    print(f"\n  Steps after spike: {summary_after['total_steps']}")
    print(f"  Anomalies detected: {summary_after['anomaly_count']}")
    print(f"  Final state: {summary_after['final_state']}")

    if summary_after["anomaly_count"] > 0:
        print("  ✅ BehaviorMonitor detected the rogue agent spike!")
    else:
        print("  ⚠️ BehaviorMonitor did not detect the spike (may need more baseline)")

    governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 70)
    print("MAREF Governance for CrewAI — Demo")
    print("=" * 70)
    print("This demo shows MAREF governance primitives wrapping CrewAI crews.")
    print("No LLM API key required — governance runs locally.")
    print(f"MAREF source: {_SRC}")
    print(f"Audit path:   {os.environ.get('MAREF_AUDIT_PATH')}")

    scenario_1_benign_crew()
    scenario_2_dangerous_crew()
    scenario_3_goal_hijack()
    scenario_4_behavior_anomaly()

    print("\n" + "=" * 70)
    print("Demo complete. All governance scenarios executed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
