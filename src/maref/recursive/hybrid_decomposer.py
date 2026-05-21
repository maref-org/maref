from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from maref.recursive.complexity_budget import ArchitectureComplexityBudget
from maref.recursive.safety_gate_v2 import SafetyGateV2
from maref.recursive.task_decomposer import SubTask, TaskDAG, TaskDecomposer
from maref.recursive.unified_audit import UnifiedAuditRecord, UnifiedAuditStore, make_record_id


class LLMBackend(Protocol):
    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


@dataclass
class DecompositionCacheEntry:
    dag: TaskDAG
    cached_at: float = field(default_factory=time.time)
    hit_count: int = 1

    def record_hit(self) -> None:
        self.hit_count += 1
        self.cached_at = time.time()


_DECOMPOSITION_PROMPT_TEMPLATE = """You are a task decomposition engine. Given a high-level task description,
break it down into a Directed Acyclic Graph (DAG) of subtasks.

Each subtask must have:
- id: unique string identifier
- description: what the subtask does
- capabilities: list of required agent capabilities (choose from: observe, collect, monitor,
    graph_query, hypothesis_test, state_transition, circuit_break, halt,
    did_resolve, vc_verify, trust_evaluate, relation_infer)
- dependencies: list of subtask ids that must complete before this one (can be empty)

Output a JSON object with the following structure:
{{
    "subtasks": [
        {{
            "id": "string",
            "description": "string",
            "capabilities": ["string"],
            "dependencies": ["string"]
        }}
    ]
}}

Task: {task_description}

Context: {context}"""

_DECOMPOSITION_SCHEMA = {
    "type": "object",
    "properties": {
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["id", "description", "capabilities", "dependencies"],
            },
        }
    },
    "required": ["subtasks"],
}


class HybridDecomposer:
    MAX_SUBTASKS = 12
    MAX_CACHE_SIZE = 256
    MAX_LLM_TIMEOUT = 5.0

    def __init__(
        self,
        llm_backend: LLMBackend | None = None,
        safety_gate: SafetyGateV2 | None = None,
        complexity_budget: ArchitectureComplexityBudget | None = None,
        audit_store: UnifiedAuditStore | None = None,
    ) -> None:
        self._llm = llm_backend
        self._safety_gate = safety_gate or SafetyGateV2()
        self._budget = complexity_budget
        self._fallback = TaskDecomposer()
        self._audit_store = audit_store or UnifiedAuditStore()
        self._cache: dict[str, DecompositionCacheEntry] = {}

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    @property
    def llm_available(self) -> bool:
        return self._llm is not None

    def decompose(self, task_description: str, context: dict[str, Any] | None = None) -> TaskDAG:
        cached = self._cache.get(task_description)
        if cached is not None:
            cached.record_hit()
            self._audit_decomposition(task_description, "cache_hit", True)
            return cached.dag

        if self._llm is not None:
            if self._budget is not None:
                assessment = self._budget.get_module_assessment("HybridDecomposer")
                if assessment.status == "BLOCKED":
                    return self._fallback_decompose(task_description, "budget_blocked")

            dag = self._llm_decompose(task_description, context)
            if dag is not None:
                if dag.node_count > self.MAX_SUBTASKS:
                    self._audit_decomposition(task_description, "subtask_explosion", False)
                    return self._fallback_decompose(task_description, "subtask_explosion")
                if not self._validate_dag(dag):
                    self._audit_decomposition(task_description, "invalid_dag", False)
                    return self._fallback_decompose(task_description, "invalid_dag")
                if not self._safety_gate_validate(dag):
                    self._audit_decomposition(task_description, "safety_gate_rejected", False)
                    return self._fallback_decompose(task_description, "safety_gate_rejected")
                self._update_cache(task_description, dag)
                self._audit_decomposition(task_description, "llm_success", True)
                return dag
            self._audit_decomposition(task_description, "llm_failed", False)
        else:
            template_result = self._fallback.decompose(task_description)
            if template_result.node_count > 0:
                self._audit_decomposition(task_description, "template_match", True)
                self._update_cache(task_description, template_result)
                return template_result
        return self._fallback_decompose(task_description, "no_llm_or_unknown")

    def _fallback_decompose(self, task_description: str, reason: str) -> TaskDAG:
        result = self._fallback.decompose(task_description)
        if result.node_count > 0:
            self._update_cache(task_description, result)
        self._audit_decomposition(task_description, reason, result.node_count > 0)
        return result

    def _llm_decompose(self, task_description: str, context: dict[str, Any] | None) -> TaskDAG | None:
        if self._llm is None:
            return None
        context_str = json.dumps(context or {}, ensure_ascii=False)
        prompt = _DECOMPOSITION_PROMPT_TEMPLATE.format(
            task_description=task_description,
            context=context_str,
        )
        try:
            response = self._llm.generate(prompt, schema=_DECOMPOSITION_SCHEMA)
            subtasks_data = response.get("subtasks", [])
            if not subtasks_data:
                return None
            nodes: dict[str, SubTask] = {}
            edges: list[tuple[str, str]] = []
            for item in subtasks_data:
                tid = str(item["id"])
                sub = SubTask(
                    task_id=tid,
                    description=str(item["description"]),
                    required_capabilities=list(item.get("capabilities", [])),
                    dependencies=list(item.get("dependencies", [])),
                )
                nodes[tid] = sub
                for dep in sub.dependencies:
                    edges.append((dep, tid))
            return TaskDAG(root_task=task_description, nodes=nodes, edges=edges)
        except Exception:
            return None

    def _validate_dag(self, dag: TaskDAG) -> bool:
        if dag.node_count == 0:
            return False
        node_ids = set(dag.nodes.keys())
        for node in dag.nodes.values():
            for dep in node.dependencies:
                if dep not in node_ids:
                    return False
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            node = dag.nodes.get(node_id)
            if node is not None:
                for dep in node.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            rec_stack.discard(node_id)
            return False

        return all(not (nid not in visited and has_cycle(nid)) for nid in node_ids)

    def _safety_gate_validate(self, dag: TaskDAG) -> bool:
        capabilities_set = set()
        for node in dag.nodes.values():
            for cap in node.required_capabilities:
                capabilities_set.add(cap)
        if "halt" in capabilities_set or "circuit_break" in capabilities_set:
            if dag.node_count > 8:
                return False
        return True

    def _update_cache(self, task_description: str, dag: TaskDAG) -> None:
        if len(self._cache) >= self.MAX_CACHE_SIZE:
            oldest = min(self._cache.values(), key=lambda e: e.cached_at)
            for key, entry in list(self._cache.items()):
                if entry is oldest:
                    del self._cache[key]
                    break
        self._cache[task_description] = DecompositionCacheEntry(dag=dag)

    def _audit_decomposition(self, task: str, event: str, success: bool) -> None:
        self._audit_store.append(UnifiedAuditRecord(
            record_id=make_record_id("hdec", hash((task, event)) % 100000),
            timestamp=time.time(),
            layer="orchestration",
            round=41,
            event_type=f"decomposition_{event}",
            source_module="HybridDecomposer",
            target_module="SelfOrchestrator",
            decision=f"decompose_{task[:20]}",
            justification=f"event={event}, success={success}",
            outcome="success" if success else "failure",
        ))

    def warm_cache(self, tasks: list[str]) -> int:
        count = 0
        for task in tasks:
            dag = self._fallback.decompose(task)
            if dag.node_count > 0:
                self._update_cache(task, dag)
                count += 1
        return count

    def clear_cache(self) -> None:
        self._cache.clear()
