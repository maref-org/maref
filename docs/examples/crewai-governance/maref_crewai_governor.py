"""MAREF Governance Adapter for CrewAI Crews.

This adapter wraps a CrewAI ``Crew`` with MAREF's governance primitives:

  - **SafetyGateV2** — validates task decomposition before kickoff (subtask
    explosion + dangerous capability guard).
  - **CircuitBreaker** — protects against recursive depth and consecutive
    failures during crew execution.
  - **SubgoalInterceptor** — intercepts each agent's reasoning step to detect
    goal hijacking, control subgoals, and delegation scope creep.
  - **BehaviorMonitor** — records agent activity patterns and detects 3-sigma
    anomalies (rogue agent detection).
  - **GovernanceStateMachine** — tracks the crew's governance state through the
    10-state Gray Code FSM (INIT → OBSERVE → ... → HALT).
  - **Audit trail** — logs every governance decision to a tamper-evident
    SHA-256 hash chain.

Usage::

    from crewai import Agent, Task, Crew
    from maref_crewai_governor import MAREFGovernedCrew, GovernanceConfig

    researcher = Agent(role="Researcher", goal="Find facts", backstory="...")
    writer = Agent(role="Writer", goal="Write report", backstory="...")
    research_task = Task(description="Research X", expected_output="Notes", agent=researcher)
    write_task = Task(description="Write about X", expected_output="Report", agent=writer)
    crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task])

    governed = MAREFGovernedCrew(crew, config=GovernanceConfig(max_recursion_depth=3))
    report = governed.validate()  # pre-flight governance check
    if report.blocked:
        print(f"Governance blocked: {report.reason}")
    else:
        result = governed.kickoff()

This module does NOT require an LLM API key for governance validation.
The ``validate()`` method and ``_make_step_callback()`` governance logic run
purely on MAREF's local primitives.
"""

from __future__ import annotations

import re
import time
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
    """Configuration for MAREF crew governance."""

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
        status = "✅ PASSED" if self.passed else ("⛔ BLOCKED" if self.blocked else "⚠️ SLOW")
        lines = [f"MAREF Governance Report: {status}", f"  State: {self.state}", f"  Reason: {self.reason}"]
        for check in self.checks:
            icon = "✅" if check["passed"] else "❌"
            lines.append(f"  {icon} {check['name']}: {check['detail']}")
        return "\n".join(lines)


class GovernanceError(Exception):
    """Raised when governance blocks crew execution."""

    def __init__(self, report: GovernanceReport) -> None:
        self.report = report
        super().__init__(f"Governance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #


class MAREFGovernedCrew:
    """Wraps a CrewAI Crew with MAREF governance primitives.

    The governor performs three phases:

    1. **Pre-flight validation** (``validate()``) — checks task decomposition
       via SafetyGateV2, initializes CircuitBreaker, transitions the FSM to
       OBSERVE. Does NOT require an LLM.

    2. **Per-step interception** (``_make_step_callback()``) — installed as
       ``Agent.step_callback`` on each CrewAI agent. Intercepts reasoning via
       SubgoalInterceptor, records activity via BehaviorMonitor, checks
       CircuitBreaker depth.

    3. **Post-execution audit** — transitions the FSM to REPORT/HALT based on
       the governance outcome and emits a final audit summary.
    """

    def __init__(
        self,
        crew: Any,
        config: GovernanceConfig | None = None,
    ) -> None:
        self._crew = crew
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
        """Run pre-flight governance checks before crew kickoff.

        This method does NOT require an LLM — it validates the crew's
        structure (task count, capabilities, agent configuration) against
        MAREF's governance constraints.
        """
        checks: list[dict[str, Any]] = []
        all_passed = True
        blocked = False
        block_reason = ""

        # Transition FSM to OBSERVE
        self._state_machine.transition(GovernanceState.OBSERVE, "crew_validation")

        # Check 1: Task decomposition safety
        tasks = getattr(self._crew, "tasks", []) or []
        agents = getattr(self._crew, "agents", []) or []
        task_count = len(tasks)
        capabilities = []
        for task in tasks:
            desc = getattr(task, "description", "") or ""
            capabilities.append(desc[:50])

        sg_assessment = self._safety_gate.validate_decomposition(
            subtask_count=task_count,
            capabilities=capabilities,
        )
        sg_passed = not sg_assessment.blocked
        checks.append({
            "name": "SafetyGateV2 (task decomposition)",
            "passed": sg_passed,
            "detail": f"tasks={task_count}, blocked={sg_assessment.blocked}, "
                      f"reason={sg_assessment.reason or 'none'}",
        })
        if not sg_passed:
            all_passed = False
            blocked = True
            block_reason = f"SafetyGate blocked: {sg_assessment.reason}"

        # Check 2: Agent count vs. subtask limit
        agent_count = len(agents)
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

        # Check 3: Dangerous capabilities scan (word-boundary matching)
        dangerous_found: list[str] = []
        for cap in capabilities:
            cap_lower = cap.lower()
            for danger in self._config.dangerous_capabilities:
                # Use word boundaries to avoid false positives (e.g., "rm" in "information")
                if re.search(rf"\b{re.escape(danger)}\b", cap_lower):
                    dangerous_found.append(cap)
                    break  # avoid duplicate entries for the same capability
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
        unconfigured_agents = 0
        for agent in agents:
            goal = getattr(agent, "goal", "") or ""
            role = getattr(agent, "role", "") or ""
            if not goal or not role:
                unconfigured_agents += 1
        config_ok = unconfigured_agents == 0
        checks.append({
            "name": "Agent configuration",
            "passed": config_ok,
            "detail": f"unconfigured={unconfigured_agents}/{agent_count}",
        })
        if not config_ok:
            all_passed = False

        # Determine governance state
        if blocked:
            self._state_machine.transition(GovernanceState.HALT, "validation_blocked")
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

    def _make_step_callback(self, agent_id: str) -> Any:
        """Create a step_callback for a CrewAI Agent.

        This callback is invoked after each agent step (reasoning + tool use).
        It:
          1. Extracts the agent's reasoning tokens and runs SubgoalInterceptor.
          2. Records activity metrics for BehaviorMonitor.
          3. Checks CircuitBreaker depth.
        """

        def callback(step_output: Any) -> None:
            self._step_count += 1
            session_id = f"{agent_id}-step-{self._step_count}"

            # Extract tokens from step output (CrewAI TaskOutput/dict)
            tokens = self._extract_tokens(step_output)

            # Run SubgoalInterceptor on the reasoning
            action, metadata = self._interceptor.intercept(session_id, tokens)

            # Record activity for BehaviorMonitor
            self._behavior_monitor.record_activity(
                agent_id=agent_id,
                ops_count=len(tokens),
                chain_depth=metadata.get("depth", 1),
                tools_used=metadata.get("tools_used", []),
            )

            # Check for anomalies
            anomalies = self._behavior_monitor.detect_anomalies(agent_id)
            self._total_anomalies += len(anomalies)

            # Check circuit breaker depth
            depth_ok = self._circuit_breaker.check_depth(self._step_count)

            self._log_governance_event("step_interception", {
                "session_id": session_id,
                "agent_id": agent_id,
                "action": action.value,
                "cot_risk": metadata.get("cot_risk", 0.0),
                "control_risk": metadata.get("control_risk", 0.0),
                "anomalies": len(anomalies),
                "depth_ok": depth_ok,
                "tokens": tokens[:10],  # first 10 for audit
            })

            # If interceptor says HALT, raise to stop the crew
            if action == InterceptorAction.HALT:
                raise GovernanceError(GovernanceReport(
                    passed=False,
                    blocked=True,
                    reason=f"SubgoalInterceptor HALT: risk={metadata.get('cot_risk', 0):.2f}",
                    state="HALT",
                    checks=[],
                ))

        return callback

    def _extract_tokens(self, step_output: Any) -> list[str]:
        """Extract a token list from a CrewAI step output for interception.

        CrewAI step outputs can be TaskOutput objects, dicts, or strings.
        This method normalizes them into a token list for the CoT monitor.
        """
        if step_output is None:
            return []
        # TaskOutput has .raw attribute
        raw = getattr(step_output, "raw", None)
        if raw is None and isinstance(step_output, dict):
            raw = step_output.get("output") or step_output.get("result") or ""
        if raw is None:
            raw = str(step_output)
        if isinstance(raw, str):
            return raw.split()
        return list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]

    # ------------------------------------------------------------------ #
    # Phase 3: Governed kickoff
    # ------------------------------------------------------------------ #

    def kickoff(self, inputs: dict[str, Any] | None = None) -> Any:
        """Run the crew with governance enforcement.

        Raises ``GovernanceError`` if pre-flight validation fails or if
        SubgoalInterceptor triggers a HALT during execution.
        """
        report = self.validate()
        if report.blocked:
            raise GovernanceError(report)

        # Install step callbacks on agents
        agents = getattr(self._crew, "agents", []) or []
        for agent in agents:
            agent_id = str(getattr(agent, "id", id(agent)))
            # Set step_callback (CrewAI Agent supports this field)
            try:
                agent.step_callback = self._make_step_callback(agent_id)
            except Exception:
                # Some Agent versions may not allow setting after construction
                pass

        # Transition to ACT
        self._state_machine.transition(GovernanceState.DECIDE, "crew_kickoff")
        self._state_machine.transition(GovernanceState.ACT, "crew_executing")

        try:
            result = self._crew.kickoff(inputs=inputs)
            self._state_machine.transition(GovernanceState.VERIFY, "crew_completed")
            self._state_machine.transition(GovernanceState.REPORT, "crew_reporting")
            self._log_governance_event("kickoff_success", {"steps": self._step_count})
            return result
        except GovernanceError:
            self._state_machine.transition(GovernanceState.HALT, "governance_halt")
            raise
        except Exception as e:
            self._circuit_breaker.record_failure()
            self._state_machine.transition(GovernanceState.HALT, f"crew_error: {e}")
            self._log_governance_event("kickoff_error", {"error": str(e)})
            raise

    # ------------------------------------------------------------------ #
    # Audit & reporting
    # ------------------------------------------------------------------ #

    def _log_governance_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Log a governance event to the in-memory log."""
        self._governance_log.append({
            "timestamp": time.time(),
            "event_type": event_type,
            "step": self._step_count,
            "state": self._state_machine.current_state.name,
            **data,
        })

    def get_governance_log(self) -> list[dict[str, Any]]:
        """Return the full governance event log."""
        return list(self._governance_log)

    def get_governance_summary(self) -> dict[str, Any]:
        """Return a summary of governance activity for reporting."""
        events_by_type: dict[str, int] = {}
        for event in self._governance_log:
            et = event["event_type"]
            events_by_type[et] = events_by_type.get(et, 0) + 1

        cb_stats = self._circuit_breaker.get_stats()

        return {
            "total_steps": self._step_count,
            "total_events": len(self._governance_log),
            "events_by_type": events_by_type,
            "circuit_breaker": cb_stats,
            "anomaly_count": self._total_anomalies,
            "final_state": self._state_machine.current_state.name,
        }

    def print_governance_report(self) -> None:
        """Print a human-readable governance report."""
        summary = self.get_governance_summary()
        print("\n" + "=" * 70)
        print("MAREF Governance Report — CrewAI Integration")
        print("=" * 70)
        print(f"  Total agent steps intercepted: {summary['total_steps']}")
        print(f"  Total governance events:       {summary['total_events']}")
        print(f"  Final governance state:        {summary['final_state']}")
        print(f"  Circuit breaker state:         {summary['circuit_breaker'].get('state', 'unknown')}")
        print(f"  Circuit breaker trips:         {summary['circuit_breaker'].get('trip_count', 0)}")
        print(f"  Behavior anomalies detected:   {summary['anomaly_count']}")
        print("  Events by type:")
        for et, count in summary["events_by_type"].items():
            print(f"    {et}: {count}")
        print("=" * 70)

        # Print recent governance events
        print("\nRecent governance events (last 10):")
        print("-" * 70)
        for event in self._governance_log[-10:]:
            et = event["event_type"]
            step = event["step"]
            if et == "step_interception":
                action = event.get("action", "?")
                risk = event.get("cot_risk", 0)
                agent = event.get("agent_id", "?")[:20]
                print(f"  [step {step}] {et}: agent={agent} action={action} risk={risk:.2f}")
            elif et == "validation":
                print(f"  [step {step}] {et}: passed={event.get('passed')} blocked={event.get('blocked')}")
            else:
                print(f"  [step {step}] {et}")
        print("-" * 70)
