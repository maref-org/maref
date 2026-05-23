from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class TaskNode:
    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


class TaskGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, TaskNode] = {}
        self._edges: dict[str, list[str]] = {}

    def add_node(self, node: TaskNode) -> None:
        self._nodes[node.task_id] = node
        self._edges[node.task_id] = list(node.depends_on)

    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id not in self._nodes:
            raise ValueError(f"Node '{from_id}' not found")
        if to_id not in self._nodes:
            raise ValueError(f"Node '{to_id}' not found")
        if to_id not in self._edges[from_id]:
            self._edges[from_id].append(to_id)

    def remove_node(self, task_id: str) -> None:
        self._nodes.pop(task_id, None)
        self._edges.pop(task_id, None)
        for deps in self._edges.values():
            if task_id in deps:
                deps.remove(task_id)

    def get_node(self, task_id: str) -> TaskNode | None:
        return self._nodes.get(task_id)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    def detect_cycles(self) -> list[list[str]]:
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles: list[list[str]] = []
        path: list[str] = []

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            for dep in self._edges.get(node_id, []):
                if dep not in visited:
                    dfs(dep)
                elif dep in rec_stack:
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])
            path.pop()
            rec_stack.discard(node_id)

        for nid in self._nodes:
            if nid not in visited:
                dfs(nid)
        return cycles

    def has_cycle(self) -> bool:
        return len(self.detect_cycles()) > 0

    def topological_order(self) -> list[str]:
        cycles = self.detect_cycles()
        if cycles:
            raise ValueError(f"Graph contains {len(cycles)} cycle(s): {cycles}")
        visited: set[str] = set()
        order: list[str] = []

        def _dfs(node_id: str) -> None:
            visited.add(node_id)
            for dep in self._edges.get(node_id, []):
                if dep not in visited:
                    _dfs(dep)
            order.append(node_id)

        for nid in self._nodes:
            if nid not in visited:
                _dfs(nid)
        return order

    def get_dependents(self, task_id: str) -> list[str]:
        return [nid for nid, deps in self._edges.items() if task_id in deps]

    def get_dependencies(self, task_id: str) -> list[str]:
        return list(self._edges.get(task_id, []))

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, TaskNode):
                return _convert(asdict(obj))
            return obj
        return {
            "nodes": [_convert(asdict(n)) for n in self._nodes.values()],
            "edges": _convert({k: list(v) for k, v in self._edges.items()}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskGraph:
        g = cls()
        for n_data in data.get("nodes", []):
            status_val = n_data.pop("status", "pending")
            node = TaskNode(**n_data)
            node.status = TaskStatus(status_val)
            g.add_node(node)
        for from_id, deps in data.get("edges", {}).items():
            for to_id in deps:
                g.add_edge(from_id, to_id)
        return g

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_mermaid(self) -> str:
        lines = ["graph TD;"]
        for nid in self._nodes:
            label = self._nodes[nid].description.replace('"', "'")
            lines.append(f'    {nid}["{label}"];')
        for nid, deps in self._edges.items():
            for dep in deps:
                lines.append(f"    {dep} --> {nid};")
        return "\n".join(lines)

    def get_ready_nodes(self) -> list[str]:
        return [
            nid for nid, node in self._nodes.items()
            if node.status == TaskStatus.PENDING
            and all(
                self._nodes[dep].status == TaskStatus.COMPLETED
                for dep in self._edges.get(nid, [])
                if dep in self._nodes
            )
        ]

    def set_node_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id in self._nodes:
            self._nodes[task_id].status = status
