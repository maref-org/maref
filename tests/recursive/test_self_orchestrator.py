from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from maref.recursive.self_orchestrator import (
    OrchestrationResult,
    SelfOrchestrator,
)
from maref.recursive.task_decomposer import TaskDAG, SubTask


class TestOrchestrationResult:
    def test_default_construction(self) -> None:
        dag = TaskDAG(root_task="test")
        r = OrchestrationResult(task_description="test", dag=dag)
        assert r.task_description == "test"
        assert r.dag is dag
        assert r.dispatch_results == []
        assert r.agent_outputs == {}
        assert r.sync_log == []
        assert r.conflicts == []
        assert r.timed_out is False
        assert r.decomposition_source == "template"
        assert r.saga_result is None


class TestSelfOrchestrator:
    def test_default_construction(self) -> None:
        o = SelfOrchestrator()
        assert o.registry is not None
        assert o.jsm is not None
        assert o.decomposer is not None
        assert o.is_hybrid is False

    def test_hybrid_construction(self) -> None:
        hybrid = MagicMock()
        o = SelfOrchestrator(use_hybrid=True, hybrid_decomposer=hybrid)
        assert o.is_hybrid is True
        assert o.decomposer is hybrid

    def test_initialize(self) -> None:
        o = SelfOrchestrator()
        with (
            patch.object(o._registry, "load_defaults") as mock_load,
            patch.object(o._registry, "list_all", return_value=[]) as mock_list,
        ):
            o.initialize()
            mock_load.assert_called_once()
            mock_list.assert_called_once()

    def test_initialize_registers_agents(self) -> None:
        o = SelfOrchestrator()
        agent_a = MagicMock()
        agent_a.agent_id = "agent_a"
        agent_b = MagicMock()
        agent_b.agent_id = "agent_b"

        with (
            patch.object(o._registry, "load_defaults"),
            patch.object(o._registry, "list_all", return_value=[agent_a, agent_b]),
            patch.object(o._jsm, "register_agent") as mock_register,
        ):
            o.initialize()
            assert mock_register.call_count == 2
            mock_register.assert_any_call("agent_a")
            mock_register.assert_any_call("agent_b")

    def test_orchestrate_basic(self) -> None:
        o = SelfOrchestrator()

        task_node = SubTask(task_id="t1", description="subtask")
        dag = TaskDAG(root_task="main task")
        dag.nodes = {"t1": task_node}

        dispatch_result = MagicMock()
        dispatch_result.assigned_agent_id = "agent_1"
        dispatch_result.subtask_id = "t1"
        dispatch_result.score = 0.95

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(
                o._dispatcher, "dispatch_all", return_value=[dispatch_result]
            ),
            patch.object(o._jsm, "agent_count", return_value=2),
            patch.object(o._jsm, "advance_all_to"),
            patch.object(o._jsm, "all_at_barrier", return_value=True),
            patch.object(o._jsm, "conflict_log", []),
        ):
            result = o.orchestrate("main task")
            assert result.task_description == "main task"
            assert result.dag is dag
            assert len(result.dispatch_results) == 1
            assert "agent_1" in result.agent_outputs
            assert result.decomposition_source == "template"
            assert result.timed_out is False

    def test_orchestrate_single_agent_no_sync(self) -> None:
        o = SelfOrchestrator()

        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate("task")
            assert result.sync_log == []

    def test_orchestrate_with_hybrid_decomposer(self) -> None:
        # Create a mock that will pass isinstance check
        from maref.recursive.hybrid_decomposer import HybridDecomposer
        hybrid = MagicMock(spec=HybridDecomposer)
        o = SelfOrchestrator(hybrid_decomposer=hybrid)

        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(hybrid, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate("task")
            assert result.decomposition_source == "hybrid"

    def test_orchestrate_without_saga(self) -> None:
        o = SelfOrchestrator()
        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate_with_saga("task")
            assert result.task_description == "task"

    def test_orchestrate_with_saga_success(self) -> None:
        saga_orch = MagicMock()
        saga_result = MagicMock()
        saga_result.is_success = True
        saga_orch.execute.return_value = saga_result

        o = SelfOrchestrator(saga_orchestrator=saga_orch)

        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate_with_saga("task")
            assert result.saga_result is saga_result
            assert result.timed_out is False

    def test_orchestrate_with_saga_timeout(self) -> None:
        saga_orch = MagicMock()
        saga_result = MagicMock()
        saga_result.is_success = False
        saga_orch.execute.return_value = saga_result

        o = SelfOrchestrator(saga_orchestrator=saga_orch)

        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate_with_saga("task")
            assert result.timed_out is True

    def test_orchestrate_with_saga_no_saga_orch(self) -> None:
        o = SelfOrchestrator()
        dag = TaskDAG(root_task="task")
        dag.nodes = {}

        with (
            patch.object(o._decomposer, "decompose", return_value=dag),
            patch.object(o._dispatcher, "dispatch_all", return_value=[]),
            patch.object(o._jsm, "agent_count", return_value=1),
        ):
            result = o.orchestrate_with_saga("task", deadline=60.0)
            assert result.task_description == "task"
            assert result.saga_result is None

    def test_resolve_conflict(self) -> None:
        o = SelfOrchestrator()
        with patch.object(o._jsm, "arbitrate", return_value="agent_a wins"):
            result = o.resolve_conflict("agent_a", "agent_b", "resource conflict")
            assert result == "agent_a wins"

    def test_reset(self) -> None:
        o = SelfOrchestrator()
        with (
            patch.object(o._registry, "clear") as mock_clear,
            patch.object(o._jsm, "reset") as mock_reset,
        ):
            o.reset()
            mock_clear.assert_called_once()
            mock_reset.assert_called_once()