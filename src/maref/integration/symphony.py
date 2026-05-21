"""
MAREF ↔ Symphony Protocol Adapter

M6.2: Exposes MAREF state machine through Athena's Symphony protocol.
Allows external components (DeerFlow, HITL, Gateway) to discover
current_state, valid_transitions, and governance status via
WORKFLOW.md-compatible protocol messages.

Symphony message types:
- CLAIM: announce capability
- HEARTBEAT: periodic liveness
- STATUS: expose state + transitions
- COMMAND: accept external transition requests
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.constants import ENTROPY_LEVELS, GRAY_CODE
from maref.governance.state_machine import GovernanceStateMachine
from maref.governance.types import GovernanceState


class SymphonyMessageType(Enum):
    CLAIM = "claim"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    COMMAND = "command"
    RESPONSE = "response"
    ERROR = "error"


@dataclass
class SymphonyMessage:
    msg_type: SymphonyMessageType
    source: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    msg_id: str = ""

    def __post_init__(self) -> None:
        if not self.msg_id:
            self.msg_id = f"{self.source}-{int(self.timestamp * 1000)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "type": self.msg_type.value,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SymphonyMessage:
        return cls(
            msg_id=d.get("msg_id", ""),
            msg_type=SymphonyMessageType(d["type"]),
            source=d["source"],
            timestamp=d.get("timestamp", time.time()),
            payload=d.get("payload", {}),
        )


class SymphonyAdapter:
    """
    Symphony protocol adapter for MAREF governance state machine.

    Exposes:
    - current_state and entropy level
    - valid_transitions (with Gray code constraints)
    - audit trail access
    - transition command acceptance

    Athena components connect via this adapter to read and influence
    MAREF's governance state.
    """

    def __init__(
        self,
        state_machine: GovernanceStateMachine,
        source_id: str = "maref-governance",
    ) -> None:
        self._sm = state_machine
        self._source_id = source_id
        self._capabilities = [
            "maref.state.observe",
            "maref.state.analyze",
            "maref.state.evaluate",
            "maref.state.decide",
            "maref.state.act",
            "maref.state.verify",
            "maref.state.stabilize",
            "maref.state.report",
            "maref.governance.force_stabilize",
            "maref.audit.read",
        ]

    def build_claim(self) -> SymphonyMessage:
        return SymphonyMessage(
            msg_type=SymphonyMessageType.CLAIM,
            source=self._source_id,
            payload={
                "capabilities": self._capabilities,
                "states": [s.name for s in GovernanceState],
                "protocol_version": "1.0",
            },
        )

    def build_heartbeat(self) -> SymphonyMessage:
        return SymphonyMessage(
            msg_type=SymphonyMessageType.HEARTBEAT,
            source=self._source_id,
            payload={
                "state": self._sm.current_state.name,
                "entropy": self._sm.current_entropy,
                "gray_code": GRAY_CODE[self._sm.current_state.value],
                "is_terminal": self._sm.current_state == GovernanceState.HALT,
            },
        )

    def build_status(self) -> SymphonyMessage:
        transitions = self._sm.get_valid_next_states()
        return SymphonyMessage(
            msg_type=SymphonyMessageType.STATUS,
            source=self._source_id,
            payload={
                "current_state": self._sm.current_state.name,
                "gray_code": GRAY_CODE[self._sm.current_state.value],
                "entropy": self._sm.current_entropy,
                "entropy_trend": self._sm.get_entropy_trend(),
                "valid_transitions": [
                    {
                        "target": t.name,
                        "gray_code": GRAY_CODE[t.value],
                        "entropy": ENTROPY_LEVELS[t.value],
                    }
                    for t in transitions
                ],
                "is_terminal": self._sm.current_state == GovernanceState.HALT,
            },
        )

    def handle_command(self, msg: SymphonyMessage) -> SymphonyMessage:
        command = msg.payload.get("command", "")
        target_name = msg.payload.get("target_state", "")

        if command == "transition":
            try:
                target = GovernanceState[target_name]
                ok = self._sm.transition(
                    target,
                    reason=msg.payload.get("reason", "symphony_command"),
                )
                return SymphonyMessage(
                    msg_type=SymphonyMessageType.RESPONSE,
                    source=self._source_id,
                    payload={
                        "success": ok,
                        "current_state": self._sm.current_state.name,
                        "error": None if ok else "transition_rejected",
                    },
                )
            except KeyError:
                return SymphonyMessage(
                    msg_type=SymphonyMessageType.ERROR,
                    source=self._source_id,
                    payload={
                        "error": f"unknown_target_state: {target_name}",
                        "valid_states": [s.name for s in GovernanceState],
                    },
                )

        elif command == "force_stabilize":
            ok = self._sm.force_stabilize(
                reason=msg.payload.get("reason", "symphony_command")
            )
            return SymphonyMessage(
                msg_type=SymphonyMessageType.RESPONSE,
                source=self._source_id,
                payload={
                    "success": ok,
                    "current_state": self._sm.current_state.name,
                },
            )

        else:
            return SymphonyMessage(
                msg_type=SymphonyMessageType.ERROR,
                source=self._source_id,
                payload={
                    "error": f"unknown_command: {command}",
                    "valid_commands": ["transition", "force_stabilize"],
                },
            )

    def export_workflow_md(self) -> str:
        sections: list[str] = []
        sections.append("# MAREF Governance — Symphony WORKFLOW.md")
        sections.append("")
        sections.append(f"**source**: `{self._source_id}`")
        sections.append(f"**current_state**: `{self._sm.current_state.name}`")
        sections.append(f"**entropy**: `{self._sm.current_entropy}`")
        sections.append("")
        sections.append("## Valid Transitions")
        sections.append("")
        sections.append("| From | To | Gray Code Δ | Entropy Δ |")
        sections.append("|------|----|-------------|-----------|")

        from_state = self._sm.current_state
        for target in self._sm.get_valid_next_states():
            if self._sm.can_transition(target):
                gc_delta_int = 0
                from_gc_bits = GRAY_CODE.get(from_state.value, (0, 0, 0, 0))
                to_gc_bits = GRAY_CODE.get(target.value, (0, 0, 0, 0))
                for a, b in zip(from_gc_bits, to_gc_bits, strict=False):
                    if a != b:
                        gc_delta_int += 1
                ent_delta = ENTROPY_LEVELS.get(target.value, 0) - ENTROPY_LEVELS.get(from_state.value, 0)
                sections.append(
                    f"| {from_state.name} | {target.name} | {gc_delta_int} | "
                    f"{'+' if ent_delta >= 0 else ''}{ent_delta} |"
                )

        sections.append("")
        sections.append("## Capabilities")
        sections.append("")
        for cap in self._capabilities:
            sections.append(f"- `{cap}`")

        return "\n".join(sections)
