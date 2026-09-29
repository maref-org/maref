"""Temporal runtime monitor — 用户可写时序策略 (P1-4).

把"先认证后访问""SANCTION 后不得 ACT"这类跨事件时序属性，从 FSM 单步转移矩阵
提升到用户可写的 LTL 片段运行时监控。支持三种片段：

    G(expr)                 全局不变式：每个事件都满足 expr
    G(expr -> X(expr))      响应：左 expr 成立后，下一事件必须满足右 expr
    expr U expr             Until：右 expr 出现前，左 expr 必须持续成立

``expr`` := ``key=value`` | ``key!=value``，对事件 dict 求值；缺键视作 ``None``。
本模块做的是有限前缀运行时监控（逐事件增量检查），不依赖外部时序逻辑引擎。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from maref.governance.types import StateTransition

_PRED_RE = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(!=|=)\s*(\S+)\s*$")
_ALWAYS_NEXT_RE = re.compile(r"^G\(\s*(.+?)\s*->\s*X\(\s*(.+?)\s*\)\s*\)$")
_ALWAYS_RE = re.compile(r"^G\(\s*(.+?)\s*\)$")
_UNTIL_RE = re.compile(r"^(.+?)\s+U\s+(.+)$")


class TemporalPolicyError(ValueError):
    """Raised when a temporal policy string cannot be parsed."""


class _CallbackHost(Protocol):
    def add_callback(self, callback: Callable[[StateTransition], None]) -> None: ...

    def remove_callback(self, callback: Callable[[StateTransition], None]) -> None: ...


@dataclass(frozen=True)
class _Predicate:
    key: str
    op: str
    value: str

    def matches(self, event: Mapping[str, Any]) -> bool:
        actual = event.get(self.key)
        text = "" if actual is None else str(actual)
        return text == self.value if self.op == "=" else text != self.value


@dataclass(frozen=True)
class TemporalPolicy:
    """A parsed LTL-fragment policy."""

    text: str
    kind: str  # "always" | "always_next" | "until"
    left: _Predicate
    right: _Predicate | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kind": self.kind,
            "left": f"{self.left.key}{self.left.op}{self.left.value}",
            "right": (
                None if self.right is None else f"{self.right.key}{self.right.op}{self.right.value}"
            ),
        }


@dataclass(frozen=True)
class Violation:
    """A runtime violation of a temporal policy."""

    policy: str
    index: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"policy": self.policy, "index": self.index, "reason": self.reason}


def _parse_predicate(text: str) -> _Predicate:
    match = _PRED_RE.match(text)
    if match is None:
        raise TemporalPolicyError(f"invalid predicate: {text!r}")
    key, op, value = match.groups()
    return _Predicate(key=key, op=op, value=value)


def parse_policy(text: str) -> TemporalPolicy:
    """Parse a policy string into a :class:`TemporalPolicy`."""
    stripped = text.strip()
    match = _ALWAYS_NEXT_RE.match(stripped)
    if match is not None:
        return TemporalPolicy(
            text=stripped,
            kind="always_next",
            left=_parse_predicate(match.group(1)),
            right=_parse_predicate(match.group(2)),
        )
    match = _ALWAYS_RE.match(stripped)
    if match is not None:
        return TemporalPolicy(text=stripped, kind="always", left=_parse_predicate(match.group(1)))
    match = _UNTIL_RE.match(stripped)
    if match is not None:
        return TemporalPolicy(
            text=stripped,
            kind="until",
            left=_parse_predicate(match.group(1)),
            right=_parse_predicate(match.group(2)),
        )
    raise TemporalPolicyError(f"unsupported temporal policy: {text!r}")


class TemporalMonitor:
    """Incremental runtime monitor over a set of temporal policies.

    Usage:
        monitor = TemporalMonitor(["G(action!=shell.exec)"])
        monitor.observe({"action": "file.read"})   # []
        monitor.observe({"action": "shell.exec"})  # [Violation(...)]
    """

    def __init__(self, policies: Iterable[str | TemporalPolicy] | None = None) -> None:
        self._policies: list[TemporalPolicy] = []
        self._runtime: list[dict[str, Any]] = []
        self._index = 0
        self._violations: list[Violation] = []
        self._on_violation: Callable[[Violation], None] | None = None
        for policy in policies or []:
            self.add_policy(policy)

    # --- Policy management ---

    def add_policy(self, policy: str | TemporalPolicy) -> TemporalPolicy:
        """Register a policy (string or parsed)."""
        parsed = parse_policy(policy) if isinstance(policy, str) else policy
        self._policies.append(parsed)
        self._runtime.append({})
        return parsed

    @property
    def policies(self) -> list[TemporalPolicy]:
        """Registered policies."""
        return list(self._policies)

    @property
    def violations(self) -> list[Violation]:
        """All violations observed so far."""
        return list(self._violations)

    @property
    def index(self) -> int:
        """Number of events observed."""
        return self._index

    def reset(self) -> None:
        """Clear runtime state and recorded violations."""
        self._runtime = [{} for _ in self._policies]
        self._index = 0
        self._violations.clear()

    # --- Observation ---

    def observe(self, event: Mapping[str, Any]) -> list[Violation]:
        """Advance the monitor by one event; return new violations."""
        found: list[Violation] = []
        for position, policy in enumerate(self._policies):
            violation = self._step(policy, self._runtime[position], event)
            if violation is not None:
                found.append(violation)
                self._violations.append(violation)
        self._index += 1
        return found

    def _step(
        self, policy: TemporalPolicy, runtime: dict[str, Any], event: Mapping[str, Any]
    ) -> Violation | None:
        if policy.kind == "always":
            return self._step_always(policy, event)
        if policy.kind == "always_next":
            return self._step_always_next(policy, runtime, event)
        return self._step_until(policy, runtime, event)

    def _step_always(self, policy: TemporalPolicy, event: Mapping[str, Any]) -> Violation | None:
        if policy.left.matches(event):
            return None
        return Violation(
            policy=policy.text,
            index=self._index,
            reason=f"G violated: {policy.left.key}{policy.left.op}{policy.left.value}",
        )

    def _step_always_next(
        self, policy: TemporalPolicy, runtime: dict[str, Any], event: Mapping[str, Any]
    ) -> Violation | None:
        assert policy.right is not None
        violation: Violation | None = None
        if runtime.get("pending") and not policy.right.matches(event):
            violation = Violation(
                policy=policy.text,
                index=self._index,
                reason=(
                    "response violated: expected "
                    f"{policy.right.key}{policy.right.op}{policy.right.value} "
                    f"after {policy.left.key}{policy.left.op}{policy.left.value}"
                ),
            )
        runtime["pending"] = policy.left.matches(event)
        return violation

    def _step_until(
        self, policy: TemporalPolicy, runtime: dict[str, Any], event: Mapping[str, Any]
    ) -> Violation | None:
        assert policy.right is not None
        if runtime.get("satisfied"):
            return None
        if policy.right.matches(event):
            runtime["satisfied"] = True
            return None
        if not policy.left.matches(event):
            return Violation(
                policy=policy.text,
                index=self._index,
                reason=(
                    f"until violated: {policy.left.key}{policy.left.op}{policy.left.value} "
                    f"stopped before {policy.right.key}{policy.right.op}{policy.right.value}"
                ),
            )
        return None

    def unsatisfied_until(self) -> list[str]:
        """Until policies whose right-hand side never occurred."""
        return [
            policy.text
            for policy, runtime in zip(self._policies, self._runtime, strict=True)
            if policy.kind == "until" and not runtime.get("satisfied")
        ]

    def observe_state_transition(self, event: StateTransition) -> list[Violation]:
        """Adapter: monitor a governance state transition event."""
        return self.observe(
            {
                "from_state": event.from_state.name,
                "to_state": event.to_state.name,
                "reason": event.reason,
            }
        )

    # --- State machine attachment ---

    def _on_transition(self, event: StateTransition) -> None:
        for violation in self.observe_state_transition(event):
            if self._on_violation is not None:
                self._on_violation(violation)

    def attach(
        self,
        state_machine: _CallbackHost,
        on_violation: Callable[[Violation], None] | None = None,
    ) -> None:
        """Register as a state machine callback, optionally reporting violations."""
        self._on_violation = on_violation
        state_machine.add_callback(self._on_transition)

    def detach(self, state_machine: _CallbackHost) -> None:
        """Unregister the state machine callback."""
        state_machine.remove_callback(self._on_transition)

    def to_dict(self) -> dict[str, Any]:
        """Serializable monitor state."""
        return {
            "policies": [policy.to_dict() for policy in self._policies],
            "index": self._index,
            "violations": [violation.to_dict() for violation in self._violations],
            "unsatisfied_until": self.unsatisfied_until(),
        }
