from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.types import GovernanceState

A2A_PROTOCOL_VERSION = "1.0"


class A2ATaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"


A2A_TO_MAREF_MAP: dict[A2ATaskState, GovernanceState] = {
    A2ATaskState.SUBMITTED: GovernanceState.INIT,
    A2ATaskState.WORKING: GovernanceState.ACT,
    A2ATaskState.INPUT_REQUIRED: GovernanceState.ANALYZE,
    A2ATaskState.COMPLETED: GovernanceState.REPORT,
    A2ATaskState.CANCELED: GovernanceState.HALT,
    A2ATaskState.FAILED: GovernanceState.HALT,
    A2ATaskState.REJECTED: GovernanceState.HALT,
}

MAREF_TO_A2A_MAP: dict[GovernanceState, A2ATaskState] = {
    GovernanceState.INIT: A2ATaskState.SUBMITTED,
    GovernanceState.OBSERVE: A2ATaskState.WORKING,
    GovernanceState.ANALYZE: A2ATaskState.WORKING,
    GovernanceState.EVALUATE: A2ATaskState.INPUT_REQUIRED,
    GovernanceState.DECIDE: A2ATaskState.WORKING,
    GovernanceState.ACT: A2ATaskState.WORKING,
    GovernanceState.VERIFY: A2ATaskState.WORKING,
    GovernanceState.STABILIZE: A2ATaskState.WORKING,
    GovernanceState.REPORT: A2ATaskState.COMPLETED,
    GovernanceState.HALT: A2ATaskState.FAILED,
}


@dataclass
class A2ASkillDefinition:
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])


@dataclass
class A2ATaskContext:
    task_id: str
    description: str
    a2a_state: A2ATaskState
    maref_state: GovernanceState
    context: dict[str, Any]
    created_at: float
    updated_at: float


@dataclass
class DelegatedTask:
    task_id: str
    target_agent_url: str
    delegated_at: float
    status: A2ATaskState = A2ATaskState.SUBMITTED


A2A_AGENT_CARD_SCHEMA = {
    "type": "object",
    "required": ["name", "description", "version", "url", "skills"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "version": {"type": "string"},
        "url": {"type": "string", "format": "uri"},
        "protocolVersion": {"type": "string"},
        "capabilities": {
            "type": "object",
            "properties": {
                "streaming": {"type": "boolean"},
                "pushNotifications": {"type": "boolean"},
                "stateTransitionHistory": {"type": "boolean"},
            },
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "description"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "inputModes": {"type": "array", "items": {"type": "string"}},
                    "outputModes": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "defaultInputModes": {"type": "array", "items": {"type": "string"}},
        "defaultOutputModes": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_agent_card_json(card: dict[str, Any]) -> bool:
    if not isinstance(card, dict):
        return False
    required = ["name", "description", "version", "url", "skills"]
    for key in required:
        if key not in card:
            return False
    if not isinstance(card["skills"], list):
        return False
    for skill in card["skills"]:
        if not isinstance(skill, dict):
            return False
        for skill_key in ["id", "name", "description"]:
            if skill_key not in skill:
                return False
    return True


def map_a2a_to_maref(a2a_state: A2ATaskState) -> GovernanceState:
    if a2a_state not in A2A_TO_MAREF_MAP:
        raise ValueError(f"Unknown A2A task state: {a2a_state}")
    return A2A_TO_MAREF_MAP[a2a_state]


def map_maref_to_a2a(maref_state: GovernanceState) -> A2ATaskState:
    if maref_state not in MAREF_TO_A2A_MAP:
        raise ValueError(f"Unknown MAREF governance state: {maref_state}")
    return MAREF_TO_A2A_MAP[maref_state]
