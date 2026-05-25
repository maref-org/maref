from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maref.security.trust_chain import (
    ChainNode,
    DelegationCapability,
    DelegationChain,
    ValidationStatus,
)


class TestDelegationChainCreate:
    def test_create_with_root_agent(self):
        chain = DelegationChain.create("agent-001")
        assert chain.root_agent_id == "agent-001"
        assert chain.depth == 1
        assert chain.max_depth == 5
        assert len(chain.nodes) == 1
        assert chain.nodes[0].capability == DelegationCapability.ADMIN

    def test_create_with_custom_max_depth(self):
        chain = DelegationChain.create("agent-001", max_depth=3)
        assert chain.max_depth == 3


class TestDelegationChainAdd:
    def test_add_delegation_success(self):
        chain = DelegationChain.create("agent-001")
        result = chain.add_delegation("agent-001", "agent-002", DelegationCapability.EXECUTE)
        assert result is True
        assert chain.depth == 2
        assert len(chain.nodes) == 2

    def test_add_delegation_max_depth_exceeded(self):
        chain = DelegationChain.create("agent-001", max_depth=2)
        chain.add_delegation("agent-001", "agent-002", DelegationCapability.EXECUTE)
        chain.add_delegation("agent-002", "agent-003", DelegationCapability.READ)
        result = chain.add_delegation("agent-003", "agent-004", DelegationCapability.READ)
        assert result is False

    def test_add_delegation_invalid_parent(self):
        chain = DelegationChain.create("agent-001")
        result = chain.add_delegation("invalid-agent", "agent-002", DelegationCapability.READ)
        assert result is False


class TestDelegationChainValidation:
    def test_validate_valid_chain(self):
        chain = DelegationChain.create("agent-001")
        chain.add_delegation("agent-001", "agent-002", DelegationCapability.READ)
        result = chain.validate()
        assert result.status == ValidationStatus.VALID
        assert result.is_valid is True

    def test_validate_max_depth_exceeded(self):
        chain = DelegationChain.create("agent-001", max_depth=1)
        chain.add_delegation("agent-001", "agent-002", DelegationCapability.READ)
        result = chain.validate()
        assert result.status == ValidationStatus.INVALID_MAX_DEPTH
        assert result.is_valid is False


class TestChainNode:
    def test_chain_node_to_dict(self):
        node = ChainNode(
            agent_id="agent-001",
            capability=DelegationCapability.READ,
            timestamp=datetime(2026, 5, 13, tzinfo=timezone.utc),
            parent_id=None,
        )
        data = node.to_dict()
        assert data["agent_id"] == "agent-001"
        assert data["capability"] == "read"
        assert data["parent_id"] is None


class TestChainHash:
    def test_get_chain_hash_deterministic(self):
        chain1 = DelegationChain.create("agent-001")
        chain1.add_delegation("agent-001", "agent-002", DelegationCapability.READ)

        chain2 = DelegationChain.create("agent-001")
        chain2.add_delegation("agent-001", "agent-002", DelegationCapability.READ)

        assert chain1.get_chain_hash() == chain2.get_chain_hash()

    def test_different_chains_different_hashes(self):
        chain1 = DelegationChain.create("agent-001")
        chain1.add_delegation("agent-001", "agent-002", DelegationCapability.READ)

        chain2 = DelegationChain.create("agent-001")
        chain2.add_delegation("agent-001", "agent-002", DelegationCapability.EXECUTE)

        assert chain1.get_chain_hash() != chain2.get_chain_hash()


class TestCapabilityHierarchy:
    """A1.3: 委托能力层级正确传播（ADMIN > DELEGATE > EXECUTE > WRITE > READ）"""

    def test_admin_can_delegate_any_capability(self):
        for cap in DelegationCapability:
            chain = DelegationChain.create("root")
            assert chain.add_delegation("root", f"child-{cap.value}", cap) is True

    def test_delegate_can_delegate_up_to_delegate(self):
        chain = DelegationChain.create("root")
        chain.add_delegation("root", "delegate", DelegationCapability.DELEGATE)
        # DELEGATE can delegate READ, WRITE, EXECUTE, DELEGATE
        assert chain.add_delegation("delegate", "c1", DelegationCapability.READ) is True

        chain = DelegationChain.create("root")
        chain.add_delegation("root", "delegate", DelegationCapability.DELEGATE)
        assert chain.add_delegation("delegate", "c2", DelegationCapability.WRITE) is True

        chain = DelegationChain.create("root")
        chain.add_delegation("root", "delegate", DelegationCapability.DELEGATE)
        assert chain.add_delegation("delegate", "c3", DelegationCapability.EXECUTE) is True

        chain = DelegationChain.create("root")
        chain.add_delegation("root", "delegate", DelegationCapability.DELEGATE)
        assert chain.add_delegation("delegate", "c4", DelegationCapability.DELEGATE) is True

        # But not ADMIN
        chain = DelegationChain.create("root")
        chain.add_delegation("root", "delegate", DelegationCapability.DELEGATE)
        assert chain.add_delegation("delegate", "c5", DelegationCapability.ADMIN) is False

    def test_execute_cannot_delegate(self):
        """EXECUTE, WRITE, READ have no delegation rights."""
        for cap in (DelegationCapability.EXECUTE, DelegationCapability.WRITE, DelegationCapability.READ):
            chain = DelegationChain.create("root")
            chain.add_delegation("root", "agent", cap)
            assert chain.add_delegation("agent", "c1", DelegationCapability.READ) is False

    def test_chain_hash_uses_sha256(self):
        chain = DelegationChain.create("root")
        chain.add_delegation("root", "child", DelegationCapability.EXECUTE)
        h = chain.get_chain_hash()
        assert len(h) == 64  # SHA-256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in h)


class TestCircularDelegation:
    """A1: 循环委托检测"""

    def test_cycle_detected_in_validation(self):
        chain = DelegationChain.create("root")
        chain.add_delegation("root", "a1", DelegationCapability.DELEGATE)
        chain.add_delegation("a1", "root", DelegationCapability.EXECUTE)  # cycle
        result = chain.validate()
        assert result.status == ValidationStatus.INVALID_CYCLE
        assert not result.is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
