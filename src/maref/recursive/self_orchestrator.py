from __future__ import annotations

from dataclasses import dataclass, field

from maref.recursive.agent_dispatcher import AgentDispatcher, DispatchResult
from maref.recursive.hybrid_decomposer import HybridDecomposer
from maref.recursive.internal_agents import InternalAgentRegistry
from maref.recursive.joint_state_machine import JointStateMachine
from maref.recursive.task_decomposer import TaskDAG, TaskDecomposer


@dataclass
class OrchestrationResult:
    task_description: str
    dag: TaskDAG
    dispatch_results: list[DispatchResult] = field(default_factory=list)
    agent_outputs: dict[str, str] = field(default_factory=dict)
    sync_log: list[str] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)
    timed_out: bool = False
    decomposition_source: str = "template"
    saga_result: object | None = None


class SelfOrchestrator:
    def __init__(
        self,
        use_hybrid: bool = False,
        hybrid_decomposer: HybridDecomposer | None = None,
        saga_orchestrator: object | None = None,
    ) -> None:
        self._registry = InternalAgentRegistry()
        if hybrid_decomposer is not None:
            self._decomposer: TaskDecomposer | HybridDecomposer = hybrid_decomposer
            self._use_hybrid = True
        else:
            self._decomposer = TaskDecomposer()
            self._use_hybrid = use_hybrid
        self._dispatcher = AgentDispatcher(self._registry)
        self._jsm = JointStateMachine()
        self._saga_orchestrator = saga_orchestrator

    @property
    def registry(self) -> InternalAgentRegistry:
        return self._registry

    @property
    def jsm(self) -> JointStateMachine:
        return self._jsm

    @property
    def decomposer(self) -> TaskDecomposer | HybridDecomposer:
        return self._decomposer

    @property
    def is_hybrid(self) -> bool:
        return self._use_hybrid

    def initialize(self) -> None:
        self._registry.load_defaults()
        for agent in self._registry.list_all():
            self._jsm.register_agent(agent.agent_id)

    def orchestrate(self, task_description: str) -> OrchestrationResult:
        dag = self._decomposer.decompose(task_description)
        decomposition_source = (
            "hybrid" if isinstance(self._decomposer, HybridDecomposer) else "template"
        )
        subtasks = list(dag.nodes.values())

        dispatch_results = self._dispatcher.dispatch_all(subtasks)

        agent_outputs: dict[str, str] = {}
        for dr in dispatch_results:
            if dr.assigned_agent_id:
                agent_outputs[dr.assigned_agent_id] = (
                    f"executed {dr.subtask_id} with score {dr.score:.2f}"
                )

        sync_log: list[str] = []
        if self._jsm.agent_count() > 1:
            self._jsm.advance_all_to("RUNNING")
            sync_log.append("all agents advanced to RUNNING")
            if self._jsm.all_at_barrier("RUNNING"):
                sync_log.append("barrier RUNNING achieved")
            self._jsm.advance_all_to("DONE")
            sync_log.append("all agents advanced to DONE")

        conflicts = list(self._jsm.conflict_log)

        return OrchestrationResult(
            task_description=task_description,
            dag=dag,
            dispatch_results=dispatch_results,
            agent_outputs=agent_outputs,
            sync_log=sync_log,
            conflicts=conflicts,
            timed_out=False,
            decomposition_source=decomposition_source,
        )

    def orchestrate_with_saga(
        self, task_description: str, deadline: float | None = None
    ) -> OrchestrationResult:
        if self._saga_orchestrator is None:
            return self.orchestrate(task_description)

        from maref.recursive.saga_orchestrator import (
            Saga,
            StepResult,
        )

        result = OrchestrationResult(
            task_description=task_description,
            dag=TaskDAG(root_task=task_description),
        )

        def decompose_step(ctx: dict) -> StepResult:
            dag = self._decomposer.decompose(task_description)
            result.dag = dag
            result.decomposition_source = "saga_wrapped"
            return StepResult(
                step_id="decompose",
                success=True,
                data={"subtask_count": len(dag.nodes)},
            )

        def dispatch_step(ctx: dict) -> StepResult:
            subtasks = list(result.dag.nodes.values())
            drs = self._dispatcher.dispatch_all(subtasks)
            result.dispatch_results = drs
            return StepResult(
                step_id="dispatch",
                success=len(drs) > 0,
                data={"dispatched": len(drs)},
            )

        def execute_step(ctx: dict) -> StepResult:
            sync_log: list[str] = []
            agent_outputs: dict[str, str] = {}
            for dr in result.dispatch_results:
                if dr.assigned_agent_id:
                    agent_outputs[dr.assigned_agent_id] = (
                        f"executed {dr.subtask_id} with score {dr.score:.2f}"
                    )
            result.agent_outputs = agent_outputs
            if self._jsm.agent_count() > 1:
                self._jsm.advance_all_to("RUNNING")
                sync_log.append("all agents advanced to RUNNING")
                if self._jsm.all_at_barrier("RUNNING"):
                    sync_log.append("barrier RUNNING achieved")
                self._jsm.advance_all_to("DONE")
                sync_log.append("all agents advanced to DONE")
            result.sync_log = sync_log
            result.conflicts = list(self._jsm.conflict_log)
            return StepResult(
                step_id="execute",
                success=True,
                data={"agents": len(agent_outputs)},
            )

        def rollback_dispatch(ctx: dict) -> StepResult:
            result.dispatch_results = []
            result.agent_outputs = {}
            return StepResult(
                step_id="rollback_dispatch",
                success=True,
                data={"rolled_back": True},
            )

        saga = Saga(description=f"Orchestrate: {task_description[:50]}")
        saga.add_step(decompose_step, description="Decompose task")
        saga.add_step(dispatch_step, rollback_dispatch, description="Dispatch subtasks")
        saga.add_step(execute_step, description="Execute subtasks")

        saga_result = self._saga_orchestrator.execute(saga)  # type: ignore[attr-defined]
        result.saga_result = saga_result
        is_success = getattr(saga_result, "is_success", True)
        if not is_success:
            result.timed_out = True
        return result

    def resolve_conflict(self, agent_a: str, agent_b: str, issue: str) -> str | dict:
        return self._jsm.arbitrate(agent_a, agent_b, issue)

    def reset(self) -> None:
        self._registry.clear()
        self._jsm.reset()
