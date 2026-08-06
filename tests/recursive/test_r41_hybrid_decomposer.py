from __future__ import annotations

from typing import Any

import pytest

from maref.recursive.complexity_budget import (
    ArchitectureComplexityBudget,
    ComplexityBudgetConfig,
)
from maref.recursive.hybrid_decomposer import (
    DecompositionCacheEntry,
    HybridDecomposer,
)
from maref.recursive.task_decomposer import TaskDecomposer


class MockLLMBackend:
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0
        self.last_prompt: str = ""

    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        self.last_prompt = prompt
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count]
            self._call_count += 1
            return result
        return {"subtasks": []}

    def add_response(self, response: dict[str, Any]) -> None:
        self._responses.append(response)

    @property
    def call_count(self) -> int:
        return self._call_count


def _make_valid_response() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": "analyze_input",
                "description": "Analyze input data",
                "capabilities": ["observe", "collect"],
                "dependencies": [],
            },
            {
                "id": "process_core",
                "description": "Process core logic",
                "capabilities": ["graph_query", "hypothesis_test"],
                "dependencies": ["analyze_input"],
            },
            {
                "id": "validate_output",
                "description": "Validate output results",
                "capabilities": ["trust_evaluate", "vc_verify"],
                "dependencies": ["process_core"],
            },
        ]
    }


def _make_cyclic_response() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": "step_a",
                "description": "Step A",
                "capabilities": ["observe"],
                "dependencies": ["step_b"],
            },
            {
                "id": "step_b",
                "description": "Step B",
                "capabilities": ["collect"],
                "dependencies": ["step_a"],
            },
        ]
    }


def _make_explosion_response() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": f"task_{i}",
                "description": f"Task {i}",
                "capabilities": ["observe"],
                "dependencies": [],
            }
            for i in range(15)
        ]
    }


def _make_dangerous_response() -> dict[str, Any]:
    return {
        "subtasks": [
            {
                "id": "halt_all",
                "description": "Halt all operations",
                "capabilities": ["halt", "circuit_break"],
                "dependencies": [],
            },
            {
                "id": "task_1",
                "description": "Task 1",
                "capabilities": ["observe"],
                "dependencies": [],
            },
            {
                "id": "task_2",
                "description": "Task 2",
                "capabilities": ["collect"],
                "dependencies": [],
            },
            {
                "id": "task_3",
                "description": "Task 3",
                "capabilities": ["monitor"],
                "dependencies": [],
            },
            {
                "id": "task_4",
                "description": "Task 4",
                "capabilities": ["graph_query"],
                "dependencies": [],
            },
            {
                "id": "task_5",
                "description": "Task 5",
                "capabilities": ["hypothesis_test"],
                "dependencies": [],
            },
            {
                "id": "task_6",
                "description": "Task 6",
                "capabilities": ["state_transition"],
                "dependencies": [],
            },
            {
                "id": "task_7",
                "description": "Task 7",
                "capabilities": ["did_resolve"],
                "dependencies": [],
            },
            {
                "id": "task_8",
                "description": "Task 8",
                "capabilities": ["vc_verify"],
                "dependencies": [],
            },
            {
                "id": "task_9",
                "description": "Task 9",
                "capabilities": ["trust_evaluate"],
                "dependencies": [],
            },
        ]
    }


class TestHybridDecomposerInit:
    def test_default_init_no_llm(self) -> None:
        dec = HybridDecomposer()
        assert dec.llm_available is False
        assert dec.cache_size == 0

    def test_init_with_llm(self) -> None:
        llm = MockLLMBackend()
        dec = HybridDecomposer(llm_backend=llm)
        assert dec.llm_available is True

    def test_init_with_complexity_budget(self) -> None:
        budget = ArchitectureComplexityBudget()
        dec = HybridDecomposer(complexity_budget=budget)
        assert dec._budget is budget


class TestHybridDecomposerTemplateFallback:
    def test_decompose_known_template_no_llm(self) -> None:
        dec = HybridDecomposer()
        dag = dec.decompose("optimize_system")
        assert dag.node_count == 4
        assert "observe_perf" in dag.nodes
        assert dag.root_task == "optimize_system"

    def test_decompose_unknown_task_no_llm_returns_empty(self) -> None:
        dec = HybridDecomposer()
        dag = dec.decompose("completely_unknown_task")
        assert dag.node_count == 0
        assert dag.root_task == "completely_unknown_task"

    def test_decompose_diagnose_anomaly_no_llm(self) -> None:
        dec = HybridDecomposer()
        dag = dec.decompose("diagnose_anomaly")
        assert dag.node_count == 3
        assert "run_probes" in dag.nodes

    def test_decompose_identity_conflict_no_llm(self) -> None:
        dec = HybridDecomposer()
        dag = dec.decompose("resolve_identity_conflict")
        assert dag.node_count == 2
        assert "audit_dids" in dag.nodes


class TestHybridDecomposerLLM:
    def test_decompose_with_llm_success(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("custom_analysis_task")
        assert dag.node_count == 3
        assert "analyze_input" in dag.nodes
        assert "process_core" in dag.nodes
        assert "validate_output" in dag.nodes
        assert ("analyze_input", "process_core") in dag.edges
        assert ("process_core", "validate_output") in dag.edges
        assert llm.call_count == 1

    def test_decompose_unknown_task_with_llm(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("unknown_task")
        assert dag.node_count == 3

    def test_decompose_llm_failure_falls_back_to_template(self) -> None:
        llm = MockLLMBackend([{"subtasks": []}])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("optimize_system")
        assert dag.node_count == 4

    def test_decompose_llm_exception_returns_empty_for_unknown(self) -> None:
        class FailingLLM:
            def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
                raise RuntimeError("LLM unavailable")

        llm = FailingLLM()
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("unknown_task")
        assert dag.node_count == 0

    def test_decompose_with_context(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("custom_task", context={"priority": "high", "domain": "governance"})
        assert dag.node_count == 3
        assert "priority" in llm.last_prompt

    @pytest.mark.slow
    def test_caching_avoids_llm_call(self) -> None:
        llm = MockLLMBackend([_make_valid_response(), _make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag1 = dec.decompose("repeated_task")
        assert dag1.node_count == 3
        assert llm.call_count == 1
        dag2 = dec.decompose("repeated_task")
        assert dag2.node_count == 3
        assert llm.call_count == 1

    def test_llm_only_called_when_no_cache(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dec.decompose("task_only_once")
        assert llm.call_count == 1


class TestHybridDecomposerCycleDetection:
    def test_cyclic_dag_rejected(self) -> None:
        llm = MockLLMBackend([_make_cyclic_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("cyclic_task")
        assert dag.node_count == 0

    def test_self_loop_rejected(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": "self_ref",
                    "description": "Self reference",
                    "capabilities": ["observe"],
                    "dependencies": ["self_ref"],
                }
            ]
        }
        llm = MockLLMBackend([response])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("self_loop_task")
        assert dag.node_count == 0

    def test_diamond_dag_accepted(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": "start",
                    "description": "Start",
                    "capabilities": ["observe"],
                    "dependencies": [],
                },
                {
                    "id": "branch_a",
                    "description": "Branch A",
                    "capabilities": ["collect"],
                    "dependencies": ["start"],
                },
                {
                    "id": "branch_b",
                    "description": "Branch B",
                    "capabilities": ["monitor"],
                    "dependencies": ["start"],
                },
                {
                    "id": "merge",
                    "description": "Merge",
                    "capabilities": ["graph_query"],
                    "dependencies": ["branch_a", "branch_b"],
                },
            ]
        }
        llm = MockLLMBackend([response])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("diamond_task")
        assert dag.node_count == 4


class TestHybridDecomposerSafetyGate:
    def test_subtask_explosion_rejected_and_falls_back(self) -> None:
        llm = MockLLMBackend([_make_explosion_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("explosion_task")
        assert dag.node_count == 0

    def test_dangerous_capability_with_many_subtasks_rejected(self) -> None:
        llm = MockLLMBackend([_make_dangerous_response()])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("dangerous_task")
        assert dag.node_count == 0

    def test_dangerous_capability_few_subtasks_allowed(self) -> None:
        response = {
            "subtasks": [
                {
                    "id": "halt_check",
                    "description": "Check halt condition",
                    "capabilities": ["halt", "circuit_break"],
                    "dependencies": [],
                },
                {
                    "id": "verify",
                    "description": "Verify condition",
                    "capabilities": ["vc_verify"],
                    "dependencies": ["halt_check"],
                },
            ]
        }
        llm = MockLLMBackend([response])
        dec = HybridDecomposer(llm_backend=llm)
        dag = dec.decompose("safe_dangerous_task")
        assert dag.node_count == 2


class TestHybridDecomposerCache:
    def test_cache_hit_returns_cached_dag(self) -> None:
        dec = HybridDecomposer()
        dag1 = dec.decompose("optimize_system")
        assert dec.cache_size == 1
        dag2 = dec.decompose("optimize_system")
        assert dag1 == dag2
        assert dec.cache_size == 1

    def test_cache_different_tasks_separate_entries(self) -> None:
        dec = HybridDecomposer()
        dec.decompose("optimize_system")
        dec.decompose("diagnose_anomaly")
        assert dec.cache_size == 2

    def test_clear_cache(self) -> None:
        dec = HybridDecomposer()
        dec.decompose("optimize_system")
        assert dec.cache_size == 1
        dec.clear_cache()
        assert dec.cache_size == 0

    def test_warm_cache(self) -> None:
        dec = HybridDecomposer()
        count = dec.warm_cache(["optimize_system", "diagnose_anomaly", "unknown"])
        assert count == 2
        assert dec.cache_size == 2

    def test_cache_max_size_eviction(self) -> None:
        dec = HybridDecomposer()
        dec.MAX_CACHE_SIZE = 2
        dec.decompose("optimize_system")
        dec.decompose("diagnose_anomaly")
        assert dec.cache_size == 2
        dec.decompose("resolve_identity_conflict")
        assert dec.cache_size == 2
        cached_tasks = set(dec._cache.keys())
        assert "resolve_identity_conflict" in cached_tasks


class TestDecompositionCacheEntry:
    def test_cache_entry_creation(self) -> None:
        dec = TaskDecomposer()
        dag = dec.decompose("optimize_system")
        entry = DecompositionCacheEntry(dag=dag)
        assert entry.dag == dag
        assert entry.hit_count == 1

    def test_cache_entry_record_hit(self) -> None:
        dec = TaskDecomposer()
        dag = dec.decompose("optimize_system")
        entry = DecompositionCacheEntry(dag=dag)
        entry.record_hit()
        assert entry.hit_count == 2


class TestHybridDecomposerBudget:
    def test_budget_blocked_triggers_template_fallback(self) -> None:
        config = ComplexityBudgetConfig(
            max_interaction_edges_per_module=2,
            warn_at_percent=0.5,
            block_at_percent=0.1,
        )
        budget = ArchitectureComplexityBudget(config=config)
        budget.register_edge("HybridDecomposer", "module_a")
        budget.register_edge("HybridDecomposer", "module_b")
        budget.register_edge("HybridDecomposer", "module_c")

        llm = MockLLMBackend([_make_valid_response()])
        dec = HybridDecomposer(llm_backend=llm, complexity_budget=budget)
        dag = dec.decompose("optimize_system")
        assert dag.node_count == 4
        assert llm.call_count == 0


class TestHybridDecomposerAudit:
    def test_audit_records_created_on_decompose(self) -> None:
        dec = HybridDecomposer()
        dec.decompose("optimize_system")
        assert dec._audit_store.count() > 0

    def test_audit_records_for_unknown_task(self) -> None:
        dec = HybridDecomposer()
        dec.decompose("unknown_task")
        records = dec._audit_store.all()
        assert len(records) >= 1
        event_types = [r.event_type for r in records]
        assert any("no_llm_or_unknown" in et for et in event_types)
