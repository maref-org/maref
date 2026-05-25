from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStage(Enum):
    IDENTIFY = "identify"
    PROPOSE = "propose"
    HUMAN_CONFIRM = "human_confirm"
    AGENT_EXECUTE = "agent_execute"
    AGENT_SELF_REVIEW = "agent_self_review"
    HUMAN_SPOT_CHECK = "human_spot_check"
    COMPLETE = "complete"
    REJECTED = "rejected"


class TaskAllocation(Enum):
    AGENT_ONLY = "agent_only"
    HUMAN_REQUIRED = "human_required"
    COLLABORATIVE = "collaborative"
    HUMAN_ONLY = "human_only"


class TaskDomain(Enum):
    CODE_GENERATION = "code_generation"
    ARCHITECTURE_DESIGN = "architecture_design"
    SECURITY_REVIEW = "security_review"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    GOVERNANCE = "governance"


DOMAIN_ALLOCATION: dict[TaskDomain, TaskAllocation] = {
    TaskDomain.CODE_GENERATION: TaskAllocation.AGENT_ONLY,
    TaskDomain.ARCHITECTURE_DESIGN: TaskAllocation.COLLABORATIVE,
    TaskDomain.SECURITY_REVIEW: TaskAllocation.HUMAN_REQUIRED,
    TaskDomain.DEPLOYMENT: TaskAllocation.COLLABORATIVE,
    TaskDomain.MONITORING: TaskAllocation.AGENT_ONLY,
    TaskDomain.GOVERNANCE: TaskAllocation.HUMAN_REQUIRED,
}

DOMAIN_CONFIDENCE_FOR_AUTO: dict[TaskDomain, float] = {
    TaskDomain.CODE_GENERATION: 0.5,
    TaskDomain.ARCHITECTURE_DESIGN: 0.8,
    TaskDomain.SECURITY_REVIEW: 0.9,
    TaskDomain.DEPLOYMENT: 0.7,
    TaskDomain.MONITORING: 0.4,
    TaskDomain.GOVERNANCE: 0.85,
}


@dataclass
class WorkflowTask:
    task_id: str
    title: str
    description: str
    domain: TaskDomain
    allocation: TaskAllocation
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "domain": self.domain.value,
            "allocation": self.allocation.value,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }


@dataclass
class WorkflowStep:
    step_id: str
    task_id: str
    stage: WorkflowStage
    assigned_to: str
    action: str
    result: str = ""
    timestamp: float = field(default_factory=time.time)
    duration_s: float = 0.0
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "task_id": self.task_id,
            "stage": self.stage.value,
            "assigned_to": self.assigned_to,
            "action": self.action,
            "result": self.result,
            "timestamp": self.timestamp,
            "duration_s": round(self.duration_s, 3),
            "status": self.status,
        }


@dataclass
class WorkflowInstance:
    task: WorkflowTask
    steps: list[WorkflowStep] = field(default_factory=list)
    current_stage: WorkflowStage = WorkflowStage.IDENTIFY
    status: str = "active"
    human_interactions: int = 0
    agent_interactions: int = 0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "current_stage": self.current_stage.value,
            "status": self.status,
            "step_count": len(self.steps),
            "human_interactions": self.human_interactions,
            "agent_interactions": self.agent_interactions,
            "steps": [s.to_dict() for s in self.steps],
        }


class CarbonSiliconSymbiosis:
    OLD_YANG_TRUST_THRESHOLD = 0.9
    HUMAN_SPOT_CHECK_RATE = 0.2

    def __init__(self, human_id: str = "human_operator"):
        self._human_id = human_id
        self._agent_trust: dict[str, float] = {}
        self._workflows: dict[str, WorkflowInstance] = {}
        self._completed_workflows: list[WorkflowInstance] = []

    def set_agent_trust(self, agent_id: str, trust: float) -> None:
        self._agent_trust[agent_id] = max(0.0, min(1.0, trust))

    def get_agent_trust(self, agent_id: str) -> float:
        return self._agent_trust.get(agent_id, 0.5)

    def is_old_yang_mode(self, agent_id: str) -> bool:
        return self.get_agent_trust(agent_id) >= self.OLD_YANG_TRUST_THRESHOLD

    def allocate_task(self, domain: TaskDomain, agent_id: str,
                      task_title: str, task_desc: str) -> WorkflowTask:
        base_allocation = DOMAIN_ALLOCATION[domain]

        if self.is_old_yang_mode(agent_id):
            if base_allocation == TaskAllocation.HUMAN_REQUIRED:
                base_allocation = TaskAllocation.COLLABORATIVE
            elif base_allocation == TaskAllocation.COLLABORATIVE:
                base_allocation = TaskAllocation.AGENT_ONLY

        task = WorkflowTask(
            task_id=str(uuid.uuid4())[:8],
            title=task_title,
            description=task_desc,
            domain=domain,
            allocation=base_allocation,
        )
        return task

    def start_workflow(self, agent_id: str, domain: TaskDomain,
                       title: str, description: str) -> WorkflowInstance:
        task = self.allocate_task(domain, agent_id, title, description)

        instance = WorkflowInstance(task=task)
        self._workflows[task.task_id] = instance

        identify_step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task.task_id,
            stage=WorkflowStage.IDENTIFY,
            assigned_to=agent_id,
            action=f"Agent {agent_id} identifies task: {title}",
            result="task_identified",
        )
        instance.steps.append(identify_step)
        instance.agent_interactions += 1

        propose_step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task.task_id,
            stage=WorkflowStage.PROPOSE,
            assigned_to=agent_id,
            action=f"Agent proposes execution plan for {title}",
            result="plan_proposed",
        )
        instance.steps.append(propose_step)
        instance.agent_interactions += 1
        instance.current_stage = WorkflowStage.PROPOSE

        return instance

    def human_confirm(self, task_id: str, confirmed: bool = True) -> WorkflowInstance | None:
        instance = self._workflows.get(task_id)
        if not instance:
            return None

        if instance.task.allocation == TaskAllocation.AGENT_ONLY:
            return instance

        step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            stage=WorkflowStage.HUMAN_CONFIRM,
            assigned_to=self._human_id,
            action=f"Human confirms: {confirmed}",
            result="approved" if confirmed else "rejected",
        )
        instance.steps.append(step)
        instance.human_interactions += 1

        if not confirmed:
            instance.status = "rejected"
            instance.current_stage = WorkflowStage.REJECTED
            return instance

        instance.current_stage = WorkflowStage.HUMAN_CONFIRM
        return instance

    def agent_execute(self, task_id: str, agent_id: str) -> WorkflowInstance | None:
        instance = self._workflows.get(task_id)
        if not instance:
            return None

        if instance.status == "rejected":
            return instance

        step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            stage=WorkflowStage.AGENT_EXECUTE,
            assigned_to=agent_id,
            action=f"Agent {agent_id} executes task",
            result="execution_complete",
            duration_s=0.5,
        )
        step.status = "completed"
        instance.steps.append(step)
        instance.agent_interactions += 1
        instance.current_stage = WorkflowStage.AGENT_EXECUTE

        return instance

    def agent_self_review(self, task_id: str, agent_id: str,
                          passed: bool = True) -> WorkflowInstance | None:
        instance = self._workflows.get(task_id)
        if not instance:
            return None

        step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            stage=WorkflowStage.AGENT_SELF_REVIEW,
            assigned_to=agent_id,
            action=f"Agent self-review: {'passed' if passed else 'failed'}",
            result="review_passed" if passed else "review_failed",
        )
        instance.steps.append(step)
        instance.agent_interactions += 1
        instance.current_stage = WorkflowStage.AGENT_SELF_REVIEW

        return instance

    def human_spot_check(self, task_id: str, passed: bool = True) -> WorkflowInstance | None:
        instance = self._workflows.get(task_id)
        if not instance:
            return None

        allocation = instance.task.allocation
        self.get_agent_trust(self._agent_trust.keys().__iter__().__next__() if self._agent_trust else "default")
        needs_check = allocation in (TaskAllocation.HUMAN_REQUIRED, TaskAllocation.COLLABORATIVE)

        if allocation == TaskAllocation.AGENT_ONLY:
            import random
            if random.random() > self.HUMAN_SPOT_CHECK_RATE:
                needs_check = False

        if not needs_check:
            instance.current_stage = WorkflowStage.COMPLETE
            instance.status = "completed"
            instance.completed_at = time.time()
            self._completed_workflows.append(instance)
            return instance

        step = WorkflowStep(
            step_id=str(uuid.uuid4())[:8],
            task_id=task_id,
            stage=WorkflowStage.HUMAN_SPOT_CHECK,
            assigned_to=self._human_id,
            action=f"Human spot check: {'passed' if passed else 'failed'}",
            result="check_passed" if passed else "check_failed",
        )
        instance.steps.append(step)
        instance.human_interactions += 1

        if passed:
            instance.current_stage = WorkflowStage.COMPLETE
            instance.status = "completed"
            instance.completed_at = time.time()
            self._completed_workflows.append(instance)
        else:
            instance.status = "rejected"

        return instance

    def run_full_cycle(self, agent_id: str, domain: TaskDomain,
                       title: str, description: str,
                       human_confirms: bool = True,
                       self_review_passes: bool = True,
                       spot_check_passes: bool = True) -> WorkflowInstance:

        instance = self.start_workflow(agent_id, domain, title, description)

        if instance.task.allocation != TaskAllocation.AGENT_ONLY:
            instance = self.human_confirm(instance.task.task_id, human_confirms) or instance
            if instance.status == "rejected":
                return instance

        instance = self.agent_execute(instance.task.task_id, agent_id) or instance

        instance = self.agent_self_review(instance.task.task_id, agent_id, self_review_passes) or instance

        instance = self.human_spot_check(instance.task.task_id, spot_check_passes) or instance

        return instance

    def _get_last_task_id(self) -> str:
        return list(self._workflows.keys())[-1] if self._workflows else ""

    def get_workflow(self, task_id: str) -> WorkflowInstance | None:
        return self._workflows.get(task_id)

    def get_all_workflows(self) -> list[WorkflowInstance]:
        return list(self._workflows.values())

    def get_completed_workflows(self) -> list[WorkflowInstance]:
        return self._completed_workflows.copy()

    def get_stats(self) -> dict[str, Any]:
        completed = len(self._completed_workflows)
        active = len(self._workflows)
        total_human = sum(w.human_interactions for w in self._workflows.values())
        total_agent = sum(w.agent_interactions for w in self._workflows.values())
        return {
            "active_workflows": active,
            "completed_workflows": completed,
            "total_human_interactions": total_human,
            "total_agent_interactions": total_agent,
            "symbiosis_ratio": round(
                total_agent / max(1, total_human + total_agent), 3
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "human_id": self._human_id,
            "agent_trust": {k: round(v, 3) for k, v in self._agent_trust.items()},
            "stats": self.get_stats(),
            "workflows": [w.to_dict() for w in self._workflows.values()],
        }
