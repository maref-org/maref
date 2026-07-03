"""Life State Sandbox — execution isolation and permission control.

C37: Execution isolation for life state entities with permission matrix and behavior monitoring.
"""

from __future__ import annotations

import shlex
import time
from abc import ABC, abstractmethod
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


class SandboxBackend(ABC):
    """平台沙箱后端抽象。

    M4 新增：LifeStateSandbox 通过 backend 参数注入平台特定实现。
    - macOS: SandboxExecBackend (M2)
    - Linux: SeccompFilter (M3)
    - 默认: MemorySandboxBackend (纯内存,向后兼容)
    """

    @abstractmethod
    def execute_sandboxed(self, command: list[str], policy: Any = None) -> dict[str, Any]:
        """在沙箱中执行命令。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """后端是否可用。"""
        ...


class MemorySandboxBackend(SandboxBackend):
    """纯内存沙箱后端 — 默认向后兼容实现。"""

    def execute_sandboxed(self, command: list[str], policy: Any = None) -> dict[str, Any]:
        # sandboxed=False 表示"未真正沙箱化",但 allowed=True 表示"允许执行"
        # LifeStateSandbox.execute 仅在 blocked=True 时阻断
        return {"status": "simulated", "command": command, "blocked": False}

    def is_available(self) -> bool:
        return True


class LifeStateSandbox:
    """Sandbox for isolating life state entity execution.

    Provides:
      - Permission matrix per entity
      - Behavior monitoring and auditing
      - Access control enforcement
      - Platform-specific sandbox backend (M4)
    """

    def __init__(self, backend: SandboxBackend | None = None) -> None:
        self._matrices: dict[str, PermissionMatrix] = {}
        self._audit_log: list[SandboxAuditEntry] = []
        self._backend = backend or MemorySandboxBackend()

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
        """执行状态操作。

        M4: 若 backend 可用,将命令传递给沙箱后端执行。
        若后端阻断,记录阻断审计并返回阻断状态。
        """
        self._audit(state_id, SandboxAction.EXECUTION_STARTED, operation)

        if self._backend.is_available():
            # 使用 shlex.split 正确处理引号包裹的参数
            try:
                cmd = shlex.split(operation)
            except ValueError:
                # shlex 解析失败 (如不匹配的引号) — 回退到简单 split
                cmd = operation.split()
            backend_result = self._backend.execute_sandboxed(cmd)
            # 仅当 backend 明确返回 blocked=True 时才阻断
            if backend_result.get("blocked", False):
                self._audit(state_id, SandboxAction.ACCESS_DENIED, f"sandbox blocked: {operation}")
                return {
                    "state_id": state_id,
                    "operation": operation,
                    "status": "blocked",
                    "reason": "sandbox policy violation",
                }

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
            1
            for e in self._audit_log
            if e.state_id == state_id and e.action == SandboxAction.ACCESS_DENIED
        )

    def clear_audit(self) -> None:
        self._audit_log.clear()

    def to_dict(self) -> dict[str, Any]:
        return {
            "registered_count": len(self._matrices),
            "audit_count": len(self._audit_log),
        }
