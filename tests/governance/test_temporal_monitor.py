"""TemporalMonitor 单元测试 — LTL 片段运行时监控 (P1-4)."""

from __future__ import annotations

from typing import Any

import pytest

from maref.governance.temporal_monitor import (
    TemporalMonitor,
    TemporalPolicyError,
    parse_policy,
)
from maref.governance.types import GovernanceState, StateTransition


class TestParsing:
    def test_parse_always(self) -> None:
        policy = parse_policy("G(action!=shell.exec)")
        assert policy.kind == "always"
        assert policy.left.key == "action"

    def test_parse_always_next(self) -> None:
        policy = parse_policy("G(auth=user -> X(access=allowed))")
        assert policy.kind == "always_next"
        assert policy.right is not None
        assert policy.right.value == "allowed"

    def test_parse_until(self) -> None:
        policy = parse_policy("action=read U action=write")
        assert policy.kind == "until"
        assert policy.right is not None

    def test_parse_unsupported(self) -> None:
        with pytest.raises(TemporalPolicyError):
            parse_policy("F(action=done)")

    def test_parse_bad_predicate(self) -> None:
        with pytest.raises(TemporalPolicyError):
            parse_policy("G(nonsense)")

    def test_to_dict(self) -> None:
        payload = parse_policy("G(action!=shell.exec)").to_dict()
        assert payload["kind"] == "always"
        assert payload["left"] == "action!=shell.exec"


class TestAlways:
    def test_no_violation_when_invariant_holds(self) -> None:
        monitor = TemporalMonitor(["G(action!=shell.exec)"])
        assert monitor.observe({"action": "file.read"}) == []

    def test_violation_when_invariant_breaks(self) -> None:
        monitor = TemporalMonitor(["G(action!=shell.exec)"])
        violations = monitor.observe({"action": "shell.exec"})
        assert len(violations) == 1
        assert violations[0].policy == "G(action!=shell.exec)"

    def test_missing_key_treated_as_none(self) -> None:
        # 缺键 -> None -> 文本 "" -> "action!=never" 成立
        monitor = TemporalMonitor(["G(action!=never)"])
        assert monitor.observe({"other": "x"}) == []


class TestAlwaysNext:
    def test_response_satisfied(self) -> None:
        monitor = TemporalMonitor(["G(auth=user -> X(access=allowed))"])
        assert monitor.observe({"auth": "user"}) == []
        assert monitor.observe({"access": "allowed"}) == []

    def test_response_violated(self) -> None:
        monitor = TemporalMonitor(["G(auth=user -> X(access=allowed))"])
        monitor.observe({"auth": "user"})
        violations = monitor.observe({"access": "denied"})
        assert len(violations) == 1
        assert "response violated" in violations[0].reason

    def test_no_trigger_no_violation(self) -> None:
        monitor = TemporalMonitor(["G(auth=user -> X(access=allowed))"])
        assert monitor.observe({"access": "denied"}) == []


class TestUntil:
    def test_satisfied(self) -> None:
        monitor = TemporalMonitor(["action=read U action=write"])
        assert monitor.observe({"action": "read"}) == []
        assert monitor.observe({"action": "write"}) == []
        assert monitor.observe({"action": "delete"}) == []

    def test_violated_before_satisfaction(self) -> None:
        monitor = TemporalMonitor(["action=read U action=write"])
        monitor.observe({"action": "read"})
        violations = monitor.observe({"action": "delete"})
        assert len(violations) == 1
        assert "until violated" in violations[0].reason

    def test_unsatisfied_until_reported(self) -> None:
        monitor = TemporalMonitor(["action=read U action=write"])
        monitor.observe({"action": "read"})
        assert monitor.unsatisfied_until() == ["action=read U action=write"]
        monitor.observe({"action": "write"})
        assert monitor.unsatisfied_until() == []


class TestLifecycle:
    def test_reset_clears_state(self) -> None:
        monitor = TemporalMonitor(["G(action!=shell.exec)"])
        monitor.observe({"action": "shell.exec"})
        assert monitor.violations
        monitor.reset()
        assert monitor.violations == []
        assert monitor.index == 0

    def test_to_dict(self) -> None:
        monitor = TemporalMonitor(["G(action!=shell.exec)"])
        monitor.observe({"action": "shell.exec"})
        payload = monitor.to_dict()
        assert payload["index"] == 1
        assert len(payload["violations"]) == 1


class _FakeStateMachine:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def add_callback(self, callback: Any) -> None:
        self.callbacks.append(callback)

    def remove_callback(self, callback: Any) -> None:
        self.callbacks.remove(callback)


class TestStateMachineWiring:
    def test_observe_state_transition(self) -> None:
        monitor = TemporalMonitor(["G(to_state!=HALT)"])
        event = StateTransition(from_state=GovernanceState.REPORT, to_state=GovernanceState.HALT)
        violations = monitor.observe_state_transition(event)
        assert len(violations) == 1

    def test_attach_reports_violation(self) -> None:
        seen: list[str] = []
        monitor = TemporalMonitor(["G(to_state!=HALT)"])
        host = _FakeStateMachine()
        monitor.attach(host, on_violation=lambda v: seen.append(v.policy))
        host.callbacks[0](
            StateTransition(from_state=GovernanceState.REPORT, to_state=GovernanceState.HALT)
        )
        assert seen == ["G(to_state!=HALT)"]

    def test_detach_removes_callback(self) -> None:
        monitor = TemporalMonitor()
        host = _FakeStateMachine()
        monitor.attach(host)
        monitor.detach(host)
        assert host.callbacks == []
