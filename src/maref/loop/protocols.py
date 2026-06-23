from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopStopReason(Enum):
    MAX_ROUNDS = "max_rounds"
    CONVERGED = "converged"
    CIRCUIT_BREAKER = "circuit_breaker"
    TOKEN_EXHAUSTED = "token_exhausted"
    TIME_EXHAUSTED = "time_exhausted"
    COVERAGE_MET = "coverage_met"
    NO_NOVELTY = "no_novelty"
    USER_ENDED = "user_ended"
    SENTIMENT_TRIP = "sentiment_trip"
    REPETITION_TRIP = "repetition_trip"
    MANUAL_STOP = "manual_stop"
    UNKNOWN = "unknown"


class ToolPermission(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    CREATE = "create"
    DENY = "deny"


@dataclass
class ToolBoundary:
    allowed_domains: list[str] = field(default_factory=list)
    permissions: dict[str, ToolPermission] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "permissions": {k: v.value for k, v in self.permissions.items()},
        }

    @classmethod
    def code_generation(cls) -> ToolBoundary:
        return cls(
            allowed_domains=["filesystem", "test_framework", "lint", "git"],
            permissions={
                "filesystem": ToolPermission.WRITE,
                "test_framework": ToolPermission.EXECUTE,
                "lint": ToolPermission.EXECUTE,
                "git": ToolPermission.READ,
            },
        )

    @classmethod
    def read_only(cls) -> ToolBoundary:
        return cls(
            allowed_domains=["search", "database", "filesystem", "llm"],
            permissions={
                "search": ToolPermission.READ,
                "database": ToolPermission.READ,
                "filesystem": ToolPermission.READ,
                "llm": ToolPermission.EXECUTE,
            },
        )

    @classmethod
    def customer_service(cls) -> ToolBoundary:
        return cls(
            allowed_domains=["knowledge_base", "crm", "ticketing", "llm", "sentiment"],
            permissions={
                "knowledge_base": ToolPermission.READ,
                "crm": ToolPermission.WRITE,
                "ticketing": ToolPermission.CREATE,
                "llm": ToolPermission.EXECUTE,
                "sentiment": ToolPermission.EXECUTE,
            },
        )


@dataclass
class EvaluationResult:
    score: float = 0.0
    errors: list[str] = field(default_factory=list)
    improvement: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Discovery:
    content: str
    source_round: int = 0
    novelty: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass
class ExplorationResult:
    discoveries: list[Discovery] = field(default_factory=list)
    novelty_scores: list[float] = field(default_factory=list)
    coverage: float = 0.0
    diversity_histogram: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    turn_id: int = 0
    user_input: str = ""
    agent_response: str = ""
    sentiment_score: float = 0.0
    intent_match: bool = False
    knowledge_match: float = 0.0
    response_time_ms: int = 0
    requires_escalation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSummary:
    turns: list[TurnResult] = field(default_factory=list)
    total_turns: int = 0
    resolved: bool = False
    user_satisfaction: float = 0.0
    escalation_count: int = 0
    compliance_issues: list[str] = field(default_factory=list)


@dataclass
class AgentResponse:
    content: str = ""
    end_conversation: bool = False
    escalate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
