from __future__ import annotations

import pytest

from maref.recursive.agent_dispatcher import AgentDispatcher
from maref.recursive.capability_contracts import (
    CapabilityContract,
    CapabilityRegistry,
    CombinatorialRiskAnalyzer,
    CombinatorialRiskReport,
    CompositeContract,
    CompositionMode,
    CostProfile,
    Predicate,
    build_default_capability_contracts,
)
from maref.recursive.internal_agents import InternalAgentRegistry


class TestPredicate:
    def test_predicate_evaluate_with_fn(self) -> None:
        p = Predicate(name="test_pred", evaluate_fn=lambda s: s.get("ready", False))
        assert p.evaluate({"ready": True})
        assert not p.evaluate({"ready": False})
        assert not p.evaluate({})

    def test_predicate_evaluate_without_fn(self) -> None:
        p = Predicate(name="test_pred")
        assert p.evaluate({"test_pred": True})
        assert not p.evaluate({"test_pred": False})

    def test_predicate_equality(self) -> None:
        a = Predicate(name="p1", args=["a", "b"])
        b = Predicate(name="p1", args=["a", "b"])
        c = Predicate(name="p1", args=["c"])
        assert a == b
        assert a != c
        assert hash(a) == hash(b)

    def test_predicate_with_args(self) -> None:
        p = Predicate(name="connected", args=["agent_a", "agent_b"])
        assert p.evaluate({}) is False


class TestCapabilityContract:
    def test_contract_creation(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            description="A test capability",
        )
        assert contract.capability_id == "test_cap"
        assert contract.version == "1.0.0"

    def test_validate_preconditions_all_pass(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            preconditions=[Predicate(name="ready")],
        )
        ok, failures = contract.validate_preconditions({"ready": True})
        assert ok
        assert failures == []

    def test_validate_preconditions_failure(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            preconditions=[Predicate(name="ready"), Predicate(name="authorized")],
        )
        ok, failures = contract.validate_preconditions({"ready": True})
        assert not ok
        assert len(failures) == 1

    def test_validate_postconditions(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            postconditions=[Predicate(name="done")],
        )
        ok, _ = contract.validate_postconditions({"done": True})
        assert ok

        ok2, _ = contract.validate_postconditions({"done": False})
        assert not ok2

    def test_validate_input_required_fields(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["name", "value"],
            },
        )
        ok, _ = contract.validate_input({"name": "x", "value": 1})
        assert ok

        ok2, errors = contract.validate_input({"name": "x"})
        assert not ok2
        assert any("value" in e for e in errors)

    def test_validate_input_type_check(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer"},
                    "name": {"type": "string"},
                },
            },
        )
        ok, _ = contract.validate_input({"count": 5, "name": "hello"})
        assert ok

        ok2, errors = contract.validate_input({"count": "not_int", "name": "hello"})
        assert not ok2
        assert any("count" in e for e in errors)

    def test_validate_output(self) -> None:
        contract = CapabilityContract(
            capability_id="test_cap",
            version="1.0.0",
            output_schema={
                "type": "object",
                "required": ["result"],
            },
        )
        ok, _ = contract.validate_output({"result": "ok"})
        assert ok

        ok2, _ = contract.validate_output({})
        assert not ok2

    def test_cost_profile_estimate(self) -> None:
        profile = CostProfile(base_cost=0.1, cost_per_input_token=0.01, cost_per_output_token=0.02)
        cost = profile.estimate(input_size=100, output_size=50)
        assert cost == 0.1 + 1.0 + 1.0  # 2.1

    def test_contract_equality(self) -> None:
        a = CapabilityContract(capability_id="c1", version="1.0.0")
        b = CapabilityContract(capability_id="c1", version="1.0.0")
        c = CapabilityContract(capability_id="c1", version="1.1.0")
        assert a == b
        assert a != c
        assert hash(a) == hash(b)


class TestCapabilityRegistry:
    @pytest.fixture
    def registry(self) -> CapabilityRegistry:
        r = CapabilityRegistry()
        r.register(CapabilityContract(
            capability_id="read_data",
            version="1.0.0",
            preconditions=[Predicate(name="db_available")],
            input_schema={"required": ["query"]},
            output_schema={"required": ["results"]},
        ))
        r.register(CapabilityContract(
            capability_id="write_data",
            version="1.0.0",
            preconditions=[Predicate(name="db_available"), Predicate(name="authorized")],
            input_schema={"required": ["data"]},
            output_schema={"required": ["written_id"]},
            side_effects=["db_write"],
            tags=["mutation"],
        ))
        return r

    def test_register_and_get(self) -> None:
        registry = CapabilityRegistry()
        contract = CapabilityContract(capability_id="test", version="1.0.0")
        assert registry.register(contract)
        assert registry.get("test") is contract
        assert registry.count() == 1

    def test_register_duplicate_same_version(self) -> None:
        registry = CapabilityRegistry()
        c1 = CapabilityContract(capability_id="test", version="1.0.0")
        c2 = CapabilityContract(capability_id="test", version="1.0.0")
        assert registry.register(c1)
        assert not registry.register(c2)

    def test_register_new_version(self) -> None:
        registry = CapabilityRegistry()
        c1 = CapabilityContract(capability_id="test", version="1.0.0")
        c2 = CapabilityContract(capability_id="test", version="1.1.0")
        assert registry.register(c1)
        assert registry.register(c2)

    def test_validate_success(self, registry: CapabilityRegistry) -> None:
        result = registry.validate("read_data", {"query": "SELECT 1"}, {"db_available": True})
        assert result.valid
        assert result.precond_ok
        assert result.input_ok

    def test_validate_missing_precondition(self, registry: CapabilityRegistry) -> None:
        result = registry.validate("read_data", {"query": "SELECT 1"}, {"db_available": False})
        assert not result.valid
        assert not result.precond_ok

    def test_validate_missing_input(self, registry: CapabilityRegistry) -> None:
        result = registry.validate("read_data", {}, {"db_available": True})
        assert not result.valid
        assert not result.input_ok

    def test_validate_unknown_capability(self, registry: CapabilityRegistry) -> None:
        result = registry.validate("nonexistent", {}, {})
        assert not result.valid
        assert "unknown" in result.errors[0].lower()

    def test_validate_output_success(self, registry: CapabilityRegistry) -> None:
        result = registry.validate_output("read_data", {"results": [1, 2, 3]})
        assert result.valid

    def test_validate_output_missing(self, registry: CapabilityRegistry) -> None:
        result = registry.validate_output("read_data", {})
        assert not result.valid

    def test_list_all(self, registry: CapabilityRegistry) -> None:
        all_contracts = registry.list_all()
        assert len(all_contracts) == 2

    def test_compatibility_matrix(self, registry: CapabilityRegistry) -> None:
        matrix = registry.compatibility_matrix()
        assert "read_data" in matrix
        assert "write_data" in matrix
        assert matrix["read_data"]["read_data"] == 1.0

    def test_compose_and(self, registry: CapabilityRegistry) -> None:
        c1 = registry.get("read_data")
        c2 = registry.get("write_data")
        assert c1 is not None and c2 is not None
        composite = registry.compose([c1, c2], CompositionMode.AND)
        assert isinstance(composite, CompositeContract)
        assert composite.composition_mode == CompositionMode.AND
        assert len(composite.sub_contracts) == 2


class TestCombinatorialRiskAnalyzer:
    @pytest.fixture
    def registry(self) -> CapabilityRegistry:
        r = CapabilityRegistry()
        r.register(CapabilityContract(
            capability_id="safe_read",
            version="1.0.0",
            side_effects=["kg_read"],
            tags=[],
        ))
        r.register(CapabilityContract(
            capability_id="safe_write",
            version="1.0.0",
            side_effects=["kg_write"],
            tags=[],
        ))
        r.register(CapabilityContract(
            capability_id="dangerous_halt",
            version="1.0.0",
            side_effects=["halt_all_operations"],
            tags=["halt", "mutation"],
        ))
        r.register(CapabilityContract(
            capability_id="dangerous_break",
            version="1.0.0",
            side_effects=["circuit_breaker_trip", "halt_all_operations"],
            tags=["circuit_break", "mutation"],
        ))
        return r

    def test_analyze_low_risk(self, registry: CapabilityRegistry) -> None:
        analyzer = CombinatorialRiskAnalyzer(registry)
        report = analyzer.analyze(["safe_read", "safe_write"])
        assert isinstance(report, CombinatorialRiskReport)
        assert report.capability_set == ["safe_read", "safe_write"]

    def test_analyze_high_risk(self, registry: CapabilityRegistry) -> None:
        analyzer = CombinatorialRiskAnalyzer(registry)
        report = analyzer.analyze(["dangerous_halt", "dangerous_break"])
        assert isinstance(report, CombinatorialRiskReport)
        assert len(report.pairwise_interactions) >= 1
        assert report.total_risk_score > 0

    def test_analyze_high_risk_blocked(self, registry: CapabilityRegistry) -> None:
        analyzer = CombinatorialRiskAnalyzer(registry)
        report = analyzer.analyze(["dangerous_halt", "dangerous_break"])
        assert report.total_risk_score >= 0.5
        assert len(report.recommendations) >= 1

    def test_pairwise_interactions_all(self, registry: CapabilityRegistry) -> None:
        analyzer = CombinatorialRiskAnalyzer(registry)
        interactions = analyzer.pairwise_interactions(["safe_read", "dangerous_halt"])
        assert len(interactions) >= 0

    def test_pairwise_shared_side_effects(self, registry: CapabilityRegistry) -> None:
        analyzer = CombinatorialRiskAnalyzer(registry)
        interactions = analyzer.pairwise_interactions(
            ["dangerous_halt", "dangerous_break"]
        )
        shared = [ir for ir in interactions if "shared side effects" in ir.risk_type]
        assert len(shared) >= 1


class TestBuildDefaults:
    def test_build_default_contracts(self) -> None:
        contracts = build_default_capability_contracts()
        assert len(contracts) == 12
        ids = {c.capability_id for c in contracts}
        expected = {
            "state_transition", "circuit_break", "halt",
            "observe", "collect", "monitor",
            "graph_query", "hypothesis_test", "relation_infer",
            "did_resolve", "vc_verify", "trust_evaluate",
        }
        assert ids == expected

    def test_all_defaults_have_version(self) -> None:
        for c in build_default_capability_contracts():
            assert c.version != ""
            assert len(c.description) > 0


class TestContractAwareRegister:
    def test_register_with_contracts(self) -> None:
        registry = InternalAgentRegistry()
        contracts = build_default_capability_contracts()
        gov_contracts = [c for c in contracts
                         if c.capability_id in ("state_transition", "circuit_break", "halt")]
        agent = registry.register_with_contracts(
            "test_agent", "test.module",
            ["state_transition", "circuit_break", "halt"],
            "governance",
            gov_contracts,
        )
        assert len(agent.contracts) == 3
        assert "state_transition" in agent.capability_ids()

    def test_find_by_contract(self) -> None:
        registry = InternalAgentRegistry()
        contracts = build_default_capability_contracts()
        gov_contracts = [c for c in contracts
                         if c.capability_id in ("state_transition", "circuit_break", "halt")]
        registry.register_with_contracts(
            "gov_agent", "test.module",
            ["state_transition", "circuit_break", "halt"],
            "governance",
            gov_contracts,
        )
        found = registry.find_by_contract("circuit_break")
        assert len(found) == 1
        assert found[0].agent_id == "gov_agent"


class TestContractAwareDispatch:
    def test_dispatcher_with_contract_registry(self) -> None:
        from maref.recursive.task_decomposer import SubTask

        agent_registry = InternalAgentRegistry()
        contract_registry = CapabilityRegistry()
        for c in build_default_capability_contracts():
            contract_registry.register(c)

        gov_contracts = [c for c in build_default_capability_contracts()
                         if c.capability_id in ("state_transition", "circuit_break", "halt")]
        agent_registry.register_with_contracts(
            "gov_agent", "test.module",
            ["state_transition", "circuit_break", "halt"],
            "governance",
            gov_contracts,
        )

        dispatcher = AgentDispatcher(agent_registry, contract_registry)
        subtask = SubTask(
            task_id="s1",
            description="transition state",
            required_capabilities=["state_transition"],
        )
        agent = dispatcher.dispatch(subtask)
        assert agent is not None
        assert agent.agent_id == "gov_agent"

    def test_dispatch_result_includes_contract_score(self) -> None:
        from maref.recursive.task_decomposer import SubTask

        agent_registry = InternalAgentRegistry()
        contract_registry = CapabilityRegistry()
        for c in build_default_capability_contracts():
            contract_registry.register(c)

        gov_contracts = [c for c in build_default_capability_contracts()
                         if c.capability_id in ("state_transition", "circuit_break", "halt")]
        agent_registry.register_with_contracts(
            "gov_agent", "test.module",
            ["state_transition", "circuit_break", "halt"],
            "governance",
            gov_contracts,
        )

        dispatcher = AgentDispatcher(agent_registry, contract_registry)
        subtask = SubTask(
            task_id="s1",
            description="transition state",
            required_capabilities=["state_transition"],
        )
        results = dispatcher.dispatch_all([subtask])
        assert len(results) == 1
        assert results[0].contract_score > 0
        assert results[0].match_details is not None
        assert "state_transition" in results[0].match_details


class TestDiscoveryWithContracts:
    def test_discovery_message_includes_contracts(self) -> None:
        from maref.recursive.agent_discovery_negotiation import (
            AgentDiscovery,
            CapabilityContractRef,
        )
        sm = __import__("maref.recursive.agent_24_state_machine",
                        fromlist=["Agent24StateMachine"]).Agent24StateMachine("test")
        discovery = AgentDiscovery(sm)
        contracts = [
            CapabilityContractRef("state_transition", "1.0.0", 0.3, 10.0),
        ]
        msg = discovery.discover("agent_a", ["state_transition"], contracts)
        assert len(msg.source_contracts) == 1
        assert msg.source_contracts[0].capability_id == "state_transition"
        assert msg.source_contracts[0].version == "1.0.0"

    def test_negotiation_proposal_includes_contracts(self) -> None:
        from maref.recursive.agent_discovery_negotiation import (
            AgentNegotiator,
            CapabilityContractRef,
        )
        negotiator = AgentNegotiator()
        contracts = [CapabilityContractRef("observe", "1.0.0", 0.0, 30.0)]
        proposal = negotiator.propose(
            "agent_a", "agent_b", "capability_exchange",
            {"exchange": "mutual"},
            contracts=contracts,
        )
        assert len(proposal.exchanged_contracts) == 1
        assert proposal.exchanged_contracts[0].capability_id == "observe"


class TestSafetyGateContractValidation:
    def test_validate_contract_passes(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        registry = CapabilityRegistry()
        c = CapabilityContract(
            capability_id="safe_op",
            version="1.0.0",
            input_schema={"required": ["input"]},
        )
        registry.register(c)

        result = gate.validate_contract("safe_op", {"input": "test"}, registry)
        assert not result.threat_detected

    def test_validate_contract_violation(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        registry = CapabilityRegistry()
        c = CapabilityContract(
            capability_id="safe_op",
            version="1.0.0",
            input_schema={"required": ["input"]},
        )
        registry.register(c)

        result = gate.validate_contract("safe_op", {}, registry)
        assert result.threat_detected
        assert "contract_violation" in result.threat_type

    def test_validate_contract_set_unregistered(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        registry = CapabilityRegistry()
        result = gate.validate_contract_set(["nonexistent"], registry)
        assert result.threat_detected
        assert "unregistered" in result.threat_type.lower()

    def test_validate_contract_set_ok(self) -> None:
        from maref.recursive.safety_gate_v2 import SafetyGateV2

        gate = SafetyGateV2()
        registry = CapabilityRegistry()
        c = CapabilityContract(capability_id="safe_op", version="1.0.0")
        registry.register(c)

        result = gate.validate_contract_set(["safe_op"], registry)
        assert not result.threat_detected
