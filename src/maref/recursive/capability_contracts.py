from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class Predicate:
    name: str
    args: list[str] = field(default_factory=list)
    evaluate_fn: Callable[[dict[str, Any]], bool] | None = None

    def evaluate(self, state: dict[str, Any]) -> bool:
        if self.evaluate_fn is not None:
            return self.evaluate_fn(state)
        return state.get(self.name, False)

    def __hash__(self) -> int:
        return hash((self.name, tuple(self.args)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Predicate):
            return NotImplemented
        return self.name == other.name and self.args == other.args


class CompositionMode(str, Enum):
    AND = "AND"
    OR = "OR"


@dataclass
class CostProfile:
    base_cost: float = 0.0
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    estimated_max_cost: float = 0.0
    currency: str = "credit_token"

    def estimate(self, input_size: int = 0, output_size: int = 0) -> float:
        return self.base_cost + input_size * self.cost_per_input_token + output_size * self.cost_per_output_token


@dataclass
class CapabilityContract:
    capability_id: str
    version: str
    description: str = ""
    preconditions: list[Predicate] = field(default_factory=list)
    postconditions: list[Predicate] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    degradation_modes: list[str] = field(default_factory=list)
    cost_profile: CostProfile | None = None
    tags: list[str] = field(default_factory=list)
    required_trust_level: float = 0.0
    timeout_seconds: float = 30.0

    def validate_preconditions(self, state: dict[str, Any]) -> tuple[bool, list[str]]:
        failures: list[str] = []
        for pred in self.preconditions:
            if not pred.evaluate(state):
                failures.append(f"precondition failed: {pred.name}({', '.join(pred.args)})")
        return len(failures) == 0, failures

    def validate_postconditions(self, state: dict[str, Any]) -> tuple[bool, list[str]]:
        failures: list[str] = []
        for pred in self.postconditions:
            if not pred.evaluate(state):
                failures.append(f"postcondition failed: {pred.name}({', '.join(pred.args)})")
        return len(failures) == 0, failures

    def validate_input(self, input_data: dict[str, Any]) -> tuple[bool, list[str]]:
        if not self.input_schema:
            return True, []
        errors: list[str] = []
        required_fields = self.input_schema.get("required", [])
        if isinstance(required_fields, list):
            for field in required_fields:
                if isinstance(field, str) and field not in input_data:
                    errors.append(f"missing required input field: {field}")
        props = self.input_schema.get("properties", {})
        if isinstance(props, dict):
            for field, field_schema in props.items():
                if field in input_data and isinstance(field_schema, dict):
                    expected_type = field_schema.get("type")
                    if expected_type and not self._check_type(input_data[field], expected_type):
                        errors.append(f"type mismatch for {field}: expected {expected_type}")
        return len(errors) == 0, errors

    def validate_output(self, output_data: dict[str, Any]) -> tuple[bool, list[str]]:
        if not self.output_schema:
            return True, []
        errors: list[str] = []
        required_fields = self.output_schema.get("required", [])
        if isinstance(required_fields, list):
            for field in required_fields:
                if isinstance(field, str) and field not in output_data:
                    errors.append(f"missing required output field: {field}")
        return len(errors) == 0, errors

    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str, "integer": int, "number": (int, float),
            "boolean": bool, "array": list, "object": dict,
        }
        expected_type = type_map.get(expected)
        if expected_type is None:
            return True
        return isinstance(value, expected_type)

    def __hash__(self) -> int:
        return hash((self.capability_id, self.version))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CapabilityContract):
            return NotImplemented
        return self.capability_id == other.capability_id and self.version == other.version


@dataclass
class CompositeContract(CapabilityContract):
    sub_contracts: list[CapabilityContract] = field(default_factory=list)
    composition_mode: CompositionMode = CompositionMode.AND

    def validate_preconditions(self, state: dict[str, Any]) -> tuple[bool, list[str]]:
        all_failures: list[str] = []
        if self.composition_mode == CompositionMode.AND:
            for sub in self.sub_contracts:
                ok, failures = sub.validate_preconditions(state)
                all_failures.extend(failures)
            return len(all_failures) == 0, all_failures
        else:
            for sub in self.sub_contracts:
                ok, _ = sub.validate_preconditions(state)
                if ok:
                    return True, []
            return False, ["no sub-contract preconditions satisfied (OR mode)"]

    def validate_postconditions(self, state: dict[str, Any]) -> tuple[bool, list[str]]:
        all_failures: list[str] = []
        for sub in self.sub_contracts:
            ok, failures = sub.validate_postconditions(state)
            all_failures.extend(failures)
        return len(all_failures) == 0, all_failures


@dataclass
class ContractValidationResult:
    valid: bool
    contract_id: str
    precond_ok: bool = True
    postcond_ok: bool = True
    input_ok: bool = True
    output_ok: bool = True
    errors: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class InteractionRisk:
    cap_a: str
    cap_b: str
    risk_type: str
    description: str
    risk_score: float

    def __hash__(self) -> int:
        return hash((self.cap_a, self.cap_b, self.risk_type))


@dataclass
class CombinatorialRiskReport:
    capability_set: list[str]
    pairwise_interactions: list[InteractionRisk] = field(default_factory=list)
    total_risk_score: float = 0.0
    max_pair_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._contracts: dict[str, CapabilityContract] = {}
        self._validation_log: list[ContractValidationResult] = []

    def register(self, contract: CapabilityContract) -> bool:
        key = contract.capability_id
        if key in self._contracts:
            existing = self._contracts[key]
            if existing.version == contract.version:
                return False
        self._contracts[key] = contract
        return True

    def get(self, capability_id: str) -> CapabilityContract | None:
        return self._contracts.get(capability_id)

    def list_all(self) -> list[CapabilityContract]:
        return list(self._contracts.values())

    def list_ids(self) -> list[str]:
        return list(self._contracts.keys())

    def count(self) -> int:
        return len(self._contracts)

    def validate(self, capability_id: str, input_data: dict[str, Any],
                 state: dict[str, Any] | None = None) -> ContractValidationResult:
        contract = self._contracts.get(capability_id)
        if contract is None:
            return ContractValidationResult(
                valid=False, contract_id=capability_id,
                errors=[f"unknown capability: {capability_id}"],
            )
        state = state or {}
        precond_ok, precond_errs = contract.validate_preconditions(state)
        input_ok, input_errs = contract.validate_input(input_data)
        errors = precond_errs + input_errs
        result = ContractValidationResult(
            valid=precond_ok and input_ok,
            contract_id=capability_id,
            precond_ok=precond_ok,
            input_ok=input_ok,
            errors=errors,
        )
        self._validation_log.append(result)
        return result

    def validate_output(self, capability_id: str,
                        output_data: dict[str, Any],
                        state: dict[str, Any] | None = None) -> ContractValidationResult:
        contract = self._contracts.get(capability_id)
        if contract is None:
            return ContractValidationResult(
                valid=False, contract_id=capability_id,
                errors=[f"unknown capability: {capability_id}"],
            )
        state = state or {}
        postcond_ok, postcond_errs = contract.validate_postconditions(state)
        output_ok, output_errs = contract.validate_output(output_data)
        errors = postcond_errs + output_errs
        result = ContractValidationResult(
            valid=postcond_ok and output_ok,
            contract_id=capability_id,
            postcond_ok=postcond_ok,
            output_ok=output_ok,
            errors=errors,
        )
        self._validation_log.append(result)
        return result

    def compose(self, contracts: list[CapabilityContract],
                mode: CompositionMode = CompositionMode.AND) -> CompositeContract:
        combined_id = "_and_".join(c.capability_id for c in contracts)
        preconds: list[Predicate] = []
        postconds: list[Predicate] = []
        side_effects: list[str] = []
        for c in contracts:
            preconds.extend(c.preconditions)
            postconds.extend(c.postconditions)
            side_effects.extend(c.side_effects)
        return CompositeContract(
            capability_id=f"composite_{combined_id}",
            version="1.0.0",
            description=f"Composite of: {combined_id}",
            preconditions=preconds,
            postconditions=postconds,
            side_effects=list(dict.fromkeys(side_effects)),
            composition_mode=mode,
            sub_contracts=list(contracts),
        )

    def compatibility_matrix(self) -> dict[str, dict[str, float]]:
        ids = self.list_ids()
        matrix: dict[str, dict[str, float]] = {}
        for cid_a in ids:
            matrix[cid_a] = {}
            ca = self._contracts[cid_a]
            for cid_b in ids:
                if cid_a == cid_b:
                    matrix[cid_a][cid_b] = 1.0
                    continue
                cb = self._contracts[cid_b]
                shared_side = set(ca.side_effects) & set(cb.side_effects)
                if shared_side:
                    matrix[cid_a][cid_b] = 0.5
                else:
                    matrix[cid_a][cid_b] = 1.0
        return matrix

    def validation_log(self) -> list[ContractValidationResult]:
        return list(self._validation_log)


class CombinatorialRiskAnalyzer:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def analyze(self, capability_ids: list[str]) -> CombinatorialRiskReport:
        interactions = self.pairwise_interactions(capability_ids)
        total_risk = sum(ir.risk_score for ir in interactions)
        max_pair = max((ir.risk_score for ir in interactions), default=0.0)
        recommendations: list[str] = []
        for ir in interactions:
            if ir.risk_score >= 0.7:
                recommendations.append(
                    f"HIGH: {ir.cap_a} × {ir.cap_b} → {ir.risk_type}: {ir.description}"
                )
            elif ir.risk_score >= 0.3:
                recommendations.append(
                    f"MEDIUM: {ir.cap_a} × {ir.cap_b} → {ir.risk_type}: {ir.description}"
                )
        return CombinatorialRiskReport(
            capability_set=list(capability_ids),
            pairwise_interactions=interactions,
            total_risk_score=total_risk,
            max_pair_risk=max_pair,
            recommendations=recommendations,
        )

    def pairwise_interactions(self, capability_ids: list[str]) -> list[InteractionRisk]:
        interactions: list[InteractionRisk] = []
        for i, cid_a in enumerate(capability_ids):
            ca = self._registry.get(cid_a)
            if ca is None:
                continue
            for cid_b in capability_ids[i + 1:]:
                cb = self._registry.get(cid_b)
                if cb is None:
                    continue
                risk = self._assess_pair(ca, cb)
                if risk is not None:
                    interactions.append(risk)
        return interactions

    def _assess_pair(self, ca: CapabilityContract,
                     cb: CapabilityContract) -> InteractionRisk | None:
        shared_side = set(ca.side_effects) & set(cb.side_effects)
        risk_tags_a = set(ca.tags)
        risk_tags_b = set(cb.tags)
        dangerous_tags = {"mutation", "halt", "state_change", "circuit_break", "escalation"}

        risk_score = 0.0
        risk_parts: list[str] = []

        if shared_side:
            risk_score += 0.4
            risk_parts.append(f"shared side effects: {shared_side}")

        a_dangerous = risk_tags_a & dangerous_tags
        b_dangerous = risk_tags_b & dangerous_tags
        if a_dangerous and b_dangerous:
            risk_score += 0.5
            risk_parts.append(f"dual dangerous tags: {a_dangerous | b_dangerous}")

        a_precond_names = {p.name for p in ca.preconditions}
        b_precond_names = {p.name for p in cb.preconditions}
        if a_precond_names & b_precond_names:
            risk_score += 0.2
            risk_parts.append("shared preconditions (possible contention)")

        if risk_score == 0.0 and not risk_parts:
            return None

        return InteractionRisk(
            cap_a=ca.capability_id,
            cap_b=cb.capability_id,
            risk_type="; ".join(risk_parts) if risk_parts else "low",
            description="Interaction risk between capabilities",
            risk_score=min(risk_score, 1.0),
        )


def build_default_capability_contracts() -> list[CapabilityContract]:
    contracts: list[CapabilityContract] = []

    contracts.append(CapabilityContract(
        capability_id="state_transition",
        version="1.0.0",
        description="Execute a state transition in the governance state machine",
        preconditions=[Predicate(name="governance_agent_active")],
        postconditions=[Predicate(name="state_transition_completed")],
        input_schema={
            "type": "object",
            "required": ["from_state", "to_state"],
            "properties": {
                "from_state": {"type": "string"},
                "to_state": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["transition_id", "success"],
        },
        side_effects=["state_change", "audit_log_append"],
        tags=["state_change"],
        required_trust_level=0.3,
        timeout_seconds=10.0,
        cost_profile=CostProfile(base_cost=0.01),
    ))

    contracts.append(CapabilityContract(
        capability_id="circuit_break",
        version="1.0.0",
        description="Trip the circuit breaker to halt operations",
        preconditions=[Predicate(name="circuit_breaker_closed")],
        postconditions=[Predicate(name="circuit_breaker_open")],
        input_schema={
            "type": "object",
            "required": ["reason"],
            "properties": {"reason": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["breaker_state", "tripped_at"],
        },
        side_effects=["circuit_breaker_trip", "halt_all_operations"],
        degradation_modes=["partial_halt", "read_only_mode"],
        tags=["halt", "circuit_break", "mutation"],
        required_trust_level=0.8,
        timeout_seconds=5.0,
        cost_profile=CostProfile(base_cost=0.0),
    ))

    contracts.append(CapabilityContract(
        capability_id="halt",
        version="1.0.0",
        description="Immediately halt all agent operations",
        preconditions=[Predicate(name="agent_operational")],
        postconditions=[Predicate(name="agent_halted")],
        input_schema={
            "type": "object",
            "required": ["reason"],
            "properties": {"reason": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["halted_at"],
        },
        side_effects=["halt_all_operations", "freeze_agent_state"],
        tags=["halt", "mutation", "escalation"],
        required_trust_level=0.9,
        timeout_seconds=5.0,
        cost_profile=CostProfile(base_cost=0.0),
    ))

    contracts.append(CapabilityContract(
        capability_id="observe",
        version="1.0.0",
        description="Observe system metrics and agent behavior",
        preconditions=[Predicate(name="observer_active")],
        postconditions=[Predicate(name="observation_recorded")],
        input_schema={
            "type": "object",
            "properties": {
                "metric_names": {"type": "array", "items": {"type": "string"}},
            },
        },
        output_schema={
            "type": "object",
            "required": ["metrics", "timestamp"],
        },
        side_effects=["metrics_collection"],
        degradation_modes=["reduced_frequency", "sampling_mode"],
        tags=[],
        required_trust_level=0.0,
        timeout_seconds=30.0,
        cost_profile=CostProfile(base_cost=0.001),
    ))

    contracts.append(CapabilityContract(
        capability_id="collect",
        version="1.0.0",
        description="Collect telemetry data from sidecar proxies",
        preconditions=[Predicate(name="sidecar_connected")],
        postconditions=[Predicate(name="telemetry_collected")],
        input_schema={
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "string"}},
            },
        },
        output_schema={
            "type": "object",
            "required": ["collected_data", "target_count"],
        },
        side_effects=["data_collection"],
        tags=[],
        required_trust_level=0.0,
        timeout_seconds=60.0,
        cost_profile=CostProfile(base_cost=0.002),
    ))

    contracts.append(CapabilityContract(
        capability_id="monitor",
        version="1.0.0",
        description="Continuously monitor agent health and governance state",
        preconditions=[Predicate(name="monitor_running")],
        postconditions=[Predicate(name="monitor_cycle_complete")],
        input_schema={
            "type": "object",
            "properties": {
                "duration_seconds": {"type": "number"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["health_status", "anomalies"],
        },
        side_effects=["continuous_monitoring"],
        degradation_modes=["reduced_interval"],
        tags=[],
        required_trust_level=0.1,
        timeout_seconds=300.0,
        cost_profile=CostProfile(base_cost=0.005),
    ))

    contracts.append(CapabilityContract(
        capability_id="graph_query",
        version="1.0.0",
        description="Query the knowledge graph for nodes and relations",
        preconditions=[Predicate(name="kg_initialized")],
        postconditions=[Predicate(name="query_executed")],
        input_schema={
            "type": "object",
            "required": ["query_type"],
            "properties": {
                "query_type": {"type": "string"},
                "filters": {"type": "object"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["results", "count"],
        },
        side_effects=["kg_read"],
        tags=[],
        required_trust_level=0.0,
        timeout_seconds=15.0,
        cost_profile=CostProfile(base_cost=0.001),
    ))

    contracts.append(CapabilityContract(
        capability_id="hypothesis_test",
        version="1.0.0",
        description="Form and test hypotheses using the knowledge graph",
        preconditions=[Predicate(name="kg_initialized"), Predicate(name="hypothesis_cycle_active")],
        postconditions=[Predicate(name="hypothesis_result_recorded")],
        input_schema={
            "type": "object",
            "required": ["hypothesis", "test_method"],
            "properties": {
                "hypothesis": {"type": "string"},
                "test_method": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["result", "confidence"],
        },
        side_effects=["kg_write", "hypothesis_log"],
        tags=[],
        required_trust_level=0.2,
        timeout_seconds=30.0,
        cost_profile=CostProfile(base_cost=0.003),
    ))

    contracts.append(CapabilityContract(
        capability_id="relation_infer",
        version="1.0.0",
        description="Infer new relations between knowledge graph nodes",
        preconditions=[Predicate(name="kg_initialized")],
        postconditions=[Predicate(name="inferred_relations_added")],
        input_schema={
            "type": "object",
            "properties": {
                "source_node": {"type": "string"},
                "max_inferences": {"type": "integer"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["inferred_relations", "count"],
        },
        side_effects=["kg_write"],
        tags=[],
        required_trust_level=0.1,
        timeout_seconds=20.0,
        cost_profile=CostProfile(base_cost=0.002),
    ))

    contracts.append(CapabilityContract(
        capability_id="did_resolve",
        version="1.0.0",
        description="Resolve a decentralized identifier to its DID document",
        preconditions=[Predicate(name="did_registry_active")],
        postconditions=[Predicate(name="did_resolved")],
        input_schema={
            "type": "object",
            "required": ["did"],
            "properties": {"did": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["did_document", "resolution_metadata"],
        },
        side_effects=["did_lookup"],
        tags=[],
        required_trust_level=0.0,
        timeout_seconds=10.0,
        cost_profile=CostProfile(base_cost=0.001),
    ))

    contracts.append(CapabilityContract(
        capability_id="vc_verify",
        version="1.0.0",
        description="Verify a verifiable credential's proof and status",
        preconditions=[Predicate(name="credential_store_active")],
        postconditions=[Predicate(name="vc_verified")],
        input_schema={
            "type": "object",
            "required": ["credential_id"],
            "properties": {
                "credential_id": {"type": "string"},
                "challenge": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["valid", "verification_details"],
        },
        side_effects=["vc_verification"],
        tags=[],
        required_trust_level=0.1,
        timeout_seconds=10.0,
        cost_profile=CostProfile(base_cost=0.001),
    ))

    contracts.append(CapabilityContract(
        capability_id="trust_evaluate",
        version="1.0.0",
        description="Evaluate trust score for an agent using multi-factor analysis",
        preconditions=[Predicate(name="trust_engine_active")],
        postconditions=[Predicate(name="trust_score_computed")],
        input_schema={
            "type": "object",
            "required": ["agent_id"],
            "properties": {"agent_id": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["trust_score", "factors"],
        },
        side_effects=["trust_computation"],
        tags=[],
        required_trust_level=0.2,
        timeout_seconds=15.0,
        cost_profile=CostProfile(base_cost=0.002),
    ))

    return contracts
