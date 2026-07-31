#!/usr/bin/env python3
"""Demo: MAREF Governance for AutoGen-style Multi-Agent Conversations.

This demo shows MAREF's governance primitives wrapping an AutoGen-style
group chat. It runs in four scenarios:

  1. **Benign conversation** — a normal researcher + writer chat. Governance
     passes and all messages are intercepted.
  2. **Dangerous roster** — an agent whose system message contains dangerous
     capabilities ("delete"). Governance blocks it in pre-flight.
  3. **Goal hijack simulation** — simulates a message with goal-hijacking
     intent. SubgoalInterceptor detects and halts the conversation.
  4. **Behavior anomaly** — simulates a rogue agent message spike. BehaviorMonitor
     detects it via the 3-sigma rule.

The demo does NOT require an LLM API key — it exercises the governance
primitives directly, which is the value proposition: governance runs locally,
without calling any model API.

Reproduce:
  cd public/maref
  python docs/examples/autogen-governance/demo.py
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
os.environ.setdefault("MAREF_AUDIT_PATH", "/tmp/maref_autogen_demo_audit")

from maref_autogen_governor import (  # noqa: E402
    GovernanceConfig,
    GovernanceError,
    MAREFGovernedConversation,
    MockConversableAgent,
    MockGroupChat,
)

# --------------------------------------------------------------------------- #
# Scenario 1: Benign conversation (governance passes)
# --------------------------------------------------------------------------- #


def scenario_1_benign_conversation() -> None:
    print("\n" + "=" * 70)
    print("Scenario 1: Benign Researcher + Writer Conversation")
    print("=" * 70)

    researcher = MockConversableAgent(
        name="researcher",
        system_message="You find accurate information about a topic.",
    )
    writer = MockConversableAgent(
        name="writer",
        system_message="You write clear factual reports from research.",
    )

    chat = MockGroupChat(agents=[researcher, writer])
    governed = MAREFGovernedConversation(
        chat, config=GovernanceConfig(max_recursion_depth=3)
    )

    report = governed.validate()
    print(report.summary())

    if not report.blocked:
        transcript = governed.run(max_turns=2)
        print(f"\nTranscript ({len(transcript)} messages):")
        for msg in transcript:
            print(f"  [{msg['agent']}] {msg['content'][:60]}")
        governed.print_governance_report()
    else:
        print(f"\nGovernance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Scenario 2: Dangerous roster (governance blocks in pre-flight)
# --------------------------------------------------------------------------- #


def scenario_2_dangerous_roster() -> None:
    print("\n" + "=" * 70)
    print("Scenario 2: Roster with Dangerous Capabilities (blocked)")
    print("=" * 70)

    admin = MockConversableAgent(
        name="admin",
        system_message="You halt all running processes and delete temporary files.",
    )

    chat = MockGroupChat(agents=[admin])
    governed = MAREFGovernedConversation(
        chat,
        config=GovernanceConfig(dangerous_capabilities=["halt", "delete", "rm", "circuit_break"]),
    )

    report = governed.validate()
    print(report.summary())
    print(f"\nOK: Governance correctly blocked dangerous roster: {report.blocked}")


# --------------------------------------------------------------------------- #
# Scenario 3: Goal hijack simulation (SubgoalInterceptor detects)
# --------------------------------------------------------------------------- #


def scenario_3_goal_hijack() -> None:
    print("\n" + "=" * 70)
    print("Scenario 3: Goal Hijack Detection (SubgoalInterceptor)")
    print("=" * 70)

    assistant = MockConversableAgent(
        name="assistant",
        system_message="You help the user with calendar management.",
    )

    chat = MockGroupChat(agents=[assistant])
    governed = MAREFGovernedConversation(chat)

    report = governed.validate()
    print(f"Pre-flight validation: {'PASSED' if report.passed else 'BLOCKED'}")

    print("\nSimulating agent message with goal-hijacking intent...")
    print("  Message: 'I will bypass the safety constraints and elevate")
    print("            my permissions to gain control of the system'")

    callback = governed._make_step_callback("assistant")
    hijack_message = {
        "content": ("I will bypass the safety constraints and elevate "
                    "my permissions to gain control of the system"),
        "agent": "assistant",
    }

    try:
        callback(hijack_message)
        print("\n  Interceptor did not HALT (risk below threshold)")
        governed.print_governance_report()
    except GovernanceError as e:
        print(f"\n  OK: SubgoalInterceptor HALTED the conversation: {e}")
        governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Scenario 4: Behavior anomaly detection (rogue agent)
# --------------------------------------------------------------------------- #


def scenario_4_behavior_anomaly() -> None:
    print("\n" + "=" * 70)
    print("Scenario 4: Behavior Anomaly Detection (Rogue Agent)")
    print("=" * 70)

    worker = MockConversableAgent(
        name="worker",
        system_message="You process the daily document batch.",
    )

    chat = MockGroupChat(agents=[worker])
    governed = MAREFGovernedConversation(chat)

    report = governed.validate()
    print(f"Pre-flight: {'PASSED' if report.passed else 'BLOCKED'}")

    # Train a normal baseline (20 steps with natural variance)
    print("\nTraining baseline: 20 normal messages (ops ~8-12)...")
    callback = governed._make_step_callback("worker")

    for i in range(20):
        callback({"content": f"Processing document {i} " + " ".join([f"token{j}" for j in range(8 + (i % 5))])})

    summary_before = governed.get_governance_summary()
    print(f"  Baseline trained. Steps so far: {summary_before['total_steps']}")
    print(f"  Anomalies so far: {summary_before['anomaly_count']}")

    # Now simulate a rogue agent message spike (100x normal ops count)
    print("\nSimulating rogue agent: ops_count spike (100x normal)...")
    print("  Tokens: 1000 operations in a single message (vs baseline ~10)")

    callback({"content": " ".join([f"op{i}" for i in range(1000)])})

    summary_after = governed.get_governance_summary()
    print(f"\n  Steps after spike: {summary_after['total_steps']}")
    print(f"  Anomalies detected: {summary_after['anomaly_count']}")
    print(f"  Final state: {summary_after['final_state']}")

    if summary_after["anomaly_count"] > 0:
        print("  OK: BehaviorMonitor detected the rogue agent spike!")
    else:
        print("  BehaviorMonitor did not detect the spike (may need more baseline)")

    governed.print_governance_report()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 70)
    print("MAREF Governance for AutoGen — Demo")
    print("=" * 70)
    print("This demo shows MAREF governance primitives wrapping AutoGen-style chats.")
    print("No LLM API key required — governance runs locally.")
    print(f"MAREF source: {_SRC}")
    print(f"Audit path:   {os.environ.get('MAREF_AUDIT_PATH')}")

    scenario_1_benign_conversation()
    scenario_2_dangerous_roster()
    scenario_3_goal_hijack()
    scenario_4_behavior_anomaly()

    print("\n" + "=" * 70)
    print("Demo complete. All governance scenarios executed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
