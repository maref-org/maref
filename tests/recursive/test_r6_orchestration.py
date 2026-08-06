from __future__ import annotations

import pytest

from maref.recursive.agent_dispatcher import AgentDispatcher
from maref.recursive.internal_agents import (
    InternalAgentRegistry,
)
from maref.recursive.joint_state_machine import JointStateMachine
from maref.recursive.self_orchestrator import (
    OrchestrationResult,
    SelfOrchestrator,
)
from maref.recursive.task_decomposer import (
    SubTask,
    TaskDecomposer,
)


class TestInternalAgentRegistry:
    def test_load_defaults_registers_four_agents(self) -> None:
        registry = InternalAgentRegistry()
        agents = registry.load_defaults()
        assert len(agents) == 4
        assert registry.count() == 4

    def test_get_returns_agent(self) -> None:
        registry = InternalAgentRegistry()
        registry.load_defaults()
        agent = registry.get("governance_agent")
        assert agent is not None
        assert agent.agent_id == "governance_agent"
        assert "state_transition" in agent.capabilities

    def test_list_all_returns_all(self) -> None:
        registry = InternalAgentRegistry()
        registry.load_defaults()
        all_agents = registry.list_all()
        assert len(all_agents) == 4

    def test_set_status(self) -> None:
        registry = InternalAgentRegistry()
        registry.load_defaults()
        assert registry.set_status("governance_agent", "RUNNING") is True
        agent = registry.get("governance_agent")
        assert agent is not None
        assert agent.status == "RUNNING"

    def test_set_status_unknown_agent(self) -> None:
        registry = InternalAgentRegistry()
        assert registry.set_status("nonexistent", "RUNNING") is False

    def test_clear_removes_all(self) -> None:
        registry = InternalAgentRegistry()
        registry.load_defaults()
        registry.clear()
        assert registry.count() == 0

    def test_find_by_capability(self) -> None:
        registry = InternalAgentRegistry()
        registry.load_defaults()
        agents = registry.find_by_capability("observe")
        assert len(agents) == 1
        assert agents[0].agent_id == "sidecar_agent"

    def test_register_custom_agent(self) -> None:
        registry = InternalAgentRegistry()
        agent = registry.register("custom", "custom.module", ["custom_cap"], "custom")
        assert agent.agent_id == "custom"
        assert registry.count() == 1


class TestTaskDecomposer:
    def test_decompose_optimize_system(self) -> None:
        decomposer = TaskDecomposer()
        dag = decomposer.decompose("optimize_system")
        assert dag.node_count == 4
        assert "observe_perf" in dag.nodes
        assert "verify_trust" in dag.nodes
        assert ("observe_perf", "analyze_bottlenecks") in dag.edges
        assert ("propose_fixes", "verify_trust") in dag.edges

    def test_decompose_unknown_task_returns_empty(self) -> None:
        decomposer = TaskDecomposer()
        dag = decomposer.decompose("unknown_task")
        assert dag.node_count == 0
        assert dag.root_task == "unknown_task"

    def test_dag_root_task_preserved(self) -> None:
        decomposer = TaskDecomposer()
        dag = decomposer.decompose("optimize_system")
        assert dag.root_task == "optimize_system"

    def test_decompose_diagnose_anomaly(self) -> None:
        decomposer = TaskDecomposer()
        dag = decomposer.decompose("diagnose_anomaly")
        assert dag.node_count == 3
        assert "run_probes" in dag.nodes
        assert "evaluate_risk" in dag.nodes
        assert "decide_action" in dag.nodes


class TestAgentDispatcher:
    @pytest.fixture
    def registry(self) -> InternalAgentRegistry:
        r = InternalAgentRegistry()
        r.load_defaults()
        return r

    def test_dispatch_matches_best_agent(self, registry: InternalAgentRegistry) -> None:
        dispatcher = AgentDispatcher(registry)
        subtask = SubTask(
            task_id="t1",
            description="observe system",
            required_capabilities=["observe", "collect"],
        )
        agent = dispatcher.dispatch(subtask)
        assert agent is not None
        assert agent.agent_id == "sidecar_agent"

    def test_dispatch_governance_subtask(self, registry: InternalAgentRegistry) -> None:
        dispatcher = AgentDispatcher(registry)
        subtask = SubTask(
            task_id="t2",
            description="break circuit",
            required_capabilities=["state_transition", "circuit_break", "halt"],
        )
        agent = dispatcher.dispatch(subtask)
        assert agent is not None
        assert agent.agent_id == "governance_agent"

    def test_dispatch_all_covers_all_subtasks(self, registry: InternalAgentRegistry) -> None:
        dispatcher = AgentDispatcher(registry)
        subtasks = [
            SubTask("a", "obs", required_capabilities=["observe"]),
            SubTask("b", "gov", required_capabilities=["halt"]),
            SubTask("c", "kg", required_capabilities=["graph_query"]),
        ]
        results = dispatcher.dispatch_all(subtasks)
        assert len(results) == 3
        for r in results:
            assert r.assigned_agent_id != ""

    def test_dispatch_empty_capabilities(self, registry: InternalAgentRegistry) -> None:
        dispatcher = AgentDispatcher(registry)
        subtask = SubTask(task_id="t", description="generic")
        agent = dispatcher.dispatch(subtask)
        assert agent is not None

    def test_dispatch_all_with_partial_match(self, registry: InternalAgentRegistry) -> None:
        dispatcher = AgentDispatcher(registry)
        subtask = SubTask(
            "partial",
            "desc",
            required_capabilities=["observe", "no_such_capability"],
        )
        agent = dispatcher.dispatch(subtask)
        assert agent is not None
        assert agent.agent_id == "sidecar_agent"


class TestJointStateMachine:
    def test_register_agents(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        assert jsm.agent_count() == 2

    def test_advance_and_barrier(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance("a", "RUNNING")
        assert jsm.all_at_barrier("RUNNING") is False
        jsm.advance("b", "RUNNING")
        assert jsm.all_at_barrier("RUNNING") is True

    def test_any_at_state(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance("a", "ERROR")
        assert jsm.any_at_state("ERROR") is True
        assert jsm.any_at_state("RUNNING") is False

    def test_advance_all_to(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.register_agent("b")
        jsm.advance_all_to("DONE")
        assert jsm.all_at_barrier("DONE") is True

    def test_arbitrate_logs_conflict(self) -> None:
        jsm = JointStateMachine()
        resolution = jsm.arbitrate("agent_x", "agent_y", "resource contention")
        assert "resolved" in resolution.lower()
        assert len(jsm.conflict_log) == 1
        assert jsm.conflict_log[0]["issue"] == "resource contention"

    def test_reset_clears_state(self) -> None:
        jsm = JointStateMachine()
        jsm.register_agent("a")
        jsm.arbitrate("a", "b", "issue")
        jsm.reset()
        assert jsm.agent_count() == 0
        assert len(jsm.conflict_log) == 0

    def test_all_at_barrier_empty(self) -> None:
        jsm = JointStateMachine()
        assert jsm.all_at_barrier("RUNNING") is False


class TestSelfOrchestrator:
    def test_initialize_registers_agents(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        assert orchestrator.registry.count() == 4
        assert orchestrator.jsm.agent_count() == 4

    def test_orchestrate_optimize_system(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        result = orchestrator.orchestrate("optimize_system")
        assert isinstance(result, OrchestrationResult)
        assert result.dag.node_count == 4
        assert len(result.dispatch_results) == 4
        assert len(result.agent_outputs) > 0
        assert len(result.sync_log) > 0

    def test_orchestrate_diagnose_anomaly(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        result = orchestrator.orchestrate("diagnose_anomaly")
        assert result.dag.node_count == 3
        assert len(result.dispatch_results) == 3

    def test_orchestrate_unknown_task(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        result = orchestrator.orchestrate("unknown")
        assert result.dag.node_count == 0

    def test_resolve_conflict(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        resolution = orchestrator.resolve_conflict(
            "governance_agent", "kg_agent", "execution order"
        )
        assert "resolved" in resolution.lower()
        assert len(orchestrator.jsm.conflict_log) == 1

    def test_reset_clears_orchestrator(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        orchestrator.reset()
        assert orchestrator.registry.count() == 0
        assert orchestrator.jsm.agent_count() == 0

    def test_no_deadlock_on_orchestrate(self) -> None:
        orchestrator = SelfOrchestrator()
        orchestrator.initialize()
        result = orchestrator.orchestrate("optimize_system")
        assert result.timed_out is False
