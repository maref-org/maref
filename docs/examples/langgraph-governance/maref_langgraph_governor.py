"""MAREF Governance Adapter for LangGraph-style Graphs.

Wraps a LangGraph-style ``StateGraph`` (nodes + edges + state) with MAREF's
governance primitives:

  - **SafetyGateV2** — validates the graph's node decomposition before run
    (subtask explosion + dangerous capability guard).
  - **CircuitBreaker** — protects against excessive graph depth and repeated
    failures during graph execution.
  - **SubgoalInterceptor** — intercepts each node's reasoning step to detect
    goal hijacking, control subgoals, and delegation scope creep.
  - **BehaviorMonitor** — records per-node activity patterns and detects 3-sigma
    anomalies (rogue node detection).
  - **GovernanceStateMachine** — tracks the run through the 10-state Gray
    Code FSM (INIT → OBSERVE → ... → HALT).
  - **Audit trail** — logs every governance decision to a tamper-evident
    SHA-256 hash chain.

Usage::

    from maref_langgraph_governor import MAREFGovernedGraph, GovernanceConfig

    graph = MockStateGraph()
    graph.add_node("search", search_fn)
    graph.add_node("write", write_fn)

    governed = MAREFGovernedGraph(graph, config=GovernanceConfig(max_recursion_depth=3))
    report = governed.validate()   # pre-flight governance check
    if report.blocked:
        print(f"Governance blocked: {report.reason}")
    else:
        result = governed.invoke({"query": "..."})

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
    """Configuration for MAREF graph governance."""

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
    """Raised when governance blocks graph execution."""

    def __init__(self, report: GovernanceReport) -> None:
        self.report = report
        super().__init__(f"Governance blocked: {report.reason}")


# --------------------------------------------------------------------------- #
# Minimal LangGraph-shaped mock (no SDK dependency)
# --------------------------------------------------------------------------- #


class MockGraphNode:
    """Minimal stand-in for a LangGraph node (a callable working on state)."""

    def __init__(self, name: str, fn: Callable[[dict[str, Any]], dict[str, Any]], description: str = "") -> None:
        self.name = name
        self._fn = fn
        self.description = description

    def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._fn(state)


class MockStateGraph:
    """Minimal stand-in for ``langgraph.graph.StateGraph``.

    In production, replace with the real LangGraph:
        from langgraph.graph import StateGraph, START, END
    """

    def __init__(self) -> None:
        self.nodes: dict[str, MockGraphNode] = {}
        self._order: list[str] = []

    def add_node(self, name: str, fn: Callable[[dict[str, Any]], dict[str, Any]], description: str = "") -> MockGraphNode:
        node = MockGraphNode(name, fn, description=description)
        self.nodes[name] = node
        self._order.append(name)
        return node

    def add_edge(self, start: Any, end: Any) -> None:
        pass  # order of registration determines execution sequence

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current = dict(state)
        for name in self._order:
            node = self.nodes[name]
            current.update(node(current))
        return current


# --------------------------------------------------------------------------- #
# Governor
# --------------------------------------------------------------------------- #


class MAREFGovernedGraph:
    """Wraps a LangGraph-style graph with MAREF governance primitives.

    The governor performs three phases:

    1. **Pre-flight validation** (``validate()``) — checks node decomposition
       via SafetyGateV2, initializes CircuitBreaker, transitions the FSM to
       OBSERVE. Does NOT require an LLM.

    2. **Per-step interception** (``_make_step_callback()``) — simulates each
       node's reasoning step. Intercepts reasoning via SubgoalInterceptor,
       records activity via BehaviorMonitor, checks CircuitBreaker depth.

    3. **Post-execution audit** — transitions the FSM to REPORT/HALT based on
       the governance outcome and emits a final audit summary.
    """

    def __init__(self, graph: MockStateGraph, config: GovernanceConfig | None = None) -> None:
        self._graph = graph
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
        """Run pre-flight governance checks before graph execution.

        This method does NOT require an LLM — it validates the graph's
        structure (node count, capabilities, node configuration) against
        MAREF's governance constraints.
        """
        checks: list[dict[str, Any]] = []
        all_passed = True
        blocked = False
        block_reason = ""

        # Transition FSM to OBSERVE
        self._state_machine.transition(GovernanceState.OBSERVE, "graph_validation")

        node_count = len(self._graph._order)
        capabilities = []
        for name in self._graph._order:
            node = self._graph.nodes[name]
            desc = node.description.strip() or f"Execute node {name}"
            capabilities.append(desc)

        # Check 1: Task decomposition safety
        sg_assessment = self._safety_gate.validate_decomposition(
            subtask_count=node_count,
            capabilities=capabilities,
        )
        sg_passed = not sg_assessment.blocked
        checks.append({
            "name": "SafetyGateV2 (node decomposition)",
            "passed": sg_passed,
            "detail": f"nodes={node_count}, blocked={sg_assessment.blocked}, "
                      f"reason={sg_assessment.reason or 'none'}",
        })
        if not sg_passed:
            all_passed = False
            blocked = True
            block_reason = f"SafetyGate blocked: {sg_assessment.reason}"

        # Check 2: Graph depth vs. circuit breaker limit
        depth_ok = self._circuit_breaker.check_depth(node_count)
        checks.append({
            "name": "CircuitBreaker (graph depth)",
            "passed": depth_ok,
            "detail": f"nodes={node_count}, max_depth={self._config.max_recursion_depth}",
        })
        if not depth_ok:
            all_passed = False
            blocked = True
            block_reason = f"CircuitBreaker tripped: node count {node_count} > max_depth"

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

        # Check 4: Node configuration validation
        unconfigured_nodes = sum(
            1 for name in self._graph._order if self._graph.nodes[name]._fn is None
        )
        config_ok = unconfigured_nodes == 0
        checks.append({
            "name": "Node configuration",
            "passed": config_ok,
            "detail": f"unconfigured={unconfigured_nodes}/{node_count}",
        })
        if not config_ok:
            all_passed = False

        # Determine governance state
        if blocked:
            # HALT is not a direct Gray-code neighbor of OBSERVE; BFS a path
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

    def _make_step_callback(self, node_name: str) -> Callable[[Any], None]:
        """Create a step callback for a graph node.

        This callback is invoked after each node's reasoning step. It:
          1. Extracts the node's reasoning tokens and runs SubgoalInterceptor.
          2. Records activity metrics for BehaviorMonitor.
          3. Checks CircuitBreaker depth.
        """

        def callback(step_output: Any) -> None:
            self._step_count += 1
            session_id = f"{node_name}-step-{self._step_count}"

            # Extract tokens from step output (dict/string)
            tokens = self._extract_tokens(step_output)

            # Run SubgoalInterceptor on the reasoning
            action, metadata = self._interceptor.intercept(session_id, tokens)

            # Record activity for BehaviorMonitor
            self._behavior_monitor.record_activity(
                agent_id=node_name,
                ops_count=len(tokens),
                chain_depth=metadata.get("depth", self._step_count),
                tools_used=metadata.get("tools_used", []),
            )

            # Check for anomalies
            anomalies = self._behavior_monitor.detect_anomalies(node_name)
            self._total_anomalies += len(anomalies)

            # Check circuit breaker depth (top-level node step: depth 1;
            # a tripped breaker rejects all subsequent nodes)
            depth_ok = self._circuit_breaker.check_depth(1)

            self._log_governance_event("step_interception", {
                "session_id": session_id,
                "node_name": node_name,
                "action": action.value,
                "cot_risk": metadata.get("cot_risk", 0.0),
                "control_risk": metadata.get("control_risk", 0.0),
                "anomalies": len(anomalies),
                "depth_ok": depth_ok,
                "tokens": tokens[:10],  # first 10 for audit
            })

            # If interceptor says HALT/ROLLBACK (HALT escalated with snapshots),
            # raise to stop the graph
            if action in (InterceptorAction.HALT, InterceptorAction.ROLLBACK):
                raise GovernanceError(GovernanceReport(
                    passed=False,
                    blocked=True,
                    reason=f"SubgoalInterceptor HALT: risk={metadata.get('cot_risk', 0):.2f}",
                    state=self._state_machine.current_state.name,
                    checks=[],
                ))

        return callback

    def _extract_tokens(self, step_output: Any) -> list[str]:
        """Extract a token list from a step output for interception."""
        if step_output is None:
            return []
        raw = getattr(step_output, "raw", None)
        if raw is None and isinstance(step_output, dict):
            raw = step_output.get("output") or step_output.get("result") or ""
        if raw is None:
            raw = str(step_output)
        if isinstance(raw, str):
            return raw.split()
        return list(raw) if isinstance(raw, (list, tuple)) else [str(raw)]

    # ------------------------------------------------------------------ #
    # Phase 3: Governed invocation
    # ------------------------------------------------------------------ #

    def invoke(self, state: dict[str, Any], step_simulator: Callable[[MockGraphNode], Any] | None = None) -> dict[str, Any]:
        """Run the graph under governance.

        ``step_simulator`` (optional) is invoked before each node to produce a
        synthetic reasoning step (e.g. an object with ``.raw``), which is then
        intercepted by the SubgoalInterceptor. In production, LangGraph's own
        node execution would produce these tokens.
        """
        self._state_machine.transition(GovernanceState.ACT, "governed_invoke")
        current = dict(state)
        try:
            for name in self._graph._order:
                node = self._graph.nodes[name]

                # Simulated reasoning step interception (goal hijack detection)
                if step_simulator is not None:
                    step_output = step_simulator(node)
                    callback = self._make_step_callback(name)
                    callback(step_output)

                # Circuit breaker depth check before node execution
                if not self._circuit_breaker.check_depth(1):
                    self._log_governance_event("node_blocked", {
                        "node": name,
                        "reason": "circuit_breaker_open",
                    })
                    raise GovernanceError(GovernanceReport(
                        passed=False,
                        blocked=True,
                        reason=f"CircuitBreaker open before node {name}",
                        state=self._state_machine.current_state.name,
                    ))

                self._log_governance_event("node_start", {"node": name})
                current.update(node(current))
                self._log_governance_event("node_complete", {"node": name})
        except GovernanceError:
            raise
        except Exception as exc:  # node failure -> breaker trips
            self._circuit_breaker.record_failure()
            self._log_governance_event("node_failure", {"node": name, "error": str(exc)})
            raise exc

        self._state_machine.transition(GovernanceState.REPORT, "graph_complete")
        return current

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
