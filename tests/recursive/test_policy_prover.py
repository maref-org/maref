"""PolicyProver 单元测试 — 能力组合可达性证明 (P1-8)."""

from __future__ import annotations

import pytest

from maref.recursive.capability_contracts import (
    CapabilityContract,
    CapabilityRegistry,
    Predicate,
)
from maref.recursive.policy_prover import PolicyProver, ReachabilityProof


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityContract(
            capability_id="read_token",
            version="1.0.0",
            postconditions=[Predicate(name="has_token")],
            side_effects=["read"],
        )
    )
    registry.register(
        CapabilityContract(
            capability_id="call_api",
            version="1.0.0",
            preconditions=[Predicate(name="has_token")],
            postconditions=[Predicate(name="external_call")],
            side_effects=["network"],
        )
    )
    registry.register(
        CapabilityContract(
            capability_id="escalate",
            version="1.0.0",
            preconditions=[Predicate(name="external_call")],
            postconditions=[Predicate(name="admin")],
            side_effects=["privilege_escalation"],
        )
    )
    return registry


CHAIN = ["read_token", "call_api", "escalate"]


class TestReachable:
    def test_composition_reaches_danger(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, "admin")
        assert proof.reachable is True
        assert proof.witness == CHAIN
        assert proof.bounded is False
        assert proof.composition_length == 3

    def test_initial_state_already_dangerous(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, "admin", {"admin": True})
        assert proof.reachable is True
        assert proof.witness == []

    def test_mapping_danger_spec(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, {"admin": True})
        assert proof.reachable is True
        assert "admin" in proof.danger

    def test_callable_danger_spec(self) -> None:
        prover = PolicyProver(_registry())
        proof = prover.prove_reachable(CHAIN, lambda state: bool(state.get("admin")))
        assert proof.reachable is True

    def test_predicate_danger_spec(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, Predicate(name="admin"))
        assert proof.reachable is True
        assert proof.danger == "admin"


class TestUnreachable:
    def test_missing_capability_is_unreachable_complete(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(["read_token", "call_api"], "admin")
        assert proof.reachable is False
        assert proof.complete is True
        assert proof.bounded is False

    def test_precondition_gate_blocks_single_capability(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(["escalate"], "admin")
        assert proof.reachable is False
        assert proof.complete is True

    def test_unknown_capabilities_ignored(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(["does-not-exist"], "admin")
        assert proof.reachable is False
        assert proof.complete is True

    def test_depth_bound_reports_bounded(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, "admin", max_depth=1)
        assert proof.reachable is False
        assert proof.bounded is True
        assert proof.complete is False

    def test_state_bound_reports_bounded(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, "admin", max_states=2)
        assert proof.reachable is False
        assert proof.bounded is True


class TestProofMetadata:
    def test_states_explored_positive(self) -> None:
        proof = PolicyProver(_registry()).prove_reachable(CHAIN, "admin")
        assert proof.states_explored >= 1

    def test_to_dict(self) -> None:
        payload = PolicyProver(_registry()).prove_reachable(CHAIN, "admin").to_dict()
        assert payload["reachable"] is True
        assert payload["witness"] == CHAIN
        assert payload["complete"] is False

    def test_prove_safe_alias(self) -> None:
        proof = PolicyProver(_registry()).prove_safe(["escalate"], "admin")
        assert isinstance(proof, ReachabilityProof)
        assert proof.reachable is False

    def test_escalation_requires_composition(self) -> None:
        prover = PolicyProver(_registry())
        # 任一单能力都不可达
        for cap in CHAIN:
            assert prover.prove_reachable([cap], "admin").reachable is False
        # 组合后可达 → 组合越权
        combined = prover.prove_reachable(CHAIN, "admin")
        assert combined.reachable is True
        assert combined.composition_length >= 2


class TestValidation:
    def test_invalid_limits(self) -> None:
        with pytest.raises(ValueError):
            PolicyProver(_registry(), max_states=0)
        with pytest.raises(ValueError):
            PolicyProver(_registry(), max_depth=0)

    def test_invalid_call_limits(self) -> None:
        prover = PolicyProver(_registry())
        with pytest.raises(ValueError):
            prover.prove_reachable(CHAIN, "admin", max_depth=0)

    def test_bad_danger_spec(self) -> None:
        with pytest.raises(TypeError):
            PolicyProver(_registry()).prove_reachable(CHAIN, 123)
