"""GaaS Billing MVP — usage metering and quota enforcement.

Tracks per-tenant usage for governance checks, HITL events, and audit storage.
Enforces quota limits and generates simple billing records.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageRecord:
    """A single usage record."""

    tenant_id: str
    resource: str  # "govern_check", "hitl_request", "audit_storage_mb"
    quantity: int
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BillingRecord:
    """Aggregated billing record for a billing period."""

    tenant_id: str
    period_start: float
    period_end: float
    items: dict[str, int] = field(default_factory=dict)
    total_quantity: int = 0


class BillingService:
    """Simple usage metering and billing service.

    Production should integrate with Stripe/Paddle for payment processing.
    """

    def __init__(self) -> None:
        self._records: list[UsageRecord] = []
        self._tenant_usage: dict[str, dict[str, int]] = {}

    def record(
        self,
        tenant_id: str,
        resource: str,
        quantity: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record usage for a tenant."""
        record = UsageRecord(
            tenant_id=tenant_id,
            resource=resource,
            quantity=quantity,
            metadata=metadata or {},
        )
        self._records.append(record)

        if tenant_id not in self._tenant_usage:
            self._tenant_usage[tenant_id] = {}
        self._tenant_usage[tenant_id][resource] = (
            self._tenant_usage[tenant_id].get(resource, 0) + quantity
        )

    def get_usage(self, tenant_id: str, resource: str | None = None) -> dict[str, int] | int:
        """Get usage for a tenant. If resource is None, return all resources."""
        usage = self._tenant_usage.get(tenant_id, {})
        if resource is None:
            return dict(usage)
        return usage.get(resource, 0)

    def check_quota(
        self,
        tenant_id: str,
        resource: str,
        quota: int,
    ) -> tuple[bool, int, int]:
        """Check if tenant is within quota. Returns (within_quota, current, limit)."""
        current = self.get_usage(tenant_id, resource)
        if isinstance(current, dict):
            current = sum(current.values())
        return current < quota, current, quota

    def generate_bill(
        self,
        tenant_id: str,
        period_start: float,
        period_end: float,
    ) -> BillingRecord:
        """Generate a billing record for a period."""
        items: dict[str, int] = {}
        for record in self._records:
            if record.tenant_id == tenant_id and period_start <= record.timestamp <= period_end:
                items[record.resource] = items.get(record.resource, 0) + record.quantity

        return BillingRecord(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            items=items,
            total_quantity=sum(items.values()),
        )

    def get_stats(self) -> dict[str, Any]:
        """Get global billing stats."""
        total_records = len(self._records)
        total_tenants = len(self._tenant_usage)
        return {
            "total_records": total_records,
            "total_tenants": total_tenants,
            "tenant_breakdown": {tid: dict(usage) for tid, usage in self._tenant_usage.items()},
        }
