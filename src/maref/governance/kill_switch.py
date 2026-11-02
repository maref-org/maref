"""Kill switch — global / tenant / agent 三级停机。

激活后由 ``GovernedPipeline`` 在路由证据与策略评估之前直接拒绝。
解除必须携带带外 Ed25519 签名授权（一次性 nonce + 有效期），工具调用
路径没有解除入口。

子智能体通过 :meth:`KillSwitch.register_child` 登记血缘；父节点被停机时，
已登记与后续登记的子节点都会被递归阻断，并触发已注册的回退钩子。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.signing.signing_key import ReportSigningKey

logger = logging.getLogger(__name__)

_MAX_EVENTS = 1000
_MAX_CLOCK_SKEW_SECONDS = 60.0


class KillScope(str, Enum):
    GLOBAL = "global"
    TENANT = "tenant"
    AGENT = "agent"


class KillSwitchAuthorizationError(PermissionError):
    """解除授权缺失、伪造、过期或重放。"""


@dataclass(frozen=True)
class KillSwitchEvent:
    timestamp: float
    action: str
    scope: KillScope
    target: str
    reason: str
    actor: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "scope": self.scope.value,
            "target": self.target,
            "reason": self.reason,
            "actor": self.actor,
        }


@dataclass(frozen=True)
class DisengageAuthorization:
    """带外解除授权。``signature`` 为 Ed25519 的 base64 签名。"""

    actor: str
    scope: str
    target: str
    issued_at: float
    nonce: str
    signature: str = ""

    def payload(self) -> bytes:
        data = {
            "action": "kill_switch.disengage",
            "actor": self.actor,
            "scope": self.scope,
            "target": self.target,
            "issued_at": self.issued_at,
            "nonce": self.nonce,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )


@dataclass
class _BlockState:
    global_blocked: bool = False
    tenants: set[str] = field(default_factory=set)
    agents: set[str] = field(default_factory=set)


class KillSwitch:
    """三级停机开关，线程安全。"""

    def __init__(
        self,
        authorizer_keys: dict[str, str] | None = None,
        state_machine: Any | None = None,
        audit_callback: Callable[[KillSwitchEvent], None] | None = None,
        max_authorization_age: float = 300.0,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._authorizer_keys = dict(authorizer_keys or {})
        self._state_machine = state_machine
        self._audit_callbacks: list[Callable[[KillSwitchEvent], None]] = []
        if audit_callback is not None:
            self._audit_callbacks.append(audit_callback)
        self._max_authorization_age = max_authorization_age
        self._now = now
        self._lock = threading.RLock()
        self._state = _BlockState()
        self._children: dict[str, set[str]] = {}
        self._parents: dict[str, set[str]] = {}
        self._block_hooks: list[Callable[[str, str, str], None]] = []
        self._used_nonces: set[str] = set()
        self._events: list[KillSwitchEvent] = []

    # --- 状态查询 ---

    def blocked_scope(self, tenant_id: str, agent_id: str) -> str:
        """返回命中的最高级作用域（global/tenant/agent），未命中为 ``""``。"""
        with self._lock:
            if self._state.global_blocked:
                return KillScope.GLOBAL.value
            if tenant_id and tenant_id in self._state.tenants:
                return KillScope.TENANT.value
            if agent_id and self._is_agent_blocked(agent_id):
                return KillScope.AGENT.value
            return ""

    def is_blocked(self, tenant_id: str, agent_id: str) -> bool:
        return bool(self.blocked_scope(tenant_id, agent_id))

    def blocked_agents(self) -> list[str]:
        """当前被阻断的智能体（含由父节点递归阻断的子节点）。"""
        with self._lock:
            candidates = set(self._state.agents) | set(self._parents)
            return sorted(agent_id for agent_id in candidates if self._is_agent_blocked(agent_id))

    def events(self) -> list[KillSwitchEvent]:
        with self._lock:
            return list(self._events)

    # --- 登记与钩子 ---

    def register_child(self, parent_agent_id: str, child_agent_id: str) -> None:
        """登记父子血缘；父节点已停机时立即阻断并触发回退钩子。"""
        if not parent_agent_id or not child_agent_id:
            raise ValueError("parent_agent_id and child_agent_id are required")
        if parent_agent_id == child_agent_id:
            raise ValueError("an agent cannot be its own parent")
        with self._lock:
            self._children.setdefault(parent_agent_id, set()).add(child_agent_id)
            self._parents.setdefault(child_agent_id, set()).add(parent_agent_id)
            ancestor = self._blocked_ancestor(child_agent_id)
        if ancestor:
            self._run_block_hooks(
                child_agent_id, f"inherited from blocked ancestor {ancestor}", "kill_switch"
            )

    def add_block_hook(self, hook: Callable[[str, str, str], None]) -> None:
        """注册回退钩子：``hook(agent_id, reason, actor)``。"""
        self._block_hooks.append(hook)

    def add_audit_callback(self, callback: Callable[[KillSwitchEvent], None]) -> None:
        if callback not in self._audit_callbacks:
            self._audit_callbacks.append(callback)

    # --- 激活 / 解除 ---

    def engage(
        self,
        scope: KillScope | str,
        target: str,
        reason: str,
        actor: str,
    ) -> KillSwitchEvent:
        scope = KillScope(scope)
        target = self._normalize_target(scope, target)
        new_targets: list[str] = []
        with self._lock:
            if scope is KillScope.GLOBAL:
                self._state.global_blocked = True
            elif scope is KillScope.TENANT:
                self._state.tenants.add(target)
            else:
                self._state.agents.add(target)
                new_targets = [target, *self._descendants(target)]

        if scope is KillScope.GLOBAL:
            self._halt_state_machine(reason, actor)
        for agent_id in new_targets:
            self._run_block_hooks(agent_id, reason, actor)

        return self._emit("engage", scope, target, reason, actor)

    def disengage(
        self,
        scope: KillScope | str,
        target: str,
        reason: str,
        actor: str,
        authorization: DisengageAuthorization | None,
    ) -> bool:
        """带外签名授权后解除；每次授权只能使用一次。"""
        scope = KillScope(scope)
        target = self._normalize_target(scope, target)
        self._verify_authorization(scope, target, actor, authorization)

        with self._lock:
            if scope is KillScope.GLOBAL:
                changed = self._state.global_blocked
                self._state.global_blocked = False
            elif scope is KillScope.TENANT:
                changed = target in self._state.tenants
                self._state.tenants.discard(target)
            else:
                changed = target in self._state.agents
                self._state.agents.discard(target)

        self._emit("disengage", scope, target, reason, actor)
        return changed

    # --- 内部实现 ---

    @staticmethod
    def _normalize_target(scope: KillScope, target: str) -> str:
        if scope is KillScope.GLOBAL:
            return "*"
        if not target:
            raise ValueError(f"target is required for scope={scope.value}")
        return target

    def _is_agent_blocked(self, agent_id: str) -> bool:
        return agent_id in self._state.agents or bool(self._blocked_ancestor(agent_id))

    def _blocked_ancestor(self, agent_id: str) -> str:
        stack = list(self._parents.get(agent_id, ()))
        seen: set[str] = {agent_id}
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            if current in self._state.agents:
                return current
            seen.add(current)
            stack.extend(self._parents.get(current, ()))
        return ""

    def _descendants(self, agent_id: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = {agent_id}
        stack = list(self._children.get(agent_id, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            stack.extend(self._children.get(current, ()))
        return result

    def _run_block_hooks(self, agent_id: str, reason: str, actor: str) -> None:
        for hook in self._block_hooks:
            try:
                hook(agent_id, reason, actor)
            except Exception:
                logger.exception("kill switch block hook failed for agent=%s", agent_id)

    def _halt_state_machine(self, reason: str, actor: str) -> None:
        if self._state_machine is None:
            return
        try:
            self._state_machine.force_halt(reason=f"kill_switch: {reason}", actor=actor)
        except Exception:
            logger.exception("kill switch failed to halt state machine")

    def _verify_authorization(
        self,
        scope: KillScope,
        target: str,
        actor: str,
        authorization: DisengageAuthorization | None,
    ) -> None:
        if authorization is None:
            raise KillSwitchAuthorizationError("signed disengage authorization is required")
        if authorization.actor != actor:
            raise KillSwitchAuthorizationError("authorization actor mismatch")
        if authorization.scope != scope.value or authorization.target != target:
            raise KillSwitchAuthorizationError("authorization does not cover this scope/target")
        public_key_pem = self._authorizer_keys.get(actor)
        if not public_key_pem:
            raise KillSwitchAuthorizationError(
                f"actor {actor!r} is not an authorized kill switch operator"
            )

        now = self._now()
        if authorization.issued_at > now + _MAX_CLOCK_SKEW_SECONDS:
            raise KillSwitchAuthorizationError("authorization issued in the future")
        if now - authorization.issued_at > self._max_authorization_age:
            raise KillSwitchAuthorizationError("authorization expired")

        with self._lock:
            if authorization.nonce in self._used_nonces:
                raise KillSwitchAuthorizationError("authorization nonce was already used")
            if not ReportSigningKey.verify_signature(
                public_key_pem, authorization.signature, authorization.payload()
            ):
                raise KillSwitchAuthorizationError("authorization signature is invalid")
            self._used_nonces.add(authorization.nonce)

    def _emit(
        self,
        action: str,
        scope: KillScope,
        target: str,
        reason: str,
        actor: str,
    ) -> KillSwitchEvent:
        event = KillSwitchEvent(
            timestamp=self._now(),
            action=action,
            scope=scope,
            target=target,
            reason=reason,
            actor=actor,
        )
        with self._lock:
            self._events.append(event)
            if len(self._events) > _MAX_EVENTS:
                self._events = self._events[-_MAX_EVENTS:]
        for callback in self._audit_callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("kill switch audit callback failed")
        return event


__all__ = [
    "DisengageAuthorization",
    "KillScope",
    "KillSwitch",
    "KillSwitchAuthorizationError",
    "KillSwitchEvent",
]
