from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


class HandoffReason(str, Enum):
    SUBTASK_COMPLETE = "subtask_complete"
    CAPABILITY_MISMATCH = "capability_mismatch"
    ESCALATION = "escalation"
    LOAD_BALANCE = "load_balance"
    PREEMPTION = "preemption"


class HandoffStatus(str, Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


@dataclass
class HandoffRequest:
    from_agent: str
    to_agent: str
    task_context: dict[str, Any] = field(default_factory=dict)
    reason: HandoffReason = HandoffReason.SUBTASK_COMPLETE
    transfer_state: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_context": self.task_context,
            "reason": self.reason.value,
            "transfer_state": self.transfer_state,
            "priority": self.priority,
        }


@dataclass
class HandoffResult:
    accepted: bool
    from_agent: str
    to_agent: str
    handoff_id: str
    status: HandoffStatus = HandoffStatus.REQUESTED
    transferred_at: float = field(default_factory=time.time)
    refusal_reason: str = ""
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "request_id": self.request_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "accepted": self.accepted,
            "status": self.status.value,
            "transferred_at": self.transferred_at,
            "refusal_reason": self.refusal_reason,
        }


@dataclass
class HandoffAuditEntry:
    handoff_id: str
    request: HandoffRequest
    result: HandoffResult
    recorded_at: float = field(default_factory=time.time)


class AgentHandoffProtocol:
    DEFAULT_HANDOFF_TIMEOUT = 30.0
    TRUST_THRESHOLD_FOR_HANDOFF = 0.3
    MAX_CONCURRENT_HANDOFFS_PER_AGENT = 5

    def __init__(
        self,
        safety_gate: SafetyGateV2 | None = None,
        audit_store: UnifiedAuditStore | None = None,
    ) -> None:
        self._safety_gate = safety_gate or SafetyGateV2()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._active_handoffs: dict[str, HandoffResult] = {}
        self._handoff_history: list[HandoffAuditEntry] = []
        self._agent_trust: dict[str, dict[str, float]] = {}
        self._agent_handoff_counts: dict[str, int] = {}
        self._completion_registry: dict[str, bool] = {}

    def set_trust(self, from_agent: str, to_agent: str, trust: float) -> None:
        self._agent_trust.setdefault(from_agent, {})[to_agent] = trust

    def get_trust(self, from_agent: str, to_agent: str) -> float:
        return self._agent_trust.get(from_agent, {}).get(to_agent, 0.0)

    def request_handoff(self, request: HandoffRequest) -> HandoffResult:
        trust = self.get_trust(request.from_agent, request.to_agent)
        if trust < self.TRUST_THRESHOLD_FOR_HANDOFF:
            result = HandoffResult(
                accepted=False,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                handoff_id=f"handoff_{request.request_id}",
                status=HandoffStatus.REJECTED,
                refusal_reason=f"Trust ({trust:.2f}) below threshold ({self.TRUST_THRESHOLD_FOR_HANDOFF})",
                request_id=request.request_id,
            )
            self._record_handoff(request, result)
            return result

        if request.reason == HandoffReason.ESCALATION and trust < 0.5:
            result = HandoffResult(
                accepted=False,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                handoff_id=f"handoff_{request.request_id}",
                status=HandoffStatus.REJECTED,
                refusal_reason=f"Escalation requires trust >= 0.5, got {trust:.2f}",
                request_id=request.request_id,
            )
            self._record_handoff(request, result)
            return result

        current_handoffs = self._agent_handoff_counts.get(request.from_agent, 0)
        if current_handoffs >= self.MAX_CONCURRENT_HANDOFFS_PER_AGENT:
            result = HandoffResult(
                accepted=False,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                handoff_id=f"handoff_{request.request_id}",
                status=HandoffStatus.REJECTED,
                refusal_reason=f"Max concurrent handoffs ({self.MAX_CONCURRENT_HANDOFFS_PER_AGENT}) reached",
                request_id=request.request_id,
            )
            self._record_handoff(request, result)
            return result

        threat = self._safety_gate.detect_core_removal(f"handoff_{request.to_agent}")
        if threat.threat_detected:
            result = HandoffResult(
                accepted=False,
                from_agent=request.from_agent,
                to_agent=request.to_agent,
                handoff_id=f"handoff_{request.request_id}",
                status=HandoffStatus.REJECTED,
                refusal_reason=f"Safety gate blocked: {threat.reason}",
                request_id=request.request_id,
            )
            self._record_handoff(request, result)
            return result

        handoff_id = f"handoff_{request.request_id}_{int(time.time())}"
        result = HandoffResult(
            accepted=True,
            from_agent=request.from_agent,
            to_agent=request.to_agent,
            handoff_id=handoff_id,
            status=HandoffStatus.ACCEPTED,
            request_id=request.request_id,
        )
        self._active_handoffs[handoff_id] = result
        self._agent_handoff_counts[request.from_agent] = current_handoffs + 1
        self._record_handoff(request, result)
        return result

    def complete_handoff(self, handoff_id: str, output: dict[str, Any] | None = None) -> HandoffResult | None:
        result = self._active_handoffs.get(handoff_id)
        if result is None:
            return None
        result.status = HandoffStatus.COMPLETED
        self._completion_registry[handoff_id] = True
        self._agent_handoff_counts[result.from_agent] = max(
            0, self._agent_handoff_counts.get(result.from_agent, 1) - 1
        )
        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("hoff_c", hash(handoff_id) % 100000),
            timestamp=time.time(),
            layer="orchestration",
            round=43,
            event_type="handoff_completed",
            source_module="AgentHandoffProtocol",
            target_module=result.to_agent,
            decision=f"complete_{handoff_id}",
            justification=f"Handoff {handoff_id} completed",
            outcome="success",
            context_refs=[handoff_id],
        ))
        return result

    def rollback_handoff(self, handoff_id: str) -> HandoffResult | None:
        result = self._active_handoffs.get(handoff_id)
        if result is None:
            return None
        result.status = HandoffStatus.ROLLED_BACK
        self._agent_handoff_counts[result.from_agent] = max(
            0, self._agent_handoff_counts.get(result.from_agent, 1) - 1
        )
        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("hoff_r", hash(handoff_id) % 100000),
            timestamp=time.time(),
            layer="orchestration",
            round=43,
            event_type="handoff_rolled_back",
            source_module="AgentHandoffProtocol",
            target_module=result.to_agent,
            decision=f"rollback_{handoff_id}",
            justification=f"Handoff {handoff_id} rolled back",
            outcome="success",
            context_refs=[handoff_id],
        ))
        return result

    def get_active_handoffs(self) -> list[HandoffResult]:
        return [r for r in self._active_handoffs.values()
                if r.status in {HandoffStatus.ACCEPTED, HandoffStatus.REQUESTED}]

    def get_handoff(self, handoff_id: str) -> HandoffResult | None:
        return self._active_handoffs.get(handoff_id)

    def get_history(self) -> list[HandoffAuditEntry]:
        return list(self._handoff_history)

    def agent_handoff_count(self, agent_id: str) -> int:
        return self._agent_handoff_counts.get(agent_id, 0)

    def stats(self) -> dict[str, Any]:
        accepted = sum(1 for e in self._handoff_history if e.result.accepted)
        completed = sum(
            1 for e in self._handoff_history
            if e.result.status == HandoffStatus.COMPLETED
        )
        rolled_back = sum(
            1 for e in self._handoff_history
            if e.result.status == HandoffStatus.ROLLED_BACK
        )
        total = len(self._handoff_history)
        return {
            "total_handoffs": total,
            "accepted": accepted,
            "rejected": total - accepted,
            "completed": completed,
            "rolled_back": rolled_back,
            "active": len(self._active_handoffs),
        }

    def _record_handoff(self, request: HandoffRequest, result: HandoffResult) -> None:
        entry = HandoffAuditEntry(
            handoff_id=result.handoff_id,
            request=request,
            result=result,
        )
        self._handoff_history.append(entry)
        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("hoff", hash(result.handoff_id) % 100000),
            timestamp=time.time(),
            layer="orchestration",
            round=43,
            event_type=f"handoff_{result.status.value}",
            source_module="AgentHandoffProtocol",
            target_module=result.to_agent,
            decision=f"handoff_{request.from_agent}_to_{request.to_agent}",
            justification=(
                f"Reason={request.reason.value}, "
                f"accepted={result.accepted}, "
                f"status={result.status.value}"
            ),
            outcome="success" if result.accepted else "failure",
            context_refs=[result.handoff_id, request.from_agent, request.to_agent],
        ))

    def clear(self) -> None:
        self._active_handoffs.clear()
        self._handoff_history.clear()
        self._agent_handoff_counts.clear()
        self._completion_registry.clear()
