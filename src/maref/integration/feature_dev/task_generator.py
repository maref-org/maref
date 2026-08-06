from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from maref.integration.feature_dev.doc_ingestor import (
    DeployStage,
    DocumentSection,
    FeatureDocument,
)


@dataclass
class LayerCriterion:
    layer_number: int
    layer_name: str
    target_score: float = 80.0
    weight: float = 1.0
    eval_prompt: str = ""


_LAYER_TEMPLATES: dict[int, tuple[str, str]] = {
    1: (
        "Static Audit",
        "Evaluate compliance, schema validity, and static analysis coverage "
        "for the feature requirements. Check that all documented constraints "
        "are addressable and no structural gaps exist.",
    ),
    2: (
        "Reasoning Metrics",
        "Evaluate how well the research/design phase covers the requirements. "
        "Check depth of analysis, trade-off exploration, and architectural "
        "coherence relative to the feature doc.",
    ),
    3: (
        "Action Metrics",
        "Evaluate implementation readiness: tool coverage, task breakdown, "
        "dependency mapping, and resource allocation for the feature.",
    ),
    4: (
        "E2E Metrics",
        "Evaluate end-to-end scenario coverage: whether the full workflow "
        "from input to deployment is addressed, including integration points "
        "and rollback paths.",
    ),
    5: (
        "MAS Dimensions",
        "Evaluate multi-agent coordination: whether the feature requires "
        "cross-agent orchestration, state isolation, or conflict resolution. "
        "Assess if the decomposition respects agent boundaries.",
    ),
}


@dataclass
class FeatureTask:
    task_id: str
    title: str
    description: str
    deploy_stage: DeployStage
    source_section: str
    criteria: list[LayerCriterion] = field(default_factory=list)
    subtasks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class TaskGenerator:
    def __init__(self, doc: FeatureDocument) -> None:
        self._doc = doc
        self._tasks: list[FeatureTask] = []

    def generate(self) -> list[FeatureTask]:
        self._tasks = []
        for stage in DeployStage:
            if stage == DeployStage.UNKNOWN:
                continue
            sections = self._doc.stages.get(stage, [])
            if not sections:
                continue
            task = self._build_stage_task(stage, sections)
            self._tasks.append(task)
        if not self._tasks:
            self._tasks.append(self._build_fallback_task())
        return self._tasks

    def _build_stage_task(self, stage: DeployStage, sections: list[DocumentSection]) -> FeatureTask:
        stage_labels = {
            DeployStage.MVP: "MVP",
            DeployStage.MIXED: "Mixed Period",
            DeployStage.INTERNALIZATION: "Internalization",
        }
        label = stage_labels.get(stage, stage.value)
        title = f"{self._doc.title} — {label}"
        reqs = []
        milestones = []
        for s in sections:
            reqs.extend(s.requirements)
            milestones.extend(s.milestones)
        joined_reqs = "; ".join(reqs[:10])
        if len(reqs) > 10:
            joined_reqs += f" ... ({len(reqs) - 10} more)"
        description = (
            f"Implement {label} phase of {self._doc.title}. "
            f"Milestones: {len(milestones)}. "
            f"Requirements: {len(reqs)}. "
            f"Details: {joined_reqs}"
        )

        criteria = self._build_criteria(stage)

        subtasks = milestones[:8] if milestones else [f"Complete {label} analysis"]

        return FeatureTask(
            task_id=f"feature-{stage.value}-{uuid4().hex[:8]}",
            title=title,
            description=description,
            deploy_stage=stage,
            source_section=sections[0].heading if sections else label,
            criteria=criteria,
            subtasks=subtasks,
        )

    def _build_criteria(self, stage: DeployStage) -> list[LayerCriterion]:
        score_targets = {
            DeployStage.MVP: 60.0,
            DeployStage.MIXED: 80.0,
            DeployStage.INTERNALIZATION: 90.0,
        }
        target = score_targets.get(stage, 60.0)
        return [
            LayerCriterion(
                layer_number=num,
                layer_name=name,
                target_score=target,
                eval_prompt=prompt,
            )
            for num, (name, prompt) in _LAYER_TEMPLATES.items()
        ]

    def _build_fallback_task(self) -> FeatureTask:
        return FeatureTask(
            task_id=f"feature-fallback-{uuid4().hex[:8]}",
            title=f"{self._doc.title} — Full Implementation",
            description=(
                f"Full implementation of {self._doc.title}. "
                f"Total sections: {len(self._doc.all_sections)}."
            ),
            deploy_stage=DeployStage.UNKNOWN,
            source_section="full-doc",
            criteria=self._build_criteria(DeployStage.MVP),
            subtasks=["Analyze document structure", "Extract requirements", "Plan implementation"],
        )

    def to_research_topics(self) -> list[str]:
        topics = []
        for task in self._tasks:
            topics.append(task.title)
            for sub in task.subtasks:
                topics.append(f"{task.title}: {sub}")
        return topics

    def get_initial_research_topic(self) -> str:
        if not self._tasks:
            return self._doc.title
        main = self._tasks[0]
        summary = "; ".join(main.subtasks[:3])
        return f"{main.title}: {summary}"
