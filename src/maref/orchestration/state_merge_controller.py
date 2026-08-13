from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maref.orchestration.protocols import AgentTaskResult, TaskResultStatus


@dataclass
class Conflict:
    task_ids: list[str]
    description: str
    severity: str = "medium"
    mitigation: str = ""


@dataclass
class MergeResult:
    merged: bool = True
    conflicts: list[Conflict] = field(default_factory=list)
    needs_rework: bool = False
    needs_human_review: bool = False
    rework_tasks: list[str] = field(default_factory=list)
    quality_score: float = 1.0


class StateMergeController:
    """Collects parallel agent results, detects conflicts, and decides on progression.

    Loop Engineering Step 4:
    "监工收到回包后，把内容合并到状态板，检查质量、发现冲突，决定是返工还是进入下一个环节"
    """

    def __init__(
        self,
        conflict_threshold: float = 0.3,
        quality_threshold: float = 0.6,
    ):
        self._conflict_threshold = conflict_threshold
        self._quality_threshold = quality_threshold

    def merge(
        self,
        results: list[AgentTaskResult],
        previous_results: list[AgentTaskResult] | None = None,
    ) -> MergeResult:
        conflicts: list[Conflict] = []
        rework_tasks: list[str] = []
        all_passed = True
        total_quality = 0.0

        for result in results:
            # Check self-check quality
            total_quality += result.self_check.quality_score

            if result.status == TaskResultStatus.FAILED:
                all_passed = False
                rework_tasks.append(result.task_id)
                conflicts.append(
                    Conflict(
                        task_ids=[result.task_id],
                        description=f"Task {result.task_id} failed: {result.summary}",
                        severity="high",
                    )
                )

            if result.status == TaskResultStatus.NEEDS_REWORK:
                all_passed = False
                rework_tasks.append(result.task_id)

            if not result.self_check.passed:
                all_passed = False
                if result.self_check.quality_score < self._quality_threshold:
                    rework_tasks.append(result.task_id)

            # High-severity risks trigger rework
            for risk in result.risks:
                if risk.severity in ("high", "critical"):
                    rework_tasks.append(result.task_id)
                    conflicts.append(
                        Conflict(
                            task_ids=[result.task_id],
                            description=f"Risk in {result.task_id}: {risk.description}",
                            severity=risk.severity,
                            mitigation=risk.mitigation,
                        )
                    )

        # Cross-task conflict detection
        if len(results) > 1:
            cross_conflicts = self._detect_cross_conflicts(results, previous_results)
            conflicts.extend(cross_conflicts)

        avg_quality = total_quality / max(len(results), 1)

        needs_human = any(r.needs_human_review for r in results) or any(
            c.severity == "critical" for c in conflicts
        )

        return MergeResult(
            merged=all_passed and not rework_tasks,
            conflicts=conflicts,
            needs_rework=bool(rework_tasks),
            needs_human_review=needs_human,
            rework_tasks=list(set(rework_tasks)),
            quality_score=avg_quality,
        )

    def _detect_cross_conflicts(
        self,
        results: list[AgentTaskResult],
        previous_results: list[AgentTaskResult] | None = None,
    ) -> list[Conflict]:
        """Detect semantic conflicts between parallel agent results."""
        conflicts: list[Conflict] = []

        for i, a in enumerate(results):
            for b in results[i + 1 :]:
                # Same task submitted by different agents
                if a.task_id == b.task_id:
                    conflicts.append(
                        Conflict(
                            task_ids=[a.task_id, b.task_id],
                            description=f"Duplicate task_id {a.task_id} from parallel agents",
                            severity="high",
                        )
                    )

                # Contradictory next steps
                if a.next_steps and b.next_steps:
                    common = set(a.next_steps) & set(b.next_steps)
                    if not common and len(a.next_steps) > 0 and len(b.next_steps) > 0:
                        conflicts.append(
                            Conflict(
                                task_ids=[a.task_id, b.task_id],
                                description=f"Divergent next steps between {a.task_id} and {b.task_id}",
                                severity="low",
                            )
                        )

        return conflicts

    def decide_route(
        self,
        merge_result: MergeResult,
        graph: Any,
    ) -> str:
        """Decide next action based on merge state.

        Returns: 'continue', 'rework', 'human_review', 'abort'
        """
        if merge_result.needs_human_review:
            return "human_review"
        if merge_result.needs_rework:
            return "rework"
        if not merge_result.merged:
            return "rework"
        return "continue"
