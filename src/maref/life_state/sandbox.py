"""Life State Sandbox — execution isolation and permission control.

C37: Execution isolation for life state entities with permission matrix and behavior monitoring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Permission(str, Enum):
    """Permissions a life state entity may be granted."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    SYSTEM = "system"


class SandboxAction(str, Enum):
    """Actions that can be audited in the sandbox."""

    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    BEACON_SENT = "beacon_sent"


@dataclass
class PermissionMatrix:
    """Permission matrix for a single life state entity."""

    state_id: str
    permissions: set[Permission] = field(default_factory=set)

    def grant(self, permission: Permission) -> None:
        self.permissions.add(permission)

    def revoke(self, permission: Permission) -> None:
        self.permissions.discard(permission)

    def has(self, permission: Permission) -> bool:
        return permission in self.permissions

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "permissions": sorted([p.value for p in self.permissions]),
        }


@dataclass
class SandboxAuditEntry:
    """Audit entry for sandbox actions."""

    state_id: str
    action: SandboxAction
    detail: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "action": self.action.value,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class LifeStateSandbox:
    """Sandbox for isolating life state entity execution.

    Provides:
      - Permission matrix per entity
      - Behavior monitoring and auditing
      - Access control enforcement
    """

    def __init__(self) -> None:
        self._matrices: dict[str, PermissionMatrix] = {}
        self._audit_log: list[SandboxAuditEntry] = []

    def register(self, state_id: str) -> PermissionMatrix:
        matrix = PermissionMatrix(state_id=state_id)
        self._matrices[state_id] = matrix
        return matrix

    def get_matrix(self, state_id: str) -> PermissionMatrix | None:
        return self._matrices.get(state_id)

    def grant(self, state_id: str, permission: Permission) -> None:
        matrix = self._matrices.get(state_id)
        if matrix is None:
            matrix = self.register(state_id)
        matrix.grant(permission)

    def revoke(self, state_id: str, permission: Permission) -> None:
        matrix = self._matrices.get(state_id)
        if matrix is not None:
            matrix.revoke(permission)

    def check(self, state_id: str, permission: Permission) -> bool:
        matrix = self._matrices.get(state_id)
        if matrix is None:
            return False
        allowed = matrix.has(permission)
        action = SandboxAction.ACCESS_GRANTED if allowed else SandboxAction.ACCESS_DENIED
        self._audit(state_id, action, f"{permission.value}")
        return allowed

    def execute(self, state_id: str, operation: str) -> dict[str, Any]:
        self._audit(state_id, SandboxAction.EXECUTION_STARTED, operation)
        result = {"state_id": state_id, "operation": operation, "status": "completed"}
        self._audit(state_id, SandboxAction.EXECUTION_COMPLETED, operation)
        return result

    def _audit(self, state_id: str, action: SandboxAction, detail: str) -> None:
        entry = SandboxAuditEntry(
            state_id=state_id,
            action=action,
            detail=detail,
        )
        self._audit_log.append(entry)

    def get_audit_log(self, state_id: str | None = None) -> list[SandboxAuditEntry]:
        if state_id is None:
            return list(self._audit_log)
        return [e for e in self._audit_log if e.state_id == state_id]

    def get_denied_count(self, state_id: str) -> int:
        return sum(
            1 for e in self._audit_log
            if e.state_id == state_id and e.action == SandboxAction.ACCESS_DENIED
        )

    def clear_audit(self) -> None:
        self._audit_log.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "registered_count": len(self._matrices),
            "audit_count": len(self._audit_log),
        }
