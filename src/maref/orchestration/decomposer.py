from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubTask:
    task_id: str
    description: str
    estimated_complexity: float
    required_capabilities: list[str]
    depends_on: list[str] = field(default_factory=list)


class TaskDAG:
    def __init__(self) -> None:
        self._nodes: dict[str, SubTask] = {}
        self._edges: dict[str, list[str]] = {}

    def add_node(self, task: SubTask) -> None:
        self._nodes[task.task_id] = task
        self._edges[task.task_id] = list(task.depends_on)

    def has_cycle(self) -> bool:
        visited: set[str] = set()
        stack: set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            stack.add(node_id)
            for dep in self._edges.get(node_id, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in stack:
                    return True
            stack.discard(node_id)
            return False

        return any(node_id not in visited and dfs(node_id) for node_id in self._nodes)

    def topological_order(self) -> list[str]:
        if self.has_cycle():
            raise ValueError("DAG contains a cycle")
        visited: set[str] = set()
        order: list[str] = []

        def _dfs(node_id: str) -> None:
            visited.add(node_id)
            for dep in self._edges.get(node_id, []):
                if dep not in visited:
                    _dfs(dep)
            order.append(node_id)

        for node_id in self._nodes:
            if node_id not in visited:
                _dfs(node_id)
        return order

    @property
    def node_count(self) -> int:
        return len(self._nodes)


class TaskDecomposer:
    def __init__(self) -> None:
        self._decomposition_rules: dict[str, Any] = {}

    def decompose(
        self, task_description: str, available_capabilities: list[str]
    ) -> tuple[TaskDAG, float]:
        dag = TaskDAG()
        steps = self._extract_steps(task_description)
        confidence = 0.85
        for i, step_info in enumerate(steps):
            task_id = f"subtask-{i}"
            sub = SubTask(
                task_id=task_id,
                description=step_info["description"],
                estimated_complexity=step_info.get("complexity", 0.5),
                required_capabilities=step_info.get("capabilities", available_capabilities),
                depends_on=[f"subtask-{d}" for d in step_info.get("depends_on", []) if d < i],
            )
            dag.add_node(sub)
        return dag, confidence

    def _extract_steps(self, description: str) -> list[dict[str, Any]]:
        lower = description.lower()
        if "analyze" in lower and "report" in lower:
            return [
                {"description": "Gather data and context", "complexity": 0.3, "depends_on": []},
                {"description": "Analyze findings", "complexity": 0.6, "depends_on": [0]},
                {"description": "Generate report", "complexity": 0.4, "depends_on": [1]},
            ]
        if "research" in lower:
            return [
                {
                    "description": "Search and collect information",
                    "complexity": 0.4,
                    "depends_on": [],
                },
                {
                    "description": "Synthesize research findings",
                    "complexity": 0.5,
                    "depends_on": [0],
                },
                {"description": "Draft research summary", "complexity": 0.3, "depends_on": [1]},
            ]
        return [
            {"description": description, "complexity": 0.5, "depends_on": []},
        ]
