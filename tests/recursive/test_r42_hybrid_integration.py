from __future__ import annotations

from typing import Any

from maref.recursive.hybrid_decomposer import HybridDecomposer
from maref.recursive.self_orchestrator import (
    OrchestrationResult,
    SelfOrchestrator,
)
from maref.recursive.task_decomposer import TaskDecomposer


class MockLLMBackend:
    def __init__(self, responses: list[dict[str, Any]] | None = None) -> None:
        self._responses = responses or []
        self._call_count = 0

    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._call_count < len(self._responses):
            result = self._responses[self._call_count]
            self._call_count += 1
            return result
        return {"subtasks": []}

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


class TestSelfOrchestratorHybridIntegration:
    def test_default_orchestrator_uses_template_decomposer(self) -> None:
        orch = SelfOrchestrator()
        assert orch.is_hybrid is False
        assert isinstance(orch.decomposer, TaskDecomposer)

    def test_orchestrator_with_hybrid_decomposer_injected(self) -> None:
        llm = MockLLMBackend()
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        assert orch.is_hybrid is True
        assert isinstance(orch.decomposer, HybridDecomposer)
        assert orch.decomposer.llm_available is True

    def test_orchestrate_with_hybrid_decomposer(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("custom_analysis_task")
        assert isinstance(result, OrchestrationResult)
        assert result.dag.node_count == 3
        assert result.decomposition_source == "hybrid"
        assert len(result.dispatch_results) == 3
        assert len(result.agent_outputs) > 0

    def test_orchestrate_known_template_with_hybrid(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("optimize_system")
        assert result.dag.node_count == 3
        assert result.decomposition_source == "hybrid"

    def test_orchestrate_unknown_without_llm_falls_back(self) -> None:
        decomp = HybridDecomposer()
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("unknown_task")
        assert result.dag.node_count == 0
        assert result.decomposition_source == "hybrid"

    def test_resolve_conflict_works_with_hybrid(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        resolution = orch.resolve_conflict("governance_agent", "kg_agent", "execution order")
        assert "resolved" in resolution.lower()

    def test_reset_clears_hybrid_orchestrator(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        orch.reset()
        assert orch.registry.count() == 0
        assert orch.jsm.agent_count() == 0

    def test_orchestrate_diagnose_with_hybrid(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("diagnose_anomaly")
        assert result.dag.node_count == 3


class TestSelfOrchestratorBackwardCompatibility:
    def test_orchestrate_optimize_system(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        result = orch.orchestrate("optimize_system")
        assert result.dag.node_count == 4
        assert result.decomposition_source == "template"
        assert len(result.dispatch_results) == 4

    def test_orchestrate_diagnose_anomaly(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        result = orch.orchestrate("diagnose_anomaly")
        assert result.dag.node_count == 3
        assert result.decomposition_source == "template"

    def test_orchestrate_unknown_task(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        result = orch.orchestrate("unknown")
        assert result.dag.node_count == 0
        assert result.decomposition_source == "template"

    def test_resolve_conflict(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        resolution = orch.resolve_conflict("governance_agent", "kg_agent", "execution order")
        assert "resolved" in resolution.lower()

    def test_reset_clears_orchestrator(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        orch.reset()
        assert orch.registry.count() == 0
        assert orch.jsm.agent_count() == 0

    def test_initialize_registers_agents(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        assert orch.registry.count() == 4
        assert orch.jsm.agent_count() == 4


class TestOrchestrationResultFields:
    def test_template_result_has_source_field(self) -> None:
        orch = SelfOrchestrator()
        orch.initialize()
        result = orch.orchestrate("optimize_system")
        assert result.decomposition_source == "template"

    def test_hybrid_result_has_source_field(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("custom_task")
        assert result.decomposition_source == "hybrid"

    def test_no_deadlock_with_hybrid(self) -> None:
        llm = MockLLMBackend([_make_valid_response()])
        decomp = HybridDecomposer(llm_backend=llm)
        orch = SelfOrchestrator(hybrid_decomposer=decomp)
        orch.initialize()
        result = orch.orchestrate("custom_task")
        assert result.timed_out is False
