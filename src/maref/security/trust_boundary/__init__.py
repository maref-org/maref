from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from maref.governance.audit import AuditLogger
    from maref.governance.circuit_breaker import CircuitBreaker


class TrustPolicy(str, Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    PERMISSIVE = "permissive"


class BoundaryEventType(str, Enum):
    CROSS_DOMAIN_CALL = "cross_domain_call"
    DELEGATION_REQUEST = "delegation_request"
    TRUST_EXPIRED = "trust_expired"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class BoundaryEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: BoundaryEventType = BoundaryEventType.CROSS_DOMAIN_CALL
    source_domain: str = ""
    target_domain: str = ""
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_reverification: bool = True
    risk_score: float = 0.0


@dataclass
class TrustDomain:
    domain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    agents: set[str] = field(default_factory=set)
    policy: TrustPolicy = TrustPolicy.MODERATE
    parent_domain: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_agent(self, agent_id: str) -> None:
        self.agents.add(agent_id)

    def remove_agent(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            self.agents.discard(agent_id)
            return True
        return False

    def contains_agent(self, agent_id: str) -> bool:
        return agent_id in self.agents


@dataclass
class BoundaryReport:
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_domain: str = ""
    target_domain: str = ""
    events: list[BoundaryEvent] = field(default_factory=list)
    total_crossings: int = 0
    high_risk_count: int = 0
    reverification_required: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_event(self, event: BoundaryEvent) -> None:
        self.events.append(event)
        self.total_crossings += 1
        if event.risk_score >= 0.7:
            self.high_risk_count += 1
        if event.requires_reverification:
            self.reverification_required += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "total_crossings": self.total_crossings,
            "high_risk_count": self.high_risk_count,
            "reverification_required": self.reverification_required,
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "agent_id": e.agent_id,
                    "risk_score": e.risk_score,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in self.events
            ],
            "generated_at": self.generated_at.isoformat(),
        }


class TrustBoundaryManager:
    def __init__(
        self,
        audit_logger: "AuditLogger | None" = None,
        circuit_breaker: "CircuitBreaker | None" = None,
    ) -> None:
        self._domains: dict[str, TrustDomain] = {}
        self._agent_domain_map: dict[str, str] = {}
        self._boundary_events: list[BoundaryEvent] = []
        self._audit_logger = audit_logger
        self._circuit_breaker = circuit_breaker

    def create_domain(
        self,
        name: str,
        policy: TrustPolicy = TrustPolicy.MODERATE,
        parent_domain: str | None = None,
    ) -> TrustDomain:
        domain = TrustDomain(
            name=name,
            policy=policy,
            parent_domain=parent_domain,
        )
        self._domains[domain.domain_id] = domain
        return domain

    def register_agent(self, agent_id: str, domain_id: str) -> bool:
        if domain_id not in self._domains:
            return False
        domain = self._domains[domain_id]
        domain.add_agent(agent_id)
        self._agent_domain_map[agent_id] = domain_id
        return True

    def get_agent_domain(self, agent_id: str) -> str | None:
        return self._agent_domain_map.get(agent_id)

    def check_cross_domain(
        self,
        source_agent_id: str,
        target_agent_id: str,
    ) -> BoundaryEvent | None:
        source_domain = self.get_agent_domain(source_agent_id)
        target_domain = self.get_agent_domain(target_agent_id)

        if source_domain is None or target_domain is None:
            return None

        if source_domain == target_domain:
            return None

        source = self._domains.get(source_domain)
        target = self._domains.get(target_domain)
        if source is None or target is None:
            return None

        risk_score = self._calculate_risk(source, target)

        event = BoundaryEvent(
            event_type=BoundaryEventType.CROSS_DOMAIN_CALL,
            source_domain=source_domain,
            target_domain=target_domain,
            agent_id=target_agent_id,
            risk_score=risk_score,
            requires_reverification=risk_score >= 0.5 or source.policy == TrustPolicy.STRICT,
        )
        self._boundary_events.append(event)

        # A2.3: 审计日志 + CircuitBreaker 评估
        self._log_cross_domain_event(event, source_agent_id, target_agent_id)
        self._evaluate_circuit_breaker(event)

        return event

    def _calculate_risk(self, source: TrustDomain, target: TrustDomain) -> float:
        risk = 0.0
        if source.policy == TrustPolicy.STRICT:
            risk += 0.3
        if target.policy == TrustPolicy.PERMISSIVE:
            risk += 0.3
        if target.parent_domain != source.domain_id:
            risk += 0.2
        return min(risk, 1.0)

    def _log_cross_domain_event(
        self,
        event: BoundaryEvent,
        source_agent_id: str,
        target_agent_id: str,
    ) -> None:
        """记录跨域调用审计日志 (A2.3)"""
        if self._audit_logger is None:
            return
        self._audit_logger.log(
            event_type="cross_domain_call",
            actor=source_agent_id,
            action="boundary_check",
            details=f"Cross-domain call from {event.source_domain} to {event.target_domain}",
            metadata={
                "target_agent": target_agent_id,
                "risk_score": round(event.risk_score, 3),
                "requires_reverification": event.requires_reverification,
                "source_policy": event.metadata.get("source_policy", ""),
                "target_policy": event.metadata.get("target_policy", ""),
            },
        )

    def _evaluate_circuit_breaker(self, event: BoundaryEvent) -> None:
        """CircuitBreaker 评估高-risk 跨域调用 (A2.3)"""
        if self._circuit_breaker is None:
            return
        if event.risk_score >= 0.7:
            # 高风险跨域调用触发 CircuitBreaker 失败记录
            self._circuit_breaker.record_failure()

    def generate_report(
        self,
        source_domain: str,
        target_domain: str,
    ) -> BoundaryReport:
        events = [
            e for e in self._boundary_events
            if e.source_domain == source_domain and e.target_domain == target_domain
        ]
        report = BoundaryReport(
            source_domain=source_domain,
            target_domain=target_domain,
        )
        for event in events:
            report.add_event(event)
        return report

    def get_domain(self, domain_id: str) -> TrustDomain | None:
        return self._domains.get(domain_id)

    def list_domains(self) -> list[TrustDomain]:
        return list(self._domains.values())