from __future__ import annotations

from maref.subgoal.delegation_graph import DelegationGraph


class TestDelegationGraph:
    def test_record_delegation(self) -> None:
        dg = DelegationGraph()
        dg.record_delegation("agent-a", "agent-b", {"read", "write"})
        perms = dg.get_effective_permissions("agent-b")
        assert "read" in perms["direct_permissions"]
        assert "write" in perms["direct_permissions"]

    def test_no_scope_creep_initial(self) -> None:
        dg = DelegationGraph()
        report = dg.detect_scope_creep("agent-a")
        assert not report.requires_cooldown

    def test_scope_creep_detected(self) -> None:
        dg = DelegationGraph(cooldown_threshold=0.3)
        dg.record_delegation("admin", "agent-x", {"read"})
        dg.record_delegation("admin", "agent-x", {"write", "execute", "delete", "admin"})
        report = dg.detect_scope_creep("agent-x")
        assert report.creep_score >= 0
        assert len(report.new_permissions) > 0

    def test_transitive_closure(self) -> None:
        dg = DelegationGraph()
        dg.record_delegation("root", "ops", {"read"})
        dg.record_delegation("ops", "worker", {"write", "execute"})
        effective = dg.transitive_closure("worker")
        assert "write" in effective
        assert "execute" in effective

    def test_cooldown(self) -> None:
        dg = DelegationGraph()
        assert not dg.is_in_cooldown("agent-c")
        dg.apply_cooldown("agent-c", 3600)
        assert dg.is_in_cooldown("agent-c")

    def test_cooldown_expiry(self) -> None:
        dg = DelegationGraph()
        dg.apply_cooldown("agent-d", -1)
        assert not dg.is_in_cooldown("agent-d")

    def test_creep_findings(self) -> None:
        dg = DelegationGraph(cooldown_threshold=0.1)
        dg.record_delegation("admin", "agent-y", {"read"})
        dg.record_delegation("admin", "agent-y", {"read", "write", "execute", "delete", "admin"})
        report = dg.detect_scope_creep("agent-y")
        assert len(report.findings) > 0
