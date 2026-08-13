from __future__ import annotations

import json
from typing import Any

from maref.governance import GovernanceStateMachine
from maref.governance.audit import AuditLogger
from maref.governance.types import GovernanceState
from maref.loop.base import LoopBase, LoopResult
from maref.loop.protocols import ToolPermission
from maref.security.trust_boundary import TrustBoundaryManager


class LoopGovernanceBridge:
    def __init__(
        self,
        state_machine: GovernanceStateMachine | None = None,
        audit_logger: AuditLogger | None = None,
        trust_boundary_manager: TrustBoundaryManager | None = None,
    ):
        self._state_machine = state_machine or GovernanceStateMachine()
        self._audit_logger = audit_logger
        self._trust_boundary_manager = trust_boundary_manager

    @property
    def state_machine(self) -> GovernanceStateMachine:
        return self._state_machine

    async def run_governed(
        self,
        loop: LoopBase,
        loop_input: Any,
        task_id: str = "",
    ) -> LoopResult[Any]:
        self._state_machine.transition(
            GovernanceState.OBSERVE,
            f"governed_loop_start:{task_id}",
        )

        if self._audit_logger:
            self._audit_logger.log(
                event_type="governed_loop_start",
                actor="loop_bridge",
                action="run_governed",
                details=json.dumps(
                    {
                        "task_id": task_id,
                        "loop_type": type(loop).__name__,
                        "tool_boundary": loop.tool_boundary.to_dict(),
                    }
                ),
            )

        self._state_machine.transition(
            GovernanceState.ANALYZE,
            "governed_loop_analyze",
        )
        self._state_machine.transition(
            GovernanceState.EVALUATE,
            "governed_loop_evaluate",
        )
        self._state_machine.transition(
            GovernanceState.DECIDE,
            "governed_loop_decide",
        )
        self._state_machine.transition(
            GovernanceState.ACT,
            "governed_loop_execute",
        )

        if not self._is_tool_boundary_allowed(loop):
            raise RuntimeError(
                f"TrustBoundary violation: loop {type(loop).__name__} "
                f"tool permission {loop.tool_boundary.permissions} "
                "not compatible with current governance state"
            )

        result = await loop.run(loop_input)

        self._state_machine.transition(
            GovernanceState.VERIFY,
            f"governed_loop_verify:{task_id}",
        )
        self._state_machine.transition(
            GovernanceState.STABILIZE,
            f"governed_loop_stabilize:{task_id}",
        )
        self._state_machine.transition(
            GovernanceState.REPORT,
            f"governed_loop_complete:{task_id}",
        )
        self._state_machine.transition(
            GovernanceState.HALT,
            f"governed_loop_halt:{task_id}",
        )

        if self._audit_logger:
            self._audit_logger.log(
                event_type="governed_loop_complete",
                actor="loop_bridge",
                action="run_governed",
                details=json.dumps(
                    {
                        "task_id": task_id,
                        "stop_reason": result.stop_reason.value,
                        "rounds": result.rounds_completed,
                        "final_state": self._state_machine.current_state.name,
                    }
                ),
            )

        return result

    def _is_tool_boundary_allowed(self, loop: LoopBase) -> bool:
        perm_values = set(loop.tool_boundary.permissions.values())
        current_state = self._state_machine.current_state
        if not perm_values:
            return True
        if current_state == GovernanceState.VERIFY:
            return ToolPermission.READ in perm_values
        if current_state in {
            GovernanceState.ACT,
            GovernanceState.EVALUATE,
        }:
            return (
                ToolPermission.WRITE in perm_values
                or ToolPermission.EXECUTE in perm_values
                or ToolPermission.READ in perm_values
            )
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "state_machine": self._state_machine.snapshot().to_dict(),
        }
