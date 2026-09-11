from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from maref.orchestration.task_graph import (
    NodeType,
    RiskLevel,
    TaskGraph,
    TaskNode,
    TaskStatus,
)


class LLMBackend(Protocol):
    """Protocol for LLM-based task decomposition."""

    def generate(self, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]: ...


class ParallelStrategy(Enum):
    """Loop Engineering strategy for parallel/serial decision."""

    AUTO = "auto"  # decomposer decides based on risk
    FORCE_PARALLEL = "force_parallel"  # override: run all as FORK
    FORCE_SERIAL = "force_serial"  # override: run all as SEQUENCE


@dataclass
class SubTask:
    task_id: str
    description: str
    estimated_complexity: float
    required_capabilities: list[str]
    depends_on: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    priority: int = 0


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

    def to_task_graph(self) -> TaskGraph:
        """Convert this TaskDAG to a TaskGraph with FORK/JOIN for parallel layers."""
        g = TaskGraph()
        if self.node_count == 0:
            return g

        # Group nodes by depth (topological layers)
        order = self.topological_order()
        depth: dict[str, int] = {}
        for nid in order:
            deps = self._edges.get(nid, [])
            if not deps:
                depth[nid] = 0
            else:
                depth[nid] = max(depth[d] for d in deps) + 1

        # Build layers
        layers: dict[int, list[str]] = {}
        for nid, d in depth.items():
            layers.setdefault(d, []).append(nid)

        for layer_num in sorted(layers):
            nids = layers[layer_num]

            for nid in nids:
                subtask = self._nodes[nid]
                node = TaskNode(
                    task_id=subtask.task_id,
                    description=subtask.description,
                    status=TaskStatus.PENDING,
                    depends_on=list(subtask.depends_on),
                    risk_level=subtask.risk_level,
                    metadata={
                        "complexity": subtask.estimated_complexity,
                        "capabilities": subtask.required_capabilities,
                        "priority": subtask.priority,
                    },
                )
                g.add_node(node)

            # If multiple nodes at same layer and all are parallelizable,
            # insert FORK before and JOIN after
            if len(nids) > 1:
                all_parallel = all(
                    self._nodes[nid].risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM) for nid in nids
                )
                if all_parallel:
                    fork_id = f"fork_layer_{layer_num}"
                    join_id = f"join_layer_{layer_num}"
                    g.add_fork(fork_id, nids, description=f"Parallel fork for layer {layer_num}")
                    g.add_join(join_id, nids, description=f"Parallel join for layer {layer_num}")

        return g

    @property
    def nodes(self) -> dict[str, SubTask]:
        return dict(self._nodes)


_DECOMPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subtasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique subtask identifier"},
                    "description": {"type": "string", "description": "What this subtask does"},
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required agent capabilities",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of subtasks that must complete first",
                    },
                    "parallel_group": {
                        "type": "integer",
                        "description": "Tasks in the same group CAN run in parallel; groups execute sequentially (0-based)",
                    },
                    "risk": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "low/medium=parallel-safe, high/critical=serial+HITL",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Higher number = higher priority (0 default)",
                    },
                },
                "required": ["id", "description", "capabilities", "dependencies"],
            },
        },
    },
    "required": ["subtasks"],
}

_DECOMPOSITION_PROMPT = """You are a task decomposition engine. Break the following task into subtasks.

Rules:
1. Tasks that don't depend on each other can run in parallel (same parallel_group).
2. LOW/MEDIUM risk tasks are parallel-safe. HIGH/CRITICAL risk must be serial.
3. HIGH/CRITICAL tasks: deployment, security audit, approval, production change.
4. Each subtask needs: id, description, capabilities, dependencies, parallel_group, risk, priority.
5. parallel_group 0 runs first, then group 1, then group 2, etc.
6. Within the same parallel_group, tasks run in parallel (FORK).
7. Dependencies reference subtask IDs from earlier parallel_groups.

Task: {task_description}

Available capabilities: {capabilities}

Return JSON matching the schema."""


_DECOMPOSITION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "analyze_report": [
        {
            "description": "Gather data and context",
            "complexity": 0.3,
            "depends_on": [],
            "risk": "low",
            "parallel_group": 0,
        },
        {
            "description": "Analyze findings",
            "complexity": 0.6,
            "depends_on": [0],
            "risk": "medium",
            "parallel_group": 1,
        },
        {
            "description": "Cross-validate results",
            "complexity": 0.5,
            "depends_on": [0],
            "risk": "low",
            "parallel_group": 1,
        },
        {
            "description": "Generate report",
            "complexity": 0.4,
            "depends_on": [1, 2],
            "risk": "medium",
            "parallel_group": 2,
        },
        {
            "description": "Review and finalize",
            "complexity": 0.3,
            "depends_on": [3],
            "risk": "high",
            "parallel_group": 3,
        },
    ],
    "research": [
        {
            "description": "Search and collect information",
            "complexity": 0.4,
            "depends_on": [],
            "risk": "low",
            "parallel_group": 0,
        },
        {
            "description": "Synthesize research findings",
            "complexity": 0.5,
            "depends_on": [0],
            "risk": "medium",
            "parallel_group": 1,
        },
        {
            "description": "Draft research summary",
            "complexity": 0.3,
            "depends_on": [1],
            "risk": "medium",
            "parallel_group": 2,
        },
    ],
    "develop_feature": [
        {
            "description": "Design architecture",
            "complexity": 0.5,
            "depends_on": [],
            "risk": "high",
            "parallel_group": 0,
        },
        {
            "description": "Implement backend logic",
            "complexity": 0.6,
            "depends_on": [0],
            "risk": "medium",
            "parallel_group": 1,
        },
        {
            "description": "Implement frontend UI",
            "complexity": 0.5,
            "depends_on": [0],
            "risk": "medium",
            "parallel_group": 1,
        },
        {
            "description": "Write unit tests",
            "complexity": 0.3,
            "depends_on": [0],
            "risk": "low",
            "parallel_group": 1,
        },
        {
            "description": "Run integration tests",
            "complexity": 0.3,
            "depends_on": [1, 2, 3],
            "risk": "high",
            "parallel_group": 2,
        },
        {
            "description": "Deploy and verify",
            "complexity": 0.2,
            "depends_on": [4],
            "risk": "critical",
            "parallel_group": 3,
        },
    ],
    "security_audit": [
        {
            "description": "Scan dependencies for CVEs",
            "complexity": 0.3,
            "depends_on": [],
            "risk": "low",
            "parallel_group": 0,
        },
        {
            "description": "Static code analysis",
            "complexity": 0.5,
            "depends_on": [],
            "risk": "low",
            "parallel_group": 0,
        },
        {
            "description": "Penetration test",
            "complexity": 0.7,
            "depends_on": [0, 1],
            "risk": "high",
            "parallel_group": 1,
        },
        {
            "description": "Remediate findings",
            "complexity": 0.6,
            "depends_on": [2],
            "risk": "critical",
            "parallel_group": 2,
        },
        {
            "description": "Final verification",
            "complexity": 0.3,
            "depends_on": [3],
            "risk": "high",
            "parallel_group": 3,
        },
    ],
}


_RISK_KEYWORDS: dict[str, RiskLevel] = {
    "deploy": RiskLevel.CRITICAL,
    "release": RiskLevel.CRITICAL,
    "security": RiskLevel.HIGH,
    "audit": RiskLevel.HIGH,
    "review": RiskLevel.HIGH,
    "approve": RiskLevel.CRITICAL,
    "critical": RiskLevel.CRITICAL,
}


class TaskDecomposer:
    def __init__(
        self,
        parallel_strategy: ParallelStrategy = ParallelStrategy.AUTO,
        llm_backend: LLMBackend | None = None,
    ) -> None:
        self._decomposition_rules: dict[str, Any] = {}
        self._parallel_strategy = parallel_strategy
        self._llm = llm_backend

    def decompose(
        self, task_description: str, available_capabilities: list[str]
    ) -> tuple[TaskDAG, float]:
        dag = TaskDAG()
        steps = self._extract_steps(task_description, available_capabilities)
        confidence = 0.85
        for i, step_info in enumerate(steps):
            task_id = f"subtask-{i}"
            risk = self._classify_risk(step_info)
            sub = SubTask(
                task_id=task_id,
                description=step_info["description"],
                estimated_complexity=step_info.get("complexity", 0.5),
                required_capabilities=step_info.get("capabilities", available_capabilities),
                depends_on=[f"subtask-{d}" for d in step_info.get("depends_on", []) if d < i],
                risk_level=risk,
                priority=step_info.get("priority", 0),
            )
            dag.add_node(sub)
        return dag, confidence

    def decompose_to_graph(
        self, task_description: str, available_capabilities: list[str]
    ) -> tuple[TaskGraph, float]:
        """Decompose directly into a TaskGraph with FORK/JOIN."""
        dag, confidence = self.decompose(task_description, available_capabilities)
        graph = dag.to_task_graph()
        self._apply_parallel_strategy(graph)
        return graph, confidence

    def decompose_with_llm(
        self, task_description: str, available_capabilities: list[str]
    ) -> tuple[TaskGraph, float]:
        """Use LLM backend for intelligent decomposition with risk-aware FORK/JOIN."""
        if self._llm is None:
            return self.decompose_to_graph(task_description, available_capabilities)

        prompt = _DECOMPOSITION_PROMPT.format(
            task_description=task_description,
            capabilities=", ".join(available_capabilities),
        )
        try:
            response = self._llm.generate(prompt, _DECOMPOSITION_SCHEMA)
        except Exception:
            return self.decompose_to_graph(task_description, available_capabilities)

        subtasks_raw = response.get("subtasks", [])
        if not subtasks_raw:
            return self.decompose_to_graph(task_description, available_capabilities)

        # Build parallel groups from LLM output
        groups: dict[int, list[dict[str, Any]]] = {}
        for st in subtasks_raw:
            pg = st.get("parallel_group", 0)
            groups.setdefault(pg, []).append(st)

        g = TaskGraph()

        for pg in sorted(groups):
            tasks = groups[pg]
            for st in tasks:
                task_id = st.get("id", f"llm_subtask_{pg}_{tasks.index(st)}")
                deps = []
                for dep in st.get("dependencies", []):
                    dep_task_id = dep
                    if dep_task_id not in g.node_ids:
                        dep_task_id = f"subtask_{dep}"
                    deps.append(dep_task_id)
                risk_str = st.get("risk", "medium")
                try:
                    risk = RiskLevel(risk_str)
                except ValueError:
                    risk = RiskLevel.MEDIUM
                node = TaskNode(
                    task_id=task_id,
                    description=st.get("description", task_id),
                    depends_on=deps,
                    risk_level=risk,
                    metadata={
                        "capabilities": st.get("capabilities", []),
                        "priority": st.get("priority", 0),
                    },
                )
                g.add_node(node)

            # Insert FORK/JOIN for parallel groups
            if len(tasks) > 1:
                all_parallel = all(
                    RiskLevel(st.get("risk", "medium")) in (RiskLevel.LOW, RiskLevel.MEDIUM)
                    for st in tasks
                )
                if all_parallel:
                    nids = [st.get("id", f"llm_subtask_{pg}_{i}") for i, st in enumerate(tasks)]
                    fork_id = f"llm_fork_{pg}"
                    join_id = f"llm_join_{pg}"
                    g.add_fork(fork_id, nids, description=f"LLM parallel fork group {pg}")
                    g.add_join(join_id, nids, description=f"LLM parallel join group {pg}")

        self._apply_parallel_strategy(g)
        return g, 0.9

    def _classify_risk(self, step_info: dict[str, Any]) -> RiskLevel:
        """Classify risk based on explicit label or keyword matching."""
        explicit = step_info.get("risk")
        if explicit:
            try:
                return RiskLevel(explicit)
            except ValueError:
                pass
        desc = step_info.get("description", "").lower()
        for keyword, risk in _RISK_KEYWORDS.items():
            if keyword in desc:
                return risk
        return RiskLevel.MEDIUM

    def _apply_parallel_strategy(self, graph: TaskGraph) -> None:
        """Override parallel decisions based on strategy."""
        if self._parallel_strategy == ParallelStrategy.FORCE_SERIAL:
            for nid in list(graph.node_ids):
                node = graph.get_node(nid)
                if node and node.node_type in (NodeType.FORK, NodeType.JOIN):
                    graph.remove_node(nid)
            if graph.has_cycle():
                return
            remaining = graph.topological_order()
            for i, nid in enumerate(remaining):
                node = graph.get_node(nid)
                if node:
                    if i > 0:
                        node.depends_on = [remaining[i - 1]]
                    else:
                        node.depends_on = []
                    node.node_type = NodeType.SEQUENCE

        elif self._parallel_strategy == ParallelStrategy.FORCE_PARALLEL:
            # Make all non-dependent nodes run in parallel
            remaining = graph.topological_order()
            roots = [nid for nid in remaining if not graph.get_dependencies(nid)]
            if len(roots) > 1:
                fork_id = "force_fork"
                join_id = "force_join"
                graph.add_fork(fork_id, roots)
                graph.add_join(join_id, roots)

    def _extract_steps(
        self, description: str, available_capabilities: list[str] | None = None
    ) -> list[dict[str, Any]]:
        lower = description.lower()
        # Check templates first (split key words for word-boundary matching)
        words_lower = lower.split()
        for key, steps in _DECOMPOSITION_TEMPLATES.items():
            key_words = key.split("_")
            if all(kw in words_lower for kw in key_words):
                result = []
                for s in steps:
                    step = dict(s)
                    if "capabilities" not in step and available_capabilities:
                        step["capabilities"] = available_capabilities[:2]
                    result.append(step)
                return result

        # Try LLM extraction if available
        if self._llm is not None:
            try:
                prompt = _DECOMPOSITION_PROMPT.format(
                    task_description=description,
                    capabilities=", ".join(available_capabilities or []),
                )
                response = self._llm.generate(prompt, _DECOMPOSITION_SCHEMA)
                subtasks = response.get("subtasks", [])
                if subtasks:
                    return [
                        {
                            "description": st.get("description", ""),
                            "complexity": 0.5,
                            "depends_on": [],
                            "risk": st.get("risk", "medium"),
                            "capabilities": st.get("capabilities", available_capabilities or []),
                            "priority": st.get("priority", 0),
                            "parallel_group": st.get("parallel_group", 0),
                        }
                        for st in subtasks
                    ]
            except Exception:
                pass

        # Fallback: basic keyword matching
        if "analyze" in lower and "report" in lower:
            return [
                {
                    "description": "Gather data and context",
                    "complexity": 0.3,
                    "depends_on": [],
                    "risk": "low",
                    "parallel_group": 0,
                },
                {
                    "description": "Analyze findings",
                    "complexity": 0.6,
                    "depends_on": [0],
                    "risk": "medium",
                    "parallel_group": 1,
                },
                {
                    "description": "Cross-validate results",
                    "complexity": 0.5,
                    "depends_on": [0],
                    "risk": "low",
                    "parallel_group": 1,
                },
                {
                    "description": "Generate report",
                    "complexity": 0.4,
                    "depends_on": [1, 2],
                    "risk": "medium",
                    "parallel_group": 2,
                },
                {
                    "description": "Review and finalize",
                    "complexity": 0.3,
                    "depends_on": [3],
                    "risk": "high",
                    "parallel_group": 3,
                },
            ]
        if "research" in lower:
            return [
                {
                    "description": "Search and collect information",
                    "complexity": 0.4,
                    "depends_on": [],
                    "risk": "low",
                    "parallel_group": 0,
                },
                {
                    "description": "Synthesize research findings",
                    "complexity": 0.5,
                    "depends_on": [0],
                    "risk": "medium",
                    "parallel_group": 1,
                },
                {
                    "description": "Draft research summary",
                    "complexity": 0.3,
                    "depends_on": [1],
                    "risk": "medium",
                    "parallel_group": 2,
                },
            ]
        return [
            {"description": description, "complexity": 0.5, "depends_on": [], "risk": "medium"},
        ]
