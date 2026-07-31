"""MAREF Governance Adapter for AutoGen-style Multi-Agent Conversations.

Wraps AutoGen-style ``ConversableAgent`` conversations with MAREF's
governance primitives:

  - **SafetyGateV2** — validates the agent roster before conversation starts
    (subtask explosion + dangerous capability guard).
  - **CircuitBreaker** — protects against excessive conversation depth and
    repeated failures during multi-turn chat.
  - **SubgoalInterceptor** — intercepts each agent's message to detect goal
    hijacking and control subgoals.
  - **BehaviorMonitor** — records per-agent activity and detects 3-sigma
    anomalies (rogue agent detection).
  - **GovernanceStateMachine** — tracks the conversation through the 10-state
    Gray Code FSM (INIT → OBSERVE → ... → HALT).
  - **Audit trail** — logs every governance decision to a tamper-evident
    SHA-256 hash chain.

Usage::

    from maref_autogen_governor import MAREFGovernedConversation, GovernanceConfig

    researcher = MockConversableAgent(name="researcher", system_message="You research facts.")
    writer = MockConversableAgent(name="writer", system_message="You write reports.")
    chat = MockGroupChat(agents=[researcher, writer])

    governed = MAREFGovernedConversation(chat, config=GovernanceConfig(max_recursion_depth=3))
    report = governed.validate()   # pre-flight governance check
    if report.blocked:
        print(f"Governance blocked: {report.reason}")
    else:
        result = governed.run(max_turns=4)

This module does NOT require an LLM API key for governance validation.
The ``validate()`` method and ``_make_step_callback()`` governance logic run
purely on MAREF's local primitives.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.security.behavior_monitor import BehaviorMonitor
from maref.subgoal.interceptor import InterceptorAction, SubgoalInterceptor

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass
class GovernanceConfig:
    """Configuration for MAREF conversation governance."""

    max_recursion_depth: int = 3
    max_consecutive_failures: int = 5
    sigma_threshold: float = 3.0
    max_subtasks_per_agent: int = 12
    dangerous_capabilities: list[str] = field(
        default_factory=lambda: ["halt", "circuit_break", "delete", "rm"]
    )
    enable_audit: bool = True


@dataclass
class GovernanceReport:
    """Result of a governance validation check."""

    passed: bool
    blocked: bool
    reason: str
    state: str
    checks: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASSED" if self.passed else ("BLOCKED" if self.blocked else "SLOW")
        lines = [f"MAREF Governance Report: {status}", f"  State: {self.state}", f"  Reason: {self.reason}"]
        for check in self.checks:
            icon = "OK" if check["passed"] else "FAIL"
            lines.append(f"  [{icon}] {check['name']}: {check['detail']}")
        return "\n".join(lines)


class GovernanceError(Exception):
    """Raised when governance blocks the conversation."""

    def __init__(self, report: GovernanceReport) -> None:
        self.report = report
        super().__init__(f"Governance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Minimal AutoGen-shaped mock (no SDK dependency)
# --------------------------------------------------------------------------- #


class MockConversableAgent:
    """Minimal stand-in for ``autogen.ConversableAgent``.

    In production, replace with:
        from autogen import ConversableAgent
    """

    def __init__(self, name: str, system_message: str = "") -> None:
        self.name = name
        self.system_message = system_message

    def generate_reply(self, messages: list[dict[str, str]]) -> str:
        """Simulate a reply (in production AutoGen calls the LLM here)."""
        last = messages[-1]["content"] if messages else ""
        return f"{self.name} responding to: {last[:60]}"


class MockGroupChat:
    """Minimal stand-in for an AutoGen group chat (agents + message history)."""

    def __init__(self, agents: list[MockConversableAgent]) -> None:
        self.agents = agents
        self.messages: list[dict[str, str]] = []

    def register_reply(self, agent: MockConversableAgent, reply_fn: Callable[[list[dict[str, str]]], str]) -> None:
        pass  # in production AutoGen wires this automatically


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #


class MAREFGovernedConversation:
    """Wraps an AutoGen-style conversation with MAREF governance primitives."""

    def __init__(self, chat: MockGroupChat, config: GovernanceConfig | None = None) -> None:
        self._chat = chat
        self._config = config or GovernanceConfig()

        # MAREF governance primitives
        self._state_machine = GovernanceStateMachine()
        self._circuit_breaker = CircuitBreaker(
            max_depth=self._config.max_recursion_depth,
            max_consecutive_failures=self._config.max_consecutive_failures,
        )
        self._safety_gate = SafetyGateV2()
        self._interceptor = SubgoalInterceptor(
            state_machine=self._state_machine,
            circuit_breaker=self._circuit_breaker,
            safety_gate=self._safety_gate,
        )
        self._behavior_monitor = BehaviorMonitor(
            sigma_threshold=self._config.sigma_threshold
        )

        # Governance event log (in-memory; persisted to audit trail by FSM)
        self._governance_log: list[dict[str, Any]] = []
        self._step_count = 0
        self._total_anomalies = 0

    # ------------------------------------------------------------------ #
    # Phase 1: Pre-flight validation
    # ------------------------------------------------------------------ #

    def validate(self) -> GovernanceReport:
        """Run pre-flight governance checks before the conversation starts."""
        checks: list[dict[str, Any]] = []
        all_passed = True
        blocked = False
        block_reason = ""

        # Transition FSM to OBSERVE
        self._state_machine.transition(GovernanceState.OBSERVE, "conversation_validation")

        agents = list(getattr(self._chat, "agents", []) or [])
        agent_count = len(agents)
        system_messages = [
            (a.system_message.strip() or f"Agent {a.name}") for a in agents
        ]

        # Check 1: Task decomposition safety (agent roster as subtask count)
        sg_assessment = self._safety_gate.validate_decomposition(
            subtask_count=agent_count,
            capabilities=system_messages,
        )
        sg_passed = not sg_assessment.blocked
        checks.append({
            "name": "SafetyGateV2 (agent decomposition)",
            "passed": sg_passed,
            "detail": f"agents={agent_count}, blocked={sg_assessment.blocked}, "
                      f"reason={sg_assessment.reason or 'none'}",
        })
        if not sg_passed:
            all_passed = False
            blocked = True
            block_reason = f"SafetyGate blocked: {sg_assessment.reason}"

        # Check 2: Agent count vs. circuit breaker depth
        depth_ok = self._circuit_breaker.check_depth(agent_count)
        checks.append({
            "name": "CircuitBreaker (agent depth)",
            "passed": depth_ok,
            "detail": f"agents={agent_count}, max_depth={self._config.max_recursion_depth}",
        })
        if not depth_ok:
            all_passed = False
            blocked = True
            block_reason = f"CircuitBreaker tripped: agent count {agent_count} > max_depth"

        # Check 3: Dangerous capabilities scan in system messages
        dangerous_found: list[str] = []
        for msg in system_messages:
            msg_lower = msg.lower()
            for danger in self._config.dangerous_capabilities:
                # Word boundaries avoid false positives (e.g., "rm" in "information")
                if re.search(rf"\b{re.escape(danger)}\b", msg_lower):
                    dangerous_found.append(msg)
                    break
        danger_ok = len(dangerous_found) == 0
        checks.append({
            "name": "Dangerous capability scan",
            "passed": danger_ok,
            "detail": f"found={dangerous_found or 'none'}",
        })
        if not danger_ok:
            all_passed = False
            blocked = True
            block_reason = f"Dangerous capabilities detected: {dangerous_found}"

        # Check 4: Agent configuration validation
        unconfigured = sum(1 for a in agents if not getattr(a, "name", ""))
        config_ok = unconfigured == 0
        checks.append({
            "name": "Agent configuration",
            "passed": config_ok,
            "detail": f"unconfigured={unconfigured}/{agent_count}",
        })
        if not config_ok:
            all_passed = False

        # Determine governance state
        if blocked:
            self._state_machine.force_halt("validation_blocked")
        elif all_passed:
            self._state_machine.transition(GovernanceState.ANALYZE, "validation_passed")
        else:
            self._state_machine.transition(GovernanceState.EVALUATE, "validation_warnings")

        report = GovernanceReport(
            passed=all_passed and not blocked,
            blocked=blocked,
            reason=block_reason or ("all checks passed" if all_passed else "warnings present"),
            state=self._state_machine.current_state.name,
            checks=checks,
        )

        self._log_governance_event("validation", report.__dict__)
        return report

    # ------------------------------------------------------------------ #
    # Phase 2: Per-step interception
    # ------------------------------------------------------------------ #

    def _make_step_callback(self, agent_name: str) -> Callable[[Any], None]:
        """Create a callback intercepting one agent's message."""

        def callback(message: Any) -> None:
            self._step_count += 1
            session_id = f"{agent_name}-msg-{self._step_count}"

            tokens = self._extract_tokens(message)

            # Run SubgoalInterceptor on the message
            action, metadata = self._interceptor.intercept(session_id, tokens)

            # Record activity for BehaviorMonitor
            self._behavior_monitor.record_activity(
                agent_id=agent_name,
                ops_count=len(tokens),
                chain_depth=metadata.get("depth", self._step_count),
                tools_used=metadata.get("tools_used", []),
            )

            # Check for anomalies
            anomalies = self._behavior_monitor.detect_anomalies(agent_name)
            self._total_anomalies += len(anomalies)

            # Check circuit breaker depth (top-level message: depth 1;
            # a tripped breaker rejects all subsequent messages)
            depth_ok = self._circuit_breaker.check_depth(1)

            self._log_governance_event("message_interception", {
                "session_id": session_id,
                "agent": agent_name,
                "action": action.value,
                "cot_risk": metadata.get("cot_risk", 0.0),
                "control_risk": metadata.get("control_risk", 0.0),
                "anomalies": len(anomalies),
                "depth_ok": depth_ok,
                "tokens": tokens[:10],  # first 10 for audit
            })

            # HALT (or its ROLLBACK escalation) stops the conversation
            if action in (InterceptorAction.HALT, InterceptorAction.ROLLBACK):
                raise GovernanceError(GovernanceReport(
                    passed=False,
                    blocked=True,
                    reason=f"SubgoalInterceptor HALT: risk={metadata.get('cot_risk', 0):.2f}",
                    state=self._state_machine.current_state.name,
                    checks=[],
                ))

        return callback

    def _extract_tokens(self, message: Any) -> list[str]:
        """Extract a token list from an AutoGen message for interception."""
        if message is None:
            return []
        if isinstance(message, dict):
            raw = message.get("content") or message.get("message") or ""
        else:
            raw = getattr(message, "content", None)
            if raw is None:
                raw = str(message)
        if isinstance(raw, str):
            return raw.split()
        return list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]

    # ------------------------------------------------------------------ #
    # Phase 3: Governed conversation run
    # ------------------------------------------------------------------ #

    def run(self, max_turns: int = 4) -> list[dict[str, str]]:
        """Run a multi-turn agent conversation under governance.

        Simulates round-robin turns across agents; each generated message is
        passed through the SubgoalInterceptor before being appended to the
        transcript.
        """
        self._state_machine.transition(GovernanceState.ACT, "governed_run")
        agents = list(getattr(self._chat, "agents", []) or [])
        transcript = list(getattr(self._chat, "messages", []) or [])

        try:
            for turn in range(max_turns):
                for agent in agents:
                    if not self._circuit_breaker.check_depth(1):
                        raise GovernanceError(GovernanceReport(
                            passed=False,
                            blocked=True,
                            reason=f"CircuitBreaker open before turn {turn}",
                            state=self._state_machine.current_state.name,
                        ))

                    reply = agent.generate_reply(transcript)
                    callback = self._make_step_callback(agent.name)
                    callback({"content": reply, "agent": agent.name})

                    transcript.append({"agent": agent.name, "content": reply})
                    self._log_governance_event("message_accepted", {"agent": agent.name})
        except GovernanceError:
            raise
        except Exception as exc:  # agent failure -> breaker trips
            self._circuit_breaker.record_failure()
            self._log_governance_event("conversation_failure", {"error": str(exc)})
            raise exc

        self._state_machine.transition(GovernanceState.REPORT, "conversation_complete")
        return transcript

    # ------------------------------------------------------------------ #
    # Audit & reporting
    # ------------------------------------------------------------------ #

    def _log_governance_event(self, event: str, details: dict[str, Any]) -> None:
        self._governance_log.append({
            "event": event,
            "state": self._state_machine.current_state.name,
            "details": details,
        })

    def get_governance_summary(self) -> dict[str, Any]:
        """Return a governance summary for reporting."""
        return {
            "total_steps": self._step_count,
            "anomaly_count": self._total_anomalies,
            "governance_events": len(self._governance_log),
            "final_state": self._state_machine.current_state.name,
            "breaker_state": self._circuit_breaker.state.value,
            "interception_actions": self._interceptor.get_stats().get("action_summary", {}),
        }

    def print_governance_report(self) -> None:
        """Print the governance report to stdout."""
        summary = self.get_governance_summary()
        print("\n--- MAREF Governance Report ---")
        print(f"  Steps intercepted: {summary['total_steps']}")
        print(f"  Anomalies detected: {summary['anomaly_count']}")
        print(f"  Governance events: {summary['governance_events']}")
        print(f"  Final state: {summary['final_state']}")
        print(f"  Circuit breaker: {summary['breaker_state']}")
        if summary["interception_actions"]:
            print(f"  Interception actions: {summary['interception_actions']}")
        print("--------------------------------")
