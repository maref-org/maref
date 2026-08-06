"""Tests for capability_contracts.py — Predicate, CapabilityContract, Registry, Risk."""
from __future__ import annotations

import pytest

from maref.recursive.capability_contracts import (
    CapabilityContract,
    CapabilityRegistry,
    CombinatorialRiskAnalyzer,
    CompositeContract,
    CompositionMode,
    CostProfile,
    InteractionRisk,
    Predicate,
)


class TestPredicate:
    def test_evaluate_with_fn(self):
        p = Predicate("custom", evaluate_fn=lambda s: s.get("ok", False))
        assert p.evaluate({"ok": True}) is True
        assert p.evaluate({"ok": False}) is False

    def test_evaluate_without_fn(self):
        p = Predicate("is_ready")
        assert p.evaluate({"is_ready": True}) is True
        assert p.evaluate({"is_ready": False}) is False
        assert p.evaluate({}) is False

    def test_hash_and_eq(self):
        p1 = Predicate("ready", ["a", "b"])
        p2 = Predicate("ready", ["a", "b"])
        p3 = Predicate("ready", ["c"])
        assert hash(p1) == hash(p2)
        assert p1 == p2
        assert p1 != p3
        assert p1.__eq__("not_predicate") == NotImplemented

    def test_inequality(self):
        p1 = Predicate("ready")
        p2 = Predicate("done")
        assert p1 != p2


class TestCostProfile:
    def test_estimate(self):
        cp = CostProfile(base_cost=1.0, cost_per_input_token=0.01, cost_per_output_token=0.02)
        assert cp.estimate(input_size=100, output_size=50) == 1.0 + 100 * 0.01 + 50 * 0.02

    def test_estimate_zero(self):
        cp = CostProfile()
        assert cp.estimate() == 0.0


class TestCapabilityContract:
    def test_validate_preconditions_all_pass(self):
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            preconditions=[
                Predicate("is_ready"),
                Predicate("has_data"),
            ],
        )
        ok, failures = contract.validate_preconditions({"is_ready": True, "has_data": True})
        assert ok is True
        assert failures == []

    def test_validate_preconditions_fail(self):
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            preconditions=[Predicate("is_ready")],
        )
        ok, failures = contract.validate_preconditions({"is_ready": False})
        assert ok is False
        assert len(failures) == 1

    def test_validate_postconditions(self):
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            postconditions=[Predicate("completed")],
        )
        ok, _ = contract.validate_postconditions({"completed": True})
        assert ok is True
        ok, _ = contract.validate_postconditions({"completed": False})
        assert ok is False

    def test_validate_input_no_schema(self):
        contract = CapabilityContract(capability_id="c1", version="1.0")
        ok, errors = contract.validate_input({"any": "data"})
        assert ok is True
        assert errors == []

    def test_validate_input_missing_required(self):
        contract = CapabilityContract(
            capability_id="c1", version="1.0",
            input_schema={"required": ["name", "email"]},
        )
        ok, errors = contract.validate_input({"name": "alice"})
        assert ok is False
        assert any("email" in e for e in errors)

    def test_validate_input_type_mismatch(self):
        contract = CapabilityContract(
            capability_id="c1", version="1.0",
            input_schema={
                "required": ["age"],
                "properties": {"age": {"type": "integer"}},
            },
        )
        ok, errors = contract.validate_input({"age": "not_a_number"})
        assert ok is False

    def test_validate_output_no_schema(self):
        contract = CapabilityContract(capability_id="c1", version="1.0")
        ok, _ = contract.validate_output({"result": "ok"})
        assert ok is True

    def test_validate_output_missing(self):
        contract = CapabilityContract(
            capability_id="c1", version="1.0",
            output_schema={"required": ["result"]},
        )
        ok, errors = contract.validate_output({"status": "done"})
        assert ok is False

    def test_check_type(self):
        assert CapabilityContract._check_type("hello", "string") is True
        assert CapabilityContract._check_type(42, "integer") is True
        assert CapabilityContract._check_type(3.14, "number") is True
        assert CapabilityContract._check_type(True, "boolean") is True
        assert CapabilityContract._check_type([1, 2], "array") is True
        assert CapabilityContract._check_type({"a": 1}, "object") is True
        assert CapabilityContract._check_type("hello", "unknown_type") is True
        assert CapabilityContract._check_type("hello", "integer") is False

    def test_hash_and_eq(self):
        c1 = CapabilityContract("cap1", "1.0")
        c2 = CapabilityContract("cap1", "1.0")
        c3 = CapabilityContract("cap1", "2.0")
        assert hash(c1) == hash(c2)
        assert c1 == c2
        assert c1 != c3
        assert c1.__eq__("not_contract") == NotImplemented


class TestCompositeContract:
    def test_and_mode_all_pass(self):
        c1 = CapabilityContract("c1", "1.0", preconditions=[Predicate("ready")])
        c2 = CapabilityContract("c2", "1.0", preconditions=[Predicate("ready")])
        composite = CompositeContract(
            capability_id="comp", version="1.0",
            sub_contracts=[c1, c2],
            composition_mode=CompositionMode.AND,
        )
        ok, failures = composite.validate_preconditions({"ready": True})
        assert ok is True

    def test_and_mode_one_fails(self):
        c1 = CapabilityContract("c1", "1.0", preconditions=[Predicate("a")])
        c2 = CapabilityContract("c2", "1.0", preconditions=[Predicate("b")])
        composite = CompositeContract(
            capability_id="comp", version="1.0",
            sub_contracts=[c1, c2],
            composition_mode=CompositionMode.AND,
        )
        ok, failures = composite.validate_preconditions({"a": True, "b": False})
        assert ok is False
        assert len(failures) >= 1

    def test_or_mode_one_pass(self):
        c1 = CapabilityContract("c1", "1.0", preconditions=[Predicate("a")])
        c2 = CapabilityContract("c2", "1.0", preconditions=[Predicate("b")])
        composite = CompositeContract(
            capability_id="comp", version="1.0",
            sub_contracts=[c1, c2],
            composition_mode=CompositionMode.OR,
        )
        ok, failures = composite.validate_preconditions({"a": True, "b": False})
        assert ok is True

    def test_or_mode_all_fail(self):
        c1 = CapabilityContract("c1", "1.0", preconditions=[Predicate("a")])
        c2 = CapabilityContract("c2", "1.0", preconditions=[Predicate("b")])
        composite = CompositeContract(
            capability_id="comp", version="1.0",
            sub_contracts=[c1, c2],
            composition_mode=CompositionMode.OR,
        )
        ok, failures = composite.validate_preconditions({"a": False, "b": False})
        assert ok is False

    def test_postconditions(self):
        c1 = CapabilityContract("c1", "1.0", postconditions=[Predicate("done")])
        composite = CompositeContract("comp", "1.0", sub_contracts=[c1])
        ok, _ = composite.validate_postconditions({"done": True})
        assert ok is True


class TestCapabilityRegistry:
    def test_register_and_get(self):
        registry = CapabilityRegistry()
        contract = CapabilityContract("cap1", "1.0")
        assert registry.register(contract) is True
        assert registry.get("cap1") is contract
        assert registry.get("nonexistent") is None

    def test_register_duplicate_version(self):
        registry = CapabilityRegistry()
        c1 = CapabilityContract("cap1", "1.0")
        c2 = CapabilityContract("cap1", "1.0")
        registry.register(c1)
        assert registry.register(c2) is False

    def test_register_new_version(self):
        registry = CapabilityRegistry()
        c1 = CapabilityContract("cap1", "1.0")
        c2 = CapabilityContract("cap1", "2.0")
        registry.register(c1)
        assert registry.register(c2) is True

    def test_list_all_and_count(self):
        registry = CapabilityRegistry()
        assert registry.count() == 0
        registry.register(CapabilityContract("c1", "1.0"))
        registry.register(CapabilityContract("c2", "1.0"))
        assert registry.count() == 2
        assert len(registry.list_all()) == 2
        assert len(registry.list_ids()) == 2

    def test_validate_unknown_capability(self):
        registry = CapabilityRegistry()
        result = registry.validate("unknown", {})
        assert result.valid is False
        assert "unknown" in str(result.errors)

    def test_validate_success(self):
        registry = CapabilityRegistry()
        contract = CapabilityContract(
            "cap1", "1.0",
            preconditions=[Predicate("ready")],
        )
        registry.register(contract)
        result = registry.validate("cap1", {}, {"ready": True})
        assert result.valid is True
        assert result.precond_ok is True
        assert result.input_ok is True

    def test_validate_failure(self):
        registry = CapabilityRegistry()
        contract = CapabilityContract(
            "cap1", "1.0",
            preconditions=[Predicate("ready")],
            input_schema={"required": ["name"]},
        )
        registry.register(contract)
        result = registry.validate("cap1", {}, {"ready": False})
        assert result.valid is False

    def test_validate_output_unknown(self):
        registry = CapabilityRegistry()
        result = registry.validate_output("unknown", {})
        assert result.valid is False

    def test_validate_output_success(self):
        registry = CapabilityRegistry()
        contract = CapabilityContract("cap1", "1.0", postconditions=[Predicate("done")])
        registry.register(contract)
        result = registry.validate_output("cap1", {}, {"done": True})
        assert result.valid is True

    def test_compose(self):
        registry = CapabilityRegistry()
        c1 = CapabilityContract("read", "1.0", preconditions=[Predicate("auth")])
        c2 = CapabilityContract("write", "1.0", preconditions=[Predicate("auth")])
        composite = registry.compose([c1, c2], CompositionMode.AND)
        assert isinstance(composite, CompositeContract)
        assert "composite" in composite.capability_id
        assert len(composite.sub_contracts) == 2

    def test_compatibility_matrix(self):
        registry = CapabilityRegistry()
        c1 = CapabilityContract("c1", "1.0", side_effects=["lock"])
        c2 = CapabilityContract("c2", "1.0", side_effects=["lock"])
        c3 = CapabilityContract("c3", "1.0", side_effects=[])
        registry.register(c1)
        registry.register(c2)
        registry.register(c3)
        matrix = registry.compatibility_matrix()
        assert matrix["c1"]["c1"] == 1.0
        assert matrix["c1"]["c2"] == 0.5
        assert matrix["c1"]["c3"] == 1.0

    def test_validation_log(self):
        registry = CapabilityRegistry()
        contract = CapabilityContract("cap1", "1.0", preconditions=[Predicate("ready")])
        registry.register(contract)
        registry.validate("cap1", {}, {"ready": True})
        assert len(registry.validation_log()) == 1


class TestCombinatorialRiskAnalyzer:
    def test_analyze_empty(self):
        registry = CapabilityRegistry()
        analyzer = CombinatorialRiskAnalyzer(registry)
        report = analyzer.analyze([])
        assert report.total_risk_score == 0.0
        assert report.max_pair_risk == 0.0

    def test_analyze_with_interactions(self):
        registry = CapabilityRegistry()
        registry.register(CapabilityContract("cap_a", "1.0"))
        registry.register(CapabilityContract("cap_b", "1.0"))
        analyzer = CombinatorialRiskAnalyzer(registry)
        report = analyzer.analyze(["cap_a", "cap_b"])
        assert isinstance(report.pairwise_interactions, list)

    def test_pairwise_interactions_unknown_cap(self):
        registry = CapabilityRegistry()
        analyzer = CombinatorialRiskAnalyzer(registry)
        interactions = analyzer.pairwise_interactions(["unknown"])
        assert interactions == []
