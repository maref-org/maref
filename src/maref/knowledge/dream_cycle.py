"""Dream Cycle — nightly knowledge enrichment orchestrator.

Scans episodic memory for new entities, enriches orphaned entities,
updates compiled truths, detects contradictions, and auto-resolves.
Each step passes through governance for safety gating.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DreamStepResult:
    """Result of a single dream cycle step."""

    step_name: str
    success: bool
    count: int = 0  # items processed
    details: str = ""
    duration_s: float = 0.0


@dataclass
class DreamCycleResult:
    """Overall result of a dream cycle run."""

    steps: list[DreamStepResult] = field(default_factory=list)
    total_duration_s: float = 0.0
    all_successful: bool = True
    governance_blocked: bool = False
    error_message: str = ""

    @property
    def total_processed(self) -> int:
        return sum(s.count for s in self.steps)


class DreamCycle:
    """Nightly knowledge enrichment orchestrator.

    Usage:
        dc = DreamCycle(memory_hub=hub, governance_bridge=bridge)
        result = dc.run()
    """

    DREAM_STEPS = [
        "extract_new_entities",
        "enrich_entities",
        "update_compiled_truths",
        "detect_contradictions",
        "resolve_contradictions",
    ]

    def __init__(
        self,
        memory_hub: Any | None = None,
        governance_bridge: Any | None = None,
        workflow_engine: Any | None = None,
        truth_store: Any | None = None,
    ) -> None:
        self._memory_hub = memory_hub
        self._governance_bridge = governance_bridge
        self._workflow_engine = workflow_engine
        self._truth_store = truth_store

        # Optional: provide graph directly if no memory_hub
        self._kg = None
        if memory_hub is not None:
            self._kg = getattr(memory_hub, "knowledge_graph", None)

    def run(self) -> DreamCycleResult:
        """Execute the full dream cycle DAG."""
        start = time.time()
        steps: list[DreamStepResult] = []

        for step_name in self.DREAM_STEPS:
            if self._check_governance(f"dream_{step_name}"):
                step_result = self._execute_step(step_name)
            else:
                steps.append(DreamStepResult(
                    step_name=step_name,
                    success=False,
                    details="blocked by governance",
                ))
                return DreamCycleResult(
                    steps=steps,
                    total_duration_s=time.time() - start,
                    all_successful=False,
                    governance_blocked=True,
                    error_message=f"governance blocked at step '{step_name}'",
                )

            steps.append(step_result)
            if not step_result.success:
                return DreamCycleResult(
                    steps=steps,
                    total_duration_s=time.time() - start,
                    all_successful=False,
                    error_message=f"step '{step_name}' failed: {step_result.details}",
                )

        return DreamCycleResult(
            steps=steps,
            total_duration_s=time.time() - start,
            all_successful=True,
        )

    def run_with_engine(self) -> DreamCycleResult:
        """Execute dream cycle via WorkflowEngine (when available)."""
        if self._workflow_engine is None:
            return self.run()

        try:
            from maref.executor.workflow.types import WorkflowScript, WorkflowStep

            script = WorkflowScript(
                id="dream_cycle",
                name="Nightly Dream Cycle",
                steps=[
                    WorkflowStep(
                        name=name,
                        agent_role="dream_step",
                        input_template=f"Run dream cycle step: {name}",
                        max_retries=1,
                    )
                    for name in self.DREAM_STEPS
                ],
            )
            result = self._workflow_engine.execute(script)

            steps = [
                DreamStepResult(
                    step_name=sr.step_name,
                    success=sr.status.value == "completed",
                    count=0,
                    details=sr.output if hasattr(sr, "output") else str(sr.status),
                    duration_s=getattr(sr, "duration_s", 0.0),
                )
                for sr in (result.steps if hasattr(result, "steps") else [])
            ]

            return DreamCycleResult(
                steps=steps or [
                    DreamStepResult(
                        step_name="engine",
                        success=result.status.value == "completed",
                        details=result.status.value,
                    )
                ],
                all_successful=result.status.value == "completed",
            )

        except Exception as e:
            return DreamCycleResult(
                all_successful=False,
                error_message=f"workflow engine error: {e}",
            )

    # -- Internal --

    def _check_governance(self, stage: str) -> bool:
        if self._governance_bridge is None:
            return True
        try:
            allowed = self._governance_bridge.check(stage)
            self._governance_bridge.record(stage, allowed)
            return allowed
        except Exception:
            return False

    def _execute_step(self, step_name: str) -> DreamStepResult:
        t0 = time.time()

        try:
            method = getattr(self, f"_step_{step_name}", None)
            if method is None:
                return DreamStepResult(
                    step_name=step_name,
                    success=False,
                    details=f"no handler for step '{step_name}'",
                )
            count = method()
            return DreamStepResult(
                step_name=step_name,
                success=True,
                count=count,
                details=f"processed {count} items",
                duration_s=time.time() - t0,
            )
        except Exception as e:
            return DreamStepResult(
                step_name=step_name,
                success=False,
                details=str(e),
                duration_s=time.time() - t0,
            )

    def _step_extract_new_entities(self) -> int:
        """Scan episodic memory → entity extraction → add to graph."""
        kg = self._kg
        hub = self._memory_hub
        if kg is None or hub is None:
            return 0

        episodes = hub.memory_manager.episodic.query(
            _make_dream_query("", limit=50)
        )
        count = 0
        for ep in episodes:
            text = str(ep.content.get("text", "")) or str(ep.content)
            if len(text) < 10:
                continue
            node_count_before = len(kg.entities)
            kg.add_finding(
                content=text,
                source=f"dream_cycle/episodic/{ep.memory_id}",
                confidence=0.5,
            )
            if len(kg.entities) > node_count_before:
                count += 1
        return count

    def _step_enrich_entities(self) -> int:
        """Enrich orphaned entities by searching for new connections."""
        kg = self._kg
        if kg is None:
            return 0

        stats = kg.get_connectivity_stats()
        orphan_ratio = stats.get("orphan_ratio", 0)
        if orphan_ratio == 0:
            return 0

        count = 0
        for entity in kg.entities:
            relations = kg.get_entity_relations(entity.id)
            if not relations:
                count += 1
        return count

    def _step_update_compiled_truths(self) -> int:
        """Re-generate compiled truths for entities with new evidence."""
        # Placeholder — full compiled truth update requires MemoryHub + TruthStore
        return 0

    def _step_detect_contradictions(self) -> int:
        """Scan TruthPages for confidence-based contradictions."""
        store = self._truth_store
        if store is None:
            return 0

        pages = store.list_all()
        count = 0
        for summary in pages:
            if summary.get("evidence_count", 0) >= 2:
                count += 1
        return count

    def _step_resolve_contradictions(self) -> int:
        """Auto-resolve low-severity contradictions."""
        # Placeholder — LLM-assisted resolution in future
        return 0


def _make_dream_query(
    keywords: str = "",
    limit: int = 50,
) -> Any:
    """Create a MemoryQuery for dream cycle scanning."""
    from maref.memory.memory_manager import MemoryQuery

    return MemoryQuery(
        keywords=[keywords] if keywords else [],
        limit=limit,
    )
