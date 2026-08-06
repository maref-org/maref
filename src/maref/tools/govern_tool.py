from __future__ import annotations

from pydantic import BaseModel, Field

from maref.codegen.tool import (
    Tool,
    ToolContext,
    ToolResult,
    ValidationResult,
)
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class GovernInput(BaseModel):
    action: str = Field(..., description="Governance action: transition, check, snapshot")
    target_state: str | None = Field(None, description="Target state name for transition")
    reason: str = Field("", description="Reason for the governance action")


class GovernOutput(BaseModel):
    current_state: str
    transition_success: bool = False
    entropy: int = 0
    valid_next_states: list[str] = Field(default_factory=list)


class GovernTool(Tool[GovernInput, GovernOutput]):
    name = "Govern"
    description: str = "Trigger governance FSM state transitions and checks"

    def __init__(self, state_machine: GovernanceStateMachine | None = None) -> None:
        self._state_machine = state_machine or GovernanceStateMachine()

    def is_read_only(self, input: GovernInput) -> bool:
        return False

    def is_concurrency_safe(self, input: GovernInput) -> bool:
        return False

    async def validate(self, input: GovernInput) -> ValidationResult:
        valid_actions = {"transition", "check", "snapshot", "stabilize", "halt"}
        if input.action not in valid_actions:
            return ValidationResult(
                is_valid=False,
                message=f"Invalid action '{input.action}'. Valid: {valid_actions}",
            )
        if input.action == "transition" and not input.target_state:
            return ValidationResult(is_valid=False, message="target_state required for transition")
        return ValidationResult(is_valid=True)

    async def call(self, input: GovernInput, ctx: ToolContext) -> ToolResult[GovernOutput]:
        if input.action == "transition" and input.target_state:
            target = GovernanceState[input.target_state.upper()]
            success = self._state_machine.transition(target, input.reason)
        elif input.action == "check":
            success = True
        elif input.action == "stabilize":
            success = self._state_machine.force_stabilize(input.reason or "manual_stabilize")
        elif input.action == "halt":
            success = self._state_machine.force_halt(input.reason or "manual_halt")
        else:
            success = True

        return ToolResult(
            data=GovernOutput(
                current_state=self._state_machine.current_state.name,
                transition_success=success,
                entropy=self._state_machine.current_entropy,
                valid_next_states=[s.name for s in self._state_machine.valid_next_states],
            )
        )
