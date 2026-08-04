"""
v0.50 W1 — 单 Agent 治理承重墙封堵测试

覆盖审计缺口：
- W1-S1 (A9)   GovernanceStateMachine HMAC 空密钥 fail-closed
- W1-S2 (A12)  force_stabilize/force_halt 授权校验
- W1-S3 (A8)   restore() 恢复历史链
"""

from __future__ import annotations

import pytest

from maref.governance.state_machine import GovernanceStateMachine, _write_state_transition
from maref.governance.types import GovernanceState, StateMachineSnapshot, StateTransition


class TestW1S1HmacFailClosed:
    """A9: 空 MAREF_HMAC_SECRET_KEY 时必须拒绝写链，不允许退化为裸 sha256。"""

    def test_write_transition_refuses_without_hmac_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        event = StateTransition(
            from_state=GovernanceState.INIT,
            to_state=GovernanceState.OBSERVE,
            reason="start",
        )
        with pytest.raises(ValueError, match="MAREF_HMAC_SECRET_KEY"):
            _write_state_transition(event)

    def test_transition_fails_closed_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MAREF_HMAC_SECRET_KEY", raising=False)
        sm = GovernanceStateMachine()
        with pytest.raises(ValueError, match="MAREF_HMAC_SECRET_KEY"):
            sm.transition(GovernanceState.OBSERVE, "start")
        assert sm.current_state == GovernanceState.INIT

    def test_transition_succeeds_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "unit-test-hmac-key")
        sm = GovernanceStateMachine()
        assert sm.transition(GovernanceState.OBSERVE, "start") is True
        assert sm.current_state == GovernanceState.OBSERVE


class TestW1S2ForceAuthorization:
    """A12: force_stabilize/force_halt 需授权校验。"""

    def test_force_halt_without_authorization_when_enforced(self) -> None:
        sm = GovernanceStateMachine()
        sm.configure_force_authorization(
            enforce=True,
            authorizer=lambda actor, reason: actor == "trusted-operator",
        )
        sm.transition(GovernanceState.OBSERVE, "start")
        with pytest.raises(PermissionError):
            sm.force_halt("emergency")
        assert sm.current_state != GovernanceState.HALT

    def test_force_halt_with_authorized_actor(self) -> None:
        sm = GovernanceStateMachine()
        sm.configure_force_authorization(
            enforce=True,
            authorizer=lambda actor, reason: actor == "trusted-operator",
        )
        sm.transition(GovernanceState.OBSERVE, "start")
        assert sm.force_halt("emergency", actor="trusted-operator") is True
        assert sm.current_state == GovernanceState.HALT

    def test_force_stabilize_without_authorization_when_enforced(self) -> None:
        sm = GovernanceStateMachine()
        sm.configure_force_authorization(
            enforce=True,
            authorizer=lambda actor, reason: actor == "operator-a",
        )
        with pytest.raises(PermissionError):
            sm.force_stabilize("recover")

    def test_force_operation_legacy_compatible_without_enforcement(self) -> None:
        sm = GovernanceStateMachine()
        assert sm.force_stabilize("recover") is True
        assert sm.current_state == GovernanceState.STABILIZE

    def test_enforce_without_authorizer_raises(self) -> None:
        sm = GovernanceStateMachine()
        with pytest.raises(RuntimeError):
            sm.configure_force_authorization(enforce=True, authorizer=None)


class TestW1S3RestoreHistory:
    """A8: restore() 必须恢复历史链，而非清空。"""

    def test_restore_preserves_history_chain(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "a")
        sm.transition(GovernanceState.ANALYZE, "b")
        snapshot = sm.snapshot()
        assert snapshot.history_length == 2
        assert len(snapshot.history_entries) == 2

        sm2 = GovernanceStateMachine.restore(snapshot)
        assert sm2.current_state == GovernanceState.ANALYZE
        assert len(sm2.get_history()) == 2
        assert sm2.transition_count == 2
        assert sm2.get_history()[0].to_state == GovernanceState.OBSERVE
        assert sm2.get_history()[1].to_state == GovernanceState.ANALYZE
        assert sm2.get_history()[1].reason == "b"

    def test_restore_from_scratch_snapshot_empty_history(self) -> None:
        sm = GovernanceStateMachine()
        snapshot = sm.snapshot()
        sm2 = GovernanceStateMachine.restore(snapshot)
        assert len(sm2.get_history()) == 0
        assert sm2.transition_count == 0

    def test_restore_keeps_entropy_history(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "a")
        snapshot = sm.snapshot()
        sm2 = GovernanceStateMachine.restore(snapshot)
        assert sm2.get_entropy_trend()["current"] == sm.get_entropy_trend()["current"]

    def test_snapshot_from_dict_preserves_history_entries(self) -> None:
        sm = GovernanceStateMachine()
        sm.transition(GovernanceState.OBSERVE, "a")
        snapshot = sm.snapshot()
        data = snapshot.to_dict()
        restored_snapshot = StateMachineSnapshot.from_dict(data)
        assert restored_snapshot.history_length == 1
