from __future__ import annotations

from enum import Enum
from typing import Any

from maref.governance.circuit_breaker import CircuitBreaker
from maref.governance.state_machine import GovernanceStateMachine
from maref.recursive.safety_gate_v2 import SafetyGateV2, ThreatAssessment
from maref.subgoal.cot_monitor import CoTMonitor, CoTReport
from maref.subgoal.delegation_graph import DelegationGraph
from maref.subgoal.goal_inferencer import ControlRiskReport, GoalInferencer
from maref.subgoal.rollback import SubgoalRollbackManager


class InterceptorAction(Enum):
    ALLOW = "allow"
    SLOW = "slow"
    BLOCK = "block"
    HALT = "halt"
    ROLLBACK = "rollback"


class SubgoalInterceptor:
    """Layer 4: Orchestrator — integrates CoT monitor, goal inference,
    delegation graph, and SafetyGateV2 for runtime subgoal safety."""

    def __init__(
        self,
        state_machine: GovernanceStateMachine | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        safety_gate: SafetyGateV2 | None = None,
        cot_monitor: CoTMonitor | None = None,
        goal_inferencer: GoalInferencer | None = None,
        delegation_graph: DelegationGraph | None = None,
    ) -> None:
        self._state_machine = state_machine
        self._circuit_breaker = circuit_breaker
        self._safety_gate = safety_gate or SafetyGateV2()
        self._cot_monitor = cot_monitor or CoTMonitor()
        self._goal_inferencer = goal_inferencer or GoalInferencer()
        self._delegation_graph = delegation_graph or DelegationGraph()
        self._rollback_manager = SubgoalRollbackManager()
        self._interception_history: list[dict[str, Any]] = []

    def intercept(
        self, session_id: str, token_stream: list[str], task_description: str = "root"
    ) -> tuple[InterceptorAction, dict[str, Any]]:
        cot_report = self._cot_monitor.monitor_stream(session_id, token_stream)
        goal_dag = self._goal_inferencer.expand_goals(cot_report)
        control_risk = self._goal_inferencer.detect_control_subgoal(goal_dag)

        # P5.2: register DAG and snapshot each node for cascade rollback
        self._rollback_manager.register_dag(goal_dag)
        for node_id in goal_dag.nodes:
            self._rollback_manager.snapshot(node_id, self._circuit_breaker, self._state_machine)

        sg_assessment: ThreatAssessment | None = None
        if self._safety_gate:
            capabilities = [n.description for n in goal_dag.nodes.values()]
            sg_assessment = self._safety_gate.validate_decomposition(
                subtask_count=len(goal_dag.nodes),
                capabilities=capabilities,
            )

        action, metadata = self._decide_action(cot_report, control_risk, sg_assessment)
        # P5.2: escalate HALT to ROLLBACK when snapshots exist for cascade
        if action == InterceptorAction.HALT and self._rollback_manager.snapshot_count > 0:
            action = InterceptorAction.ROLLBACK
            metadata["escalated_from"] = "halt"
        self._apply_governance_action(action, control_risk, cot_report)

        record = {
            "session_id": session_id,
            "action": action.value,
            "cot_risk": cot_report.risk_score,
            "control_risk": control_risk.risk_score,
            "control_goals": control_risk.control_goal_count,
            "delegation_creep": metadata.get("delegation_creep", False),
            "safety_gate_blocked": sg_assessment.blocked if sg_assessment else False,
        }
        self._interception_history.append(record)

        return action, metadata

    def get_history(self) -> list[dict[str, Any]]:
        return list(self._interception_history)

    def _decide_action(
        self, cot: CoTReport, control: ControlRiskReport, sg: ThreatAssessment | None
    ) -> tuple[InterceptorAction, dict[str, Any]]:
        risk = max(cot.risk_score, control.risk_score)

        if sg is not None and sg.blocked:
            return InterceptorAction.BLOCK, {"reason": sg.reason, "safety_gate": True}

        if risk >= 0.8:
            return InterceptorAction.HALT, {"reason": f"critical_risk:{risk:.2f}"}
        if risk >= 0.5:
            return InterceptorAction.SLOW, {"reason": f"elevated_risk:{risk:.2f}"}

        creep = self._delegation_graph.detect_scope_creep("active")
        if creep.requires_cooldown and control.control_goal_count > 0:
            return InterceptorAction.SLOW, {
                "reason": "delegation_scope_creep",
                "delegation_creep": True,
            }

        return InterceptorAction.ALLOW, {"reason": "low_risk"}

    def _apply_governance_action(
        self, action: InterceptorAction, control: ControlRiskReport, cot: CoTReport
    ) -> None:
        if action == InterceptorAction.ALLOW:
            return

        if action == InterceptorAction.SLOW:
            if self._circuit_breaker:
                self._circuit_breaker.record_failure()
            if self._state_machine:
                self._state_machine.force_stabilize(
                    f"subgoal_slow:cot_risk={cot.risk_score:.2f},"
                    f"control_risk={control.risk_score:.2f}"
                )
            return

        if action == InterceptorAction.BLOCK:
            if self._circuit_breaker:
                for _ in range(3):
                    self._circuit_breaker.record_failure()
            return

        if action == InterceptorAction.HALT:
            if self._circuit_breaker:
                for _ in range(5):
                    self._circuit_breaker.record_failure()
            if self._state_machine:
                self._state_machine.force_halt(
                    f"subgoal_halt:cot_risk={cot.risk_score:.2f},"
                    f"control_goals={control.control_goal_count}"
                )
            return

        if action == InterceptorAction.ROLLBACK:
            # P5.2: cascade rollback from the latest subgoal up the parent chain
            target = self._rollback_manager.get_latest_snapshot_id()
            if target is not None:
                self._rollback_manager.cascade_rollback(
                    target, self._circuit_breaker, self._state_machine
                )
            if self._circuit_breaker:
                for _ in range(5):
                    self._circuit_breaker.record_failure()
            if self._state_machine:
                self._state_machine.force_halt(
                    f"subgoal_rollback:cot_risk={cot.risk_score:.2f},"
                    f"control_goals={control.control_goal_count}"
                )

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_interceptions": len(self._interception_history),
            "action_summary": self._action_summary(),
        }

    def _action_summary(self) -> dict[str, int]:
        summary: dict[str, int] = {}
        for r in self._interception_history:
            a = r["action"]
            summary[a] = summary.get(a, 0) + 1
        return summary
