from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maref.recursive.formal_planner import ForwardChainingPlanner, PlanningDomain


@dataclass
class SubTask:
    task_id: str
    description: str
    required_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    assigned_to: str = ""


@dataclass
class TaskDAG:
    root_task: str
    nodes: dict[str, SubTask] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)

    @property
    def node_count(self) -> int:
        return len(self.nodes)


_TASK_TEMPLATES: dict[str, list[dict[str, object]]] = {
    "optimize_system": [
        {"id": "observe_perf", "desc": "观测当前系统性能指标",
         "capabilities": ["observe", "collect", "monitor"], "deps": []},
        {"id": "analyze_bottlenecks", "desc": "分析性能瓶颈点",
         "capabilities": ["graph_query", "hypothesis_test"], "deps": ["observe_perf"]},
        {"id": "propose_fixes", "desc": "提出修复/优化方案",
         "capabilities": ["state_transition", "circuit_break"], "deps": ["analyze_bottlenecks"]},
        {"id": "verify_trust", "desc": "验证优化方案可信度",
         "capabilities": ["did_resolve", "vc_verify", "trust_evaluate"], "deps": ["propose_fixes"]},
    ],
    "diagnose_anomaly": [
        {"id": "run_probes", "desc": "运行全量诊断探针",
         "capabilities": ["observe", "collect"], "deps": []},
        {"id": "evaluate_risk", "desc": "评估风险等级",
         "capabilities": ["graph_query", "hypothesis_test"], "deps": ["run_probes"]},
        {"id": "decide_action", "desc": "决策治理动作",
         "capabilities": ["state_transition", "circuit_break", "halt"], "deps": ["evaluate_risk"]},
    ],
    "resolve_identity_conflict": [
        {"id": "audit_dids", "desc": "审计 DID 注册信息",
         "capabilities": ["did_resolve", "vc_verify"], "deps": []},
        {"id": "cross_check_trust", "desc": "交叉校验 Trust Score",
         "capabilities": ["trust_evaluate"], "deps": ["audit_dids"]},
    ],
}

_TASK_GOALS: dict[str, str] = {
    "optimize_system": "trust_verified",
    "diagnose_anomaly": "action_decided",
    "resolve_identity_conflict": "trust_cross_checked",
}


class TaskDecomposer:
    def __init__(self, use_formal_planner: bool = False,
                 planner: ForwardChainingPlanner | None = None,
                 domain: PlanningDomain | None = None) -> None:
        self._use_formal_planner = use_formal_planner
        self._planner = planner
        self._domain = domain

    def decompose(self, task_description: str) -> TaskDAG:
        if self._use_formal_planner and self._planner is not None and self._domain is not None:
            formal_result = self._decompose_formal(task_description)
            if formal_result is not None:
                return formal_result

        template = _TASK_TEMPLATES.get(task_description)
        if template is None:
            return TaskDAG(root_task=task_description)

        return self._decompose_template(task_description, template)

    def _decompose_template(self, root_task: str,
                            template: list[dict[str, object]]) -> TaskDAG:
        nodes: dict[str, SubTask] = {}
        edges: list[tuple[str, str]] = []
        for tpl in template:
            task_id = str(tpl["id"])
            sub = SubTask(
                task_id=task_id,
                description=str(tpl["desc"]),
                required_capabilities=list(tpl["capabilities"]),  # type: ignore[call-overload]
                dependencies=list(tpl.get("deps", [])),  # type: ignore[call-overload]
            )
            nodes[task_id] = sub
            for dep in sub.dependencies:
                edges.append((dep, task_id))
        return TaskDAG(root_task=root_task, nodes=nodes, edges=edges)

    def _decompose_formal(self, task_description: str) -> TaskDAG | None:
        from maref.recursive.formal_planner import plan_to_taskdag

        if self._planner is None or self._domain is None:
            return None

        goal_pred_name = _TASK_GOALS.get(task_description)
        if goal_pred_name is None:
            return None

        goal_pred = None
        for p in self._domain.predicates:
            if p.name == goal_pred_name:
                goal_pred = p
                break
        if goal_pred is None:
            return None

        self._domain.goal_state = frozenset([goal_pred])

        plan = self._planner.plan(self._domain)
        if plan is None:
            return None

        dag, _ = plan_to_taskdag(plan, self._domain)
        return dag
