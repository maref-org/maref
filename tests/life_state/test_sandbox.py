"""Tests for C37: Life State Sandbox."""

from __future__ import annotations

from maref.life_state.sandbox import (
    LifeStateSandbox,
    Permission,
    PermissionMatrix,
    SandboxAction,
)


class TestPermissionMatrix:
    def test_grant_and_has(self):
        m = PermissionMatrix(state_id="s1")
        m.grant(Permission.READ)
        assert m.has(Permission.READ)
        assert not m.has(Permission.WRITE)

    def test_revoke(self):
        m = PermissionMatrix(state_id="s1")
        m.grant(Permission.READ)
        m.revoke(Permission.READ)
        assert not m.has(Permission.READ)

    def test_to_dict(self):
        m = PermissionMatrix(state_id="s1")
        m.grant(Permission.READ)
        m.grant(Permission.EXECUTE)
        d = m.to_dict()
        assert d["state_id"] == "s1"
        assert d["permissions"] == ["execute", "read"]


class TestLifeStateSandbox:
    def test_register(self):
        sandbox = LifeStateSandbox()
        matrix = sandbox.register("s1")
        assert matrix.state_id == "s1"
        assert sandbox.get_matrix("s1") is matrix

    def test_grant_permission(self):
        sandbox = LifeStateSandbox()
        sandbox.grant("s1", Permission.READ)
        assert sandbox.get_matrix("s1").has(Permission.READ)

    def test_revoke_permission(self):
        sandbox = LifeStateSandbox()
        sandbox.grant("s1", Permission.READ)
        sandbox.revoke("s1", Permission.READ)
        assert not sandbox.get_matrix("s1").has(Permission.READ)

    def test_check_granted(self):
        sandbox = LifeStateSandbox()
        sandbox.grant("s1", Permission.READ)
        assert sandbox.check("s1", Permission.READ) is True

    def test_check_denied(self):
        sandbox = LifeStateSandbox()
        sandbox.register("s1")
        assert sandbox.check("s1", Permission.WRITE) is False

    def test_check_unregistered(self):
        sandbox = LifeStateSandbox()
        assert sandbox.check("s1", Permission.READ) is False

    def test_execute(self):
        sandbox = LifeStateSandbox()
        result = sandbox.execute("s1", "test_op")
        assert result["state_id"] == "s1"
        assert result["operation"] == "test_op"
        assert result["status"] == "completed"

    def test_audit_log(self):
        sandbox = LifeStateSandbox()
        sandbox.grant("s1", Permission.READ)
        sandbox.check("s1", Permission.READ)
        log = sandbox.get_audit_log("s1")
        assert len(log) >= 1
        assert log[-1].action == SandboxAction.ACCESS_GRANTED

    def test_audit_log_filtered(self):
        sandbox = LifeStateSandbox()
        sandbox.grant("s1", Permission.READ)
        sandbox.grant("s2", Permission.WRITE)
        sandbox.check("s1", Permission.READ)
        sandbox.check("s2", Permission.WRITE)
        log = sandbox.get_audit_log("s1")
        assert all(e.state_id == "s1" for e in log)

    def test_denied_count(self):
        sandbox = LifeStateSandbox()
        sandbox.register("s1")
        sandbox.check("s1", Permission.READ)
        sandbox.check("s1", Permission.WRITE)
        assert sandbox.get_denied_count("s1") == 2

    def test_clear_audit(self):
        sandbox = LifeStateSandbox()
        sandbox.check("s1", Permission.READ)
        sandbox.clear_audit()
        assert len(sandbox.get_audit_log()) == 0

    def test_to_dict(self):
        sandbox = LifeStateSandbox()
        sandbox.register("s1")
        d = sandbox.to_dict()
        assert d["registered_count"] == 1
        assert d["audit_count"] == 0
