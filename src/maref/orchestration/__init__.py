"""MAREF Orchestration Layer.

Local imports of the federated plan executor are deferred via
``__getattr__`` to break the circular dependency:

    maref.orchestration.federated_plan_executor
        -> maref.federation.gateway
        -> maref.orchestration.dispatcher
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maref.orchestration.decomposer import ParallelStrategy, SubTask, TaskDAG, TaskDecomposer
from maref.orchestration.dispatcher import AgentDispatcher, DispatchResult
from maref.orchestration.joint_machine import JointState, JointStateMachine
from maref.orchestration.plan_executor import (
    Plan,
    PlanExecutionReport,
    PlanExecutor,
    PlanStatus,
    PlanStep,
    StepExecutionRecord,
    StepResult,
)
from maref.orchestration.protocols import (
    AgentTaskResult,
    RiskPoint,
    SelfCheckResult,
    TaskResultStatus,
)
from maref.orchestration.state_merge_controller import Conflict, MergeResult, StateMergeController
from maref.orchestration.task_graph import (
    NodeType,
    RiskLevel,
    TaskGraph,
    TaskNode,
    TaskStatus,
)

# Lazy module references for the federated plan executor.
# Imported on first attribute access to avoid the circular dependency
# with maref.federation.gateway at package import time.
if TYPE_CHECKING:
    from maref.orchestration.federated_plan_executor import (
        FEDERATION_DISPATCH_ACTION,
        FederatedPlanExecutionReport,
        FederatedPlanExecutor,
        FederationDispatchRecord,
    )

__all__ = [
    "SubTask",
    "TaskDAG",
    "TaskDecomposer",
    "AgentDispatcher",
    "DispatchResult",
    # Federated plan executor (lazy-loaded via __getattr__)
    "FEDERATION_DISPATCH_ACTION",
    "FederationDispatchRecord",
    "FederatedPlanExecutionReport",
    "FederatedPlanExecutor",
    "JointState",
    "JointStateMachine",
    "NodeType",
    "RiskLevel",
    "TaskGraph",
    "TaskNode",
    "TaskStatus",
    "Plan",
    "PlanExecutor",
    "PlanStep",
    "PlanStatus",
    "PlanExecutionReport",
    "StepExecutionRecord",
    "StepResult",
    "AgentTaskResult",
    "RiskPoint",
    "SelfCheckResult",
    "TaskResultStatus",
    "StateMergeController",
    "MergeResult",
    "Conflict",
    "ParallelStrategy",
]

_FEDERATED_EXPORTS = {
    "FEDERATION_DISPATCH_ACTION",
    "FederationDispatchRecord",
    "FederatedPlanExecutionReport",
    "FederatedPlanExecutor",
}


def __getattr__(name: str) -> Any:
    """Lazily import the federated plan executor symbols on first use.

    This breaks the circular import:

        maref.orchestration.federated_plan_executor
            -> maref.federation.gateway
            -> maref.orchestration.decomposer / dispatcher
                -> maref.orchestration.__init__
    """
    if name in _FEDERATED_EXPORTS:
        from maref.orchestration import federated_plan_executor as _fp

        value = getattr(_fp, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'maref.orchestration' has no attribute {name!r}")
