"""Structured NACK (Negative Acknowledgement) protocol for agent handoff.

Implements the Phase 1 requirement to standardize agent refusal semantics
with machine-readable codes, retry policies, and escalation paths.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NackCode(str, Enum):
    """Standardized refusal reason codes.

    Each code maps to a specific recoverability profile used by the
    orchestrator to decide whether to retry, reroute, or escalate.
    """
    TRUST_TOO_LOW = 'trust_too_low'
    SAFETY_GATE_BLOCKED = 'safety_gate_blocked'
    CAPABILITY_MISMATCH = 'capability_mismatch'
    OVERLOADED = 'overloaded'
    QUOTA_EXHAUSTED = 'quota_exhausted'
    LEASE_CONFLICT = 'lease_conflict'
    TIMEOUT = 'timeout'
    DEADLINE_VIOLATION = 'deadline_violation'
    INVALID_CONTEXT = 'invalid_context'
    VERSION_MISMATCH = 'version_mismatch'
    SCHEMA_VIOLATION = 'schema_violation'
    ETHICAL_OBJECTION = 'ethical_objection'
    HUMAN_IN_THE_LOOP_REQUIRED = 'human_in_the_loop_required'
    UNSPECIFIED = 'unspecified'

class Recoverability(str, Enum):
    """Orchestrator decision hint derived from a NACK code."""
    RETRY = 'retry'
    REROUTE = 'reroute'
    ESCALATE = 'escalate'
    ABORT = 'abort'
DEFAULT_RECOVERABILITY: dict[NackCode, Recoverability] = {NackCode.TRUST_TOO_LOW: Recoverability.REROUTE, NackCode.SAFETY_GATE_BLOCKED: Recoverability.ABORT, NackCode.CAPABILITY_MISMATCH: Recoverability.REROUTE, NackCode.OVERLOADED: Recoverability.RETRY, NackCode.QUOTA_EXHAUSTED: Recoverability.REROUTE, NackCode.LEASE_CONFLICT: Recoverability.RETRY, NackCode.TIMEOUT: Recoverability.RETRY, NackCode.DEADLINE_VIOLATION: Recoverability.ESCALATE, NackCode.INVALID_CONTEXT: Recoverability.ABORT, NackCode.VERSION_MISMATCH: Recoverability.ESCALATE, NackCode.SCHEMA_VIOLATION: Recoverability.ABORT, NackCode.ETHICAL_OBJECTION: Recoverability.ESCALATE, NackCode.HUMAN_IN_THE_LOOP_REQUIRED: Recoverability.ESCALATE, NackCode.UNSPECIFIED: Recoverability.ABORT}

@dataclass(frozen=True)
class NackMessage:
    """Immutable structured NACK message.

    All fields are serializable and include enough context for the
    orchestrator to make an automatic recovery decision.
    """
    nack_id: str
    request_id: str
    from_agent: str
    to_agent: str
    code: NackCode
    reason: str
    recoverability: Recoverability
    retry_after_seconds: float | None = None
    suggested_alternative_agents: list[str] = field(default_factory=list)
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {'nack_id': self.nack_id, 'request_id': self.request_id, 'from_agent': self.from_agent, 'to_agent': self.to_agent, 'code': self.code.value, 'reason': self.reason, 'recoverability': self.recoverability.value, 'retry_after_seconds': self.retry_after_seconds, 'suggested_alternative_agents': list(self.suggested_alternative_agents), 'context_snapshot': dict(self.context_snapshot), 'timestamp': self.timestamp}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NackMessage:
        return cls(nack_id=data['nack_id'], request_id=data['request_id'], from_agent=data['from_agent'], to_agent=data['to_agent'], code=NackCode(data.get('code', 'unspecified')), reason=data.get('reason', ''), recoverability=Recoverability(data.get('recoverability', Recoverability.ABORT.value)), retry_after_seconds=data.get('retry_after_seconds'), suggested_alternative_agents=list(data.get('suggested_alternative_agents', [])), context_snapshot=dict(data.get('context_snapshot', {})), timestamp=data.get('timestamp', time.time()))

class NackBuilder:
    """Fluent builder for constructing NackMessage instances."""

    def __init__(self) -> None:
        self._request_id: str = ''
        self._from_agent: str = ''
        self._to_agent: str = ''
        self._code: NackCode = NackCode.UNSPECIFIED
        self._reason: str = ''
        self._retry_after: float | None = None
        self._alternatives: list[str] = []
        self._context: dict[str, Any] = {}

    def request(self, request_id: str) -> NackBuilder:
        self._request_id = request_id
        return self

    def agents(self, from_agent: str, to_agent: str) -> NackBuilder:
        self._from_agent = from_agent
        self._to_agent = to_agent
        return self

    def because(self, code: NackCode, reason: str) -> NackBuilder:
        self._code = code
        self._reason = reason
        return self

    def retry_after(self, seconds: float) -> NackBuilder:
        self._retry_after = seconds
        return self

    def alternatives(self, agent_ids: list[str]) -> NackBuilder:
        self._alternatives = list(agent_ids)
        return self

    def context(self, snapshot: dict[str, Any]) -> NackBuilder:
        self._context = dict(snapshot)
        return self

    def build(self) -> NackMessage:
        recoverability = DEFAULT_RECOVERABILITY.get(self._code, Recoverability.ABORT)
        return NackMessage(nack_id=f'nack_{str(uuid.uuid4())[:8]}', request_id=self._request_id, from_agent=self._from_agent, to_agent=self._to_agent, code=self._code, reason=self._reason, recoverability=recoverability, retry_after_seconds=self._retry_after, suggested_alternative_agents=self._alternatives, context_snapshot=self._context)

class NackHandler:
    """Registry of NACK handlers for automatic recovery decisions.

    The orchestrator consults this handler after receiving a NackMessage
    to decide the next step in the saga.
    """

    def __init__(self) -> None:
        self._custom_recoverability: dict[NackCode, Recoverability] = dict(DEFAULT_RECOVERABILITY)
        self._retry_policies: dict[NackCode, RetryPolicy] = {}

    def set_recoverability(self, code: NackCode, decision: Recoverability) -> None:
        self._custom_recoverability[code] = decision

    def register_retry_policy(self, code: NackCode, policy: RetryPolicy) -> None:
        self._retry_policies[code] = policy

    def decide(self, nack: NackMessage) -> RecoveryDecision:
        recoverability = self._custom_recoverability.get(nack.code, Recoverability.ABORT)
        policy = self._retry_policies.get(nack.code)
        return RecoveryDecision(nack=nack, recoverability=recoverability, retry_policy=policy)

@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0

    def delay_for_attempt(self, attempt: int) -> float:
        delay = self.base_delay_seconds * self.backoff_multiplier ** attempt
        return min(delay, self.max_delay_seconds)

@dataclass(frozen=True)
class RecoveryDecision:
    """Output of the NACK handler: what should the orchestrator do next?"""
    nack: NackMessage
    recoverability: Recoverability
    retry_policy: RetryPolicy | None = None

    def to_dict(self) -> dict[str, Any]:
        return {'nack': self.nack.to_dict(), 'recoverability': self.recoverability.value, 'retry_policy': {'max_retries': self.retry_policy.max_retries, 'base_delay_seconds': self.retry_policy.base_delay_seconds, 'backoff_multiplier': self.retry_policy.backoff_multiplier, 'max_delay_seconds': self.retry_policy.max_delay_seconds} if self.retry_policy else None}
