"""Life State Resources — resource awareness and limits.

C36: CPU/memory/IO resource monitoring and quota enforcement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResourceType(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    NETWORK = "network"


@dataclass
class ResourceUsage:
    state_id: str
    resource_type: ResourceType
    used: float
    limit: float
    timestamp: float = field(default_factory=time.time)

    @property
    def percent(self) -> float:
        if self.limit <= 0:
            return 0.0
        return (self.used / self.limit) * 100.0

    def is_over_limit(self) -> bool:
        return self.used > self.limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "resource_type": self.resource_type.value,
            "used": self.used,
            "limit": self.limit,
            "percent": round(self.percent, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class ResourceQuota:
    state_id: str
    cpu_limit: float = 100.0
    memory_limit: float = 1024.0
    io_limit: float = 1000.0
    network_limit: float = 1000.0

    def get_limit(self, resource_type: ResourceType) -> float:
        return {
            ResourceType.CPU: self.cpu_limit,
            ResourceType.MEMORY: self.memory_limit,
            ResourceType.IO: self.io_limit,
            ResourceType.NETWORK: self.network_limit,
        }.get(resource_type, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "cpu_limit": self.cpu_limit,
            "memory_limit": self.memory_limit,
            "io_limit": self.io_limit,
            "network_limit": self.network_limit,
        }


class ResourceMonitor:
    """Monitors resource usage for life state entities."""

    def __init__(self) -> None:
        self._usages: list[ResourceUsage] = []
        self._quotas: dict[str, ResourceQuota] = {}
        self._alerts: list[dict[str, Any]] = []

    def set_quota(self, quota: ResourceQuota) -> None:
        self._quotas[quota.state_id] = quota

    def get_quota(self, state_id: str) -> ResourceQuota | None:
        return self._quotas.get(state_id)

    def record(self, usage: ResourceUsage) -> None:
        self._usages.append(usage)
        if usage.is_over_limit():
            self._alerts.append(
                {
                    "state_id": usage.state_id,
                    "resource_type": usage.resource_type.value,
                    "used": usage.used,
                    "limit": usage.limit,
                    "timestamp": time.time(),
                }
            )

    def get_usage(self, state_id: str, resource_type: ResourceType) -> ResourceUsage | None:
        for u in reversed(self._usages):
            if u.state_id == state_id and u.resource_type == resource_type:
                return u
        return None

    def get_all_usage(self, state_id: str) -> list[ResourceUsage]:
        return [u for u in self._usages if u.state_id == state_id]

    def check_quota(self, state_id: str, resource_type: ResourceType, amount: float) -> bool:
        quota = self._quotas.get(state_id)
        if quota is None:
            return True
        limit = quota.get_limit(resource_type)
        current = self.get_usage(state_id, resource_type)
        current_used = current.used if current else 0.0
        return (current_used + amount) <= limit

    def get_alerts(self) -> list[dict[str, Any]]:
        return list(self._alerts)

    def clear_alerts(self) -> None:
        self._alerts.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "quota_count": len(self._quotas),
            "usage_count": len(self._usages),
            "alert_count": len(self._alerts),
        }
