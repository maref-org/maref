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


class TestEnforceDelegation:
    """Tests for enforce_delegation -- hard permission enforcement."""

    def test_all_in_scope(self) -> None:
        """All requested permissions are within delegator scope."""
        dg = DelegationGraph()
        dg.record_delegation("root", "admin", {"read", "write", "execute"})

        result = dg.enforce_delegation(
            "admin", "worker", {"read", "write"}
        )
        assert result.allowed is True
        assert result.granted_permissions == {"read", "write"}
        assert result.trimmed_permissions == set()

    def test_trims_out_of_scope(self) -> None:
        """Out-of-scope permissions are trimmed, in-scope ones granted."""
        dg = DelegationGraph()
        dg.record_delegation("root", "admin", {"read", "write"})

        result = dg.enforce_delegation(
            "admin", "worker", {"read", "write", "execute", "delete"}
        )
        assert result.allowed is True
        assert result.granted_permissions == {"read", "write"}
        assert result.trimmed_permissions == {"execute", "delete"}

    def test_rejects_all_out_of_scope(self) -> None:
        """Delegation refused when no permissions are in scope."""
        dg = DelegationGraph()
        dg.record_delegation("root", "admin", {"read"})

        result = dg.enforce_delegation(
            "admin", "worker", {"execute", "delete"}
        )
        assert result.allowed is False
        assert result.granted_permissions == set()
        assert result.trimmed_permissions == {"execute", "delete"}

    def test_check_permission(self) -> None:
        """check_permission correctly reports transitive permissions."""
        dg = DelegationGraph()
        dg.record_delegation("root", "admin", {"read", "write"})
        dg.record_delegation("admin", "worker", {"read"})

        assert dg.check_permission("worker", "read") is True
        assert dg.check_permission("worker", "write") is False
        assert dg.check_permission("admin", "write") is True
        assert dg.check_permission("unknown", "read") is False

    def test_chain_delegation_enforcement(self) -> None:
        """A->B->C chain: C's permissions cannot exceed A's scope."""
        dg = DelegationGraph()
        dg.record_delegation("root", "A", {"read", "write", "execute"})

        # A delegates to B (enforced)
        result_b = dg.enforce_delegation("A", "B", {"read", "write", "delete"})
        assert result_b.allowed is True
        assert result_b.granted_permissions == {"read", "write"}
        assert "delete" in result_b.trimmed_permissions

        # B delegates to C (enforced) -- C cannot get "delete" via B
        result_c = dg.enforce_delegation("B", "C", {"read", "delete"})
        assert result_c.allowed is True
        assert result_c.granted_permissions == {"read"}
        assert "delete" in result_c.trimmed_permissions

    def test_enforcement_records_delegation(self) -> None:
        """enforce_delegation actually records the granted permissions."""
        dg = DelegationGraph()
        dg.record_delegation("root", "admin", {"read", "write"})

        dg.enforce_delegation("admin", "worker", {"read", "write"})
        perms = dg.get_effective_permissions("worker")
        assert "read" in perms["direct_permissions"]
        assert "write" in perms["direct_permissions"]

    def test_no_delegator_permissions(self) -> None:
        """Delegation from an agent with no permissions is refused."""
        dg = DelegationGraph()

        result = dg.enforce_delegation("nobody", "worker", {"read"})
        assert result.allowed is False
        assert result.granted_permissions == set()

