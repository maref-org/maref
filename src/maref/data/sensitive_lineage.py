"""SensitiveDataLineage: cross-domain sensitive-data flow tracking (v0.51 W3-S3 / C3).

Tracks how sensitive data (by DataCategory) flows between domain boundaries,
computes the downstream spread of a sensitive asset, and raises circuit-breaker
alerts when a flow enters a domain not authorized for its classification.

Integrates with the TrustBoundaryManager audit trail; a violation opens the
circuit breaker so downstream consumers refuse further sensitive ingestion.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.compliance.data_sovereignty import DataCategory

# Default domain authorization per category — cross-domain flows to domains
# NOT in this set are violations.  Configurable per engine instance.
_DEFAULT_ALLOWED_CROSS_DOMAINS: dict[DataCategory, set[str]] = {
    DataCategory.PUBLIC: {"*"},  # public data may flow anywhere
    DataCategory.INTERNAL: {"analytics", "etl", "reporting"},
    DataCategory.CONFIDENTIAL: {"analytics", "etl"},
    DataCategory.RESTRICTED: {"etl"},
    DataCategory.PERSONAL: {"analytics", "etl"},
    DataCategory.SENSITIVE_PERSONAL: {"analytics"},
    DataCategory.HEALTH: {"analytics", "clinical"},
    DataCategory.FINANCIAL: {"analytics", "finance"},
    DataCategory.CRITICAL_INFRASTRUCTURE: {"ops"},
}

# Domains that always make a flow "internal" — moving within the same domain
# is never a cross-domain violation even if it is not explicitly whitelisted.
_INTERNAL_DOMAINS = {"etl", "analytics", "reporting", "ops", "clinical", "finance", "src", "health"}


class FlowAction(Enum):
    ALLOWED = "allowed"
    VIOLATION = "violation"


@dataclass(frozen=True)
class SensitiveFlowNode:
    """A single sensitive-data transfer between two domains."""

    asset: str
    from_domain: str
    to_domain: str
    category: DataCategory
    action: FlowAction = FlowAction.ALLOWED
    # asset flow continuity: asset X → downstream asset Y
    next_asset: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "from_domain": self.from_domain,
            "to_domain": self.to_domain,
            "category": self.category.value,
            "action": self.action.value,
            "next_asset": self.next_asset,
        }


class SensitiveDataLineage:
    """In-memory graph + policy of sensitive data flow across domains."""

    def __init__(
        self,
        allowed_cross_domains: dict[DataCategory, set[str]] | None = None,
    ) -> None:
        self._allowed = allowed_cross_domains or _DEFAULT_ALLOWED_CROSS_DOMAINS
        self._flows: list[SensitiveFlowNode] = []
        self._downstream: dict[str, set[str]] = defaultdict(set)
        self._violations: int = 0
        self._circuit_breaker_open = False

    def record_flow(
        self, node: SensitiveFlowNode, next_asset: str = ""
    ) -> SensitiveFlowNode:
        """Record a sensitive-data transfer and enforce cross-domain policy.

        ``next_asset`` optionally links this flow to the downstream asset it
        produces, enabling chain-based spread analysis.
        """
        is_internal = node.from_domain == node.to_domain or node.to_domain in _INTERNAL_DOMAINS
        allowed = self._allowed.get(node.category, set())
        permitted = is_internal or "*" in allowed or node.to_domain in allowed

        if permitted:
            recorded = SensitiveFlowNode(
                asset=node.asset,
                from_domain=node.from_domain,
                to_domain=node.to_domain,
                category=node.category,
                action=FlowAction.ALLOWED,
                next_asset=next_asset,
            )
        else:
            recorded = SensitiveFlowNode(
                asset=node.asset,
                from_domain=node.from_domain,
                to_domain=node.to_domain,
                category=node.category,
                action=FlowAction.VIOLATION,
                next_asset=next_asset,
            )
            self._violations += 1
            self._circuit_breaker_open = True

        self._flows.append(recorded)
        if next_asset:
            self._downstream.setdefault(node.asset, set()).add(next_asset)
        return recorded

    def flows(self) -> list[SensitiveFlowNode]:
        return list(self._flows)

    def violation_count(self) -> int:
        return self._violations

    def circuit_breaker_open(self) -> bool:
        return self._circuit_breaker_open

    def audit_alerts(self) -> list[dict[str, Any]]:
        """Return structured alerts for flows that violated the policy."""
        alerts: list[dict[str, Any]] = []
        for flow in self._flows:
            if flow.action == FlowAction.VIOLATION:
                alerts.append(
                    {
                        "event_type": "sensitive_flow_violation",
                        "asset": flow.asset,
                        "category": flow.category.value,
                        "from_domain": flow.from_domain,
                        "to_domain": flow.to_domain,
                        "message": (
                            f"sensitive data {flow.asset!r} ({flow.category.value}) "
                            f"flowed from {flow.from_domain} to unauthorized domain "
                            f"{flow.to_domain}"
                        ),
                    }
                )
        return alerts

    def trace_downstream(self, asset: str) -> set[str]:
        """Spread of the sensitive asset across downstream assets."""
        visited: set[str] = set()
        queue: deque[str] = deque(self._downstream.get(asset, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._downstream.get(node, set()))
        return visited

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": self._violations,
            "circuit_breaker_open": self._circuit_breaker_open,
            "flows": [f.to_dict() for f in self._flows],
        }
