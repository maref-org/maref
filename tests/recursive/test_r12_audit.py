from __future__ import annotations

import json
import time

import pytest

from maref.governance.audit import AuditEntry, AuditLogger
from maref.recursive.evolution_dsl import (
    EvolutionAuditEntry,
    EvolutionDSL,
)
from maref.recursive.meta_governance import CrossLayerAuditEntry
from maref.recursive.self_healer import HealAction, HealingRecord
from maref.recursive.unified_audit import (
    UnifiedAuditRecord,
    UnifiedAuditStore,
    make_record_id,
)


class TestUnifiedAuditRecord:
    def test_create_record(self) -> None:
        record = UnifiedAuditRecord(
            record_id="rec_001",
            timestamp=1000.0,
            layer="inner",
            round=1,
            event_type="diagnosis",
            source_module="SelfDiagnostician",
            target_module="governance",
            decision="analyze_entropy",
            justification="entropy threshold exceeded",
            outcome="success",
            context_refs=["rec_000"],
        )
        assert record.record_id == "rec_001"
        assert record.layer == "inner"
        assert record.round == 1
        assert record.outcome == "success"

    def test_record_defaults(self) -> None:
        record = UnifiedAuditRecord(
            record_id="r",
            timestamp=0.0,
            layer="outer",
            round=2,
            event_type="healing",
            source_module="A",
            target_module="B",
            decision="fix",
            justification="needed",
        )
        assert record.outcome is None
        assert record.context_refs == []

    def test_to_dict_and_from_dict(self) -> None:
        original = UnifiedAuditRecord(
            record_id="rec_002",
            timestamp=2000.0,
            layer="meta",
            round=5,
            event_type="governance",
            source_module="MetaGovernance",
            target_module="inner_gov",
            decision="halt",
            justification="cb trip threshold exceeded",
            outcome="failure",
            context_refs=["rec_001", "rec_000"],
        )
        d = original.to_dict()
        restored = UnifiedAuditRecord.from_dict(d)
        assert restored.record_id == original.record_id
        assert restored.layer == original.layer
        assert restored.context_refs == original.context_refs

    def test_to_dict_json_serializable(self) -> None:
        record = UnifiedAuditRecord(
            record_id="r",
            timestamp=0.0,
            layer="evolution",
            round=10,
            event_type="evolution",
            source_module="A",
            target_module="B",
            decision="D",
            justification="J",
            outcome="success",
            context_refs=["r1", "r2"],
        )
        try:
            json.dumps(record.to_dict())
        except (TypeError, ValueError) as e:
            pytest.fail(f"Failed to serialize: {e}")


class TestUnifiedAuditStoreAppend:
    @pytest.fixture
    def store(self) -> UnifiedAuditStore:
        return UnifiedAuditStore()

    @pytest.fixture
    def records(self) -> list[UnifiedAuditRecord]:
        return [
            UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "test1", "success", []),
            UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "test2", "success", ["r1"]),
            UnifiedAuditRecord("r3", 3.0, "outer", 2, "governance", "MG", "inner", "halt", "test3", "failure", ["r2"]),
            UnifiedAuditRecord("r4", 4.0, "meta", 3, "governance", "MG", "outer", "open", "test4", "failure", ["r3"]),
            UnifiedAuditRecord("r5", 5.0, "evolution", 10, "evolution", "DSL", "cb", "tune", "test5", "success", []),
        ]

    def test_append_increases_count(self, store: UnifiedAuditStore, records: list[UnifiedAuditRecord]) -> None:
        for r in records:
            store.append(r)
        assert store.count() == 5

    def test_all_returns_all_records(self, store: UnifiedAuditStore, records: list[UnifiedAuditRecord]) -> None:
        for r in records:
            store.append(r)
        assert len(store.all()) == 5


class TestUnifiedAuditStoreQuery:
    @pytest.fixture
    def store(self) -> UnifiedAuditStore:
        s = UnifiedAuditStore()
        s.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SelfDiagnostician", "governance", "check", "test", "success", []))
        s.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SelfHealer", "governance", "repair", "test", "success", ["r1"]))
        s.append(UnifiedAuditRecord("r3", 3.0, "outer", 2, "governance", "MetaGovernance", "inner_l1", "halt", "test", "failure", ["r2"]))
        s.append(UnifiedAuditRecord("r4", 4.0, "evolution", 10, "evolution", "EvolutionDSL", "circuit_breaker", "tune", "test", "success", []))
        return s

    def test_query_by_layer_inner(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_layer("inner")
        assert len(results) == 2
        assert all(r.layer == "inner" for r in results)

    def test_query_by_layer_evolution(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_layer("evolution")
        assert len(results) == 1
        assert results[0].layer == "evolution"

    def test_query_by_layer_empty(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_layer("nonexistent")
        assert results == []

    def test_query_by_event_diagnosis(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_event("diagnosis")
        assert len(results) == 1
        assert results[0].event_type == "diagnosis"

    def test_query_by_module(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_module("SelfHealer")
        assert len(results) == 1
        assert results[0].source_module == "SelfHealer"

    def test_query_by_round(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_round(1)
        assert len(results) == 2

    def test_query_by_round_ten(self, store: UnifiedAuditStore) -> None:
        results = store.query_by_round(10)
        assert len(results) == 1


class TestUnifiedAuditStoreDecisionChain:
    def test_decision_chain_single(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", []))
        chain = store.query_decision_chain("r1")
        assert len(chain) == 1
        assert chain[0].record_id == "r1"

    def test_decision_chain_three_links(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", []))
        store.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "j", "success", ["r1"]))
        store.append(UnifiedAuditRecord("r3", 3.0, "outer", 2, "governance", "MG", "inner", "halt", "j", "failure", ["r2"]))
        chain = store.query_decision_chain("r3")
        assert len(chain) == 3

    def test_decision_chain_max_depth(self) -> None:
        store = UnifiedAuditStore()
        for i in range(15):
            prev = [] if i == 0 else [f"r{i}"]
            store.append(UnifiedAuditRecord(f"r{i+1}", float(i), "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", prev))
        chain = store.query_decision_chain("r15", max_depth=5)
        assert len(chain) <= 5

    def test_decision_chain_self_ref_avoids_loop(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", ["r2"]))
        store.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "j", "success", ["r1"]))
        chain = store.query_decision_chain("r1", max_depth=10)
        assert len(chain) == 2


class TestUnifiedAuditStoreStats:
    def test_stats_by_event_type(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", []))
        store.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "j", "success", ["r1"]))
        store.append(UnifiedAuditRecord("r3", 3.0, "inner", 1, "healing", "SH", "gov2", "repair2", "j", "success", []))
        stats = store.stats_by_event_type()
        assert stats["diagnosis"] == 1
        assert stats["healing"] == 2

    def test_stats_by_module(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", []))
        store.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "j", "success", ["r1"]))
        stats = store.stats_by_module()
        assert stats["SD"] == 1
        assert stats["SH"] == 1

    def test_stats_by_round(self) -> None:
        store = UnifiedAuditStore()
        store.append(UnifiedAuditRecord("r1", 1.0, "inner", 1, "diagnosis", "SD", "gov", "check", "j", "success", []))
        store.append(UnifiedAuditRecord("r2", 2.0, "inner", 1, "healing", "SH", "gov", "repair", "j", "success", ["r1"]))
        store.append(UnifiedAuditRecord("r3", 3.0, "outer", 2, "governance", "MG", "inner", "halt", "j", "failure", ["r2"]))
        stats = store.stats_by_round()
        assert stats[1] == 2
        assert stats[2] == 1


class TestAuditEntryToUnified:
    def test_audit_entry_to_unified(self) -> None:
        entry = AuditEntry(
            id="audit_001",
            timestamp=1000.0,
            event_type="anomaly_detected",
            actor="GovernanceOverlay",
            action="force_stabilize",
            details="entropy spike recovery",
            metadata={"target_module": "state_machine"},
        )
        unified = entry.to_unified(layer="governance", round_num=1)
        assert unified.record_id == "audit_001"
        assert unified.layer == "governance"
        assert unified.round == 1
        assert unified.event_type == "anomaly_detected"
        assert unified.source_module == "GovernanceOverlay"
        assert unified.target_module == "state_machine"
        assert unified.decision == "force_stabilize"

    def test_audit_entry_to_unified_trip_outcome(self) -> None:
        entry = AuditEntry(
            id="audit_002",
            timestamp=2000.0,
            event_type="circuit_breaker_trip",
            actor="CircuitBreaker",
            action="open",
            details="failure threshold exceeded",
        )
        unified = entry.to_unified()
        assert unified.outcome == "failure"

    def test_audit_entry_to_unified_success_outcome(self) -> None:
        entry = AuditEntry(
            id="audit_003",
            timestamp=3000.0,
            event_type="recovery",
            actor="SelfHealer",
            action="recover",
            details="successfully recovered",
        )
        unified = entry.to_unified()
        assert unified.outcome == "success"


class TestCrossLayerAuditEntryToUnified:
    def test_cross_layer_to_unified(self) -> None:
        entry = CrossLayerAuditEntry(
            timestamp=1000.0,
            layer="depth_1",
            inner_state="TRIPPED",
            outer_state="open",
            event="inner_cb_trip",
        )
        unified = entry.to_unified(round_num=5)
        assert unified.layer == "depth_1"
        assert unified.round == 5
        assert unified.event_type == "cross_layer_inner_cb_trip"
        assert unified.source_module == "MetaGovernance"
        assert unified.outcome == "failure"

    def test_cross_layer_recovery_to_unified(self) -> None:
        entry = CrossLayerAuditEntry(
            timestamp=2000.0,
            layer="depth_0",
            inner_state="RECOVERED",
            outer_state="closed",
            event="recovery_confirmed",
        )
        unified = entry.to_unified()
        assert unified.outcome == "success"


class TestHealingRecordToUnified:
    def test_healing_record_to_unified(self) -> None:
        record = HealingRecord(
            actions=[
                HealAction(problem_type="test_failure", strategy="rerun_tests", applied=True, result="simulated_recovery", iteration=0, exit_code=0),
                HealAction(problem_type="coverage_drop", strategy="identify_untested", applied=True, result="simulated_recovery", iteration=1, exit_code=0),
            ],
            final_state="HEALTHY",
            iterations=2,
            converged=True,
        )
        unified_list = record.to_unified(round_num=3)
        assert len(unified_list) == 2
        assert unified_list[0].event_type == "healing"
        assert unified_list[0].source_module == "SelfHealer"
        assert unified_list[0].outcome == "success"
        assert unified_list[0].round == 3

    def test_healing_record_with_failure(self) -> None:
        record = HealingRecord(
            actions=[
                HealAction(problem_type="unknown", strategy="full_system_scan", applied=True, result="needs_investigation", iteration=0),
            ],
            final_state="DEGRADED",
            iterations=1,
            converged=False,
        )
        unified_list = record.to_unified()
        assert len(unified_list) == 1
        assert unified_list[0].outcome == "failure"

    def test_healing_record_empty_actions(self) -> None:
        record = HealingRecord()
        unified_list = record.to_unified()
        assert unified_list == []


class TestEvolutionAuditEntryToUnified:
    def test_evolution_audit_to_unified_gate_passed(self) -> None:
        entry = EvolutionAuditEntry(
            rule_id="rule_001",
            target="coverage_target_pct",
            timestamp=time.time(),
            justification="increase coverage requirement",
            gate_passed=True,
        )
        unified = entry.to_unified()
        assert unified.record_id == "rule_001"
        assert unified.layer == "evolution"
        assert unified.round == 10
        assert unified.event_type == "evolution"
        assert unified.decision == "apply_rule"
        assert unified.outcome == "success"

    def test_evolution_audit_to_unified_gate_rejected(self) -> None:
        entry = EvolutionAuditEntry(
            rule_id="rule_002",
            target="circuit_breaker",
            timestamp=time.time(),
            justification="try to remove CB",
            gate_passed=False,
        )
        unified = entry.to_unified()
        assert unified.decision == "reject_rule"
        assert unified.outcome == "failure"


class TestUnifiedAuditE2E:
    def test_full_audit_flow(self) -> None:
        store = UnifiedAuditStore()

        audit_logger = AuditLogger()
        entry1 = audit_logger.log_anomaly(
            actor="GovernanceOverlay",
            anomaly_type="entropy_spike",
            severity="warning",
            description="entropy=4.5",
        )
        store.append(entry1.to_unified(layer="governance", round_num=1))

        cross_entry = CrossLayerAuditEntry(
            timestamp=time.time(),
            layer="depth_1",
            inner_state="TRIPPED",
            outer_state="open",
            event="inner_cb_trip",
        )
        store.append(cross_entry.to_unified(round_num=2))

        heal_record = HealingRecord(
            actions=[HealAction(problem_type="test_failure", strategy="rerun_tests", applied=True, result="simulated_recovery", iteration=0)],
            final_state="RECOVERED",
            iterations=1,
            converged=True,
        )
        for r in heal_record.to_unified(round_num=3):
            store.append(r)

        assert store.count() == 3
        assert len(store.query_by_layer("governance")) == 1
        assert len(store.query_by_layer("depth_1")) == 1
        assert len(store.query_by_event("healing")) == 1
        assert len(store.query_by_module("SelfHealer")) == 1

        entry1_ref = store.all()[0].record_id
        chain = store.query_decision_chain(entry1_ref)
        assert len(chain) >= 1

    def test_ten_round_audit_import(self) -> None:
        store = UnifiedAuditStore()

        dsl = EvolutionDSL()
        rules = dsl.load_default_rules()
        for rule in rules:
            dsl.apply(rule)
            for audit_entry in dsl.audit_trail():
                store.append(audit_entry.to_unified(round_num=10))

        assert store.count() >= 10
        evo_records = store.query_by_layer("evolution")
        assert len(evo_records) >= 10

    def test_make_record_id(self) -> None:
        rid = make_record_id("test", 42)
        assert rid.startswith("test_000042_")
