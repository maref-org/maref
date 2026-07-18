"""Pipeline Registry — governance-level pipeline registration and selection validation.

Implements "方案 A" from the pipeline governance audit:
  - PipelineRegistration: formal metadata for every pipeline
  - QualityTier: official/stable/experimental/deprecated classification
  - PipelineGovernor: intercepts agent's pipeline selection decisions

The PipelineGovernor works as a pre-governance gate. It validates pipeline
selections BEFORE they reach the GovernancePipeline, ensuring agents use
the correct pipeline for each task type.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.core_pipeline import Verdict
from maref.integration.hitl import HITLTier
from maref.security.decorators import security_critical

logger = logging.getLogger(__name__)


class QualityTier(Enum):
    """Pipeline quality classification.

    Tiers determine what level of governance gate applies when an agent
    selects this pipeline:
      OFFICIAL (0)     — Verified, documented, git-committed. Full support.
      STABLE (1)       — Works correctly but may lack full documentation.
      EXPERIMENTAL (2) — In development. Selection triggers HITL warning.
      DEPRECATED (3)   — Replaced by a newer pipeline. Selection denied by default.
    """

    OFFICIAL = 0
    STABLE = 1
    EXPERIMENTAL = 2
    DEPRECATED = 3


@dataclass(frozen=True)
class PipelineRegistration:
    """Formal registration metadata for a single pipeline.

    Every pipeline in the project should have one of these. The registry
    acts as the single source of truth for "which pipeline to use."
    """

    pipeline_id: str
    name: str
    entry_point: str
    description: str
    quality_tier: QualityTier
    tags: list[str] = field(default_factory=list)
    git_status: str = "unknown"
    commit_hash: str = ""
    verified: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "name": self.name,
            "entry_point": self.entry_point,
            "description": self.description,
            "quality_tier": self.quality_tier.name,
            "quality_tier_id": self.quality_tier.value,
            "tags": list(self.tags),
            "git_status": self.git_status,
            "commit_hash": self.commit_hash,
            "verified": self.verified,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineRegistration:
        raw_tier = data.get("quality_tier", "EXPERIMENTAL")
        tier: QualityTier
        if isinstance(raw_tier, str):
            tier = QualityTier[raw_tier]
        elif isinstance(raw_tier, int):
            tier = QualityTier(raw_tier)
        else:
            tier = raw_tier

        return cls(
            pipeline_id=data["pipeline_id"],
            name=data["name"],
            entry_point=data["entry_point"],
            description=data["description"],
            quality_tier=tier,
            tags=list(data.get("tags", [])),
            git_status=data.get("git_status", "unknown"),
            commit_hash=data.get("commit_hash", ""),
            verified=bool(data.get("verified", False)),
            metadata=dict(data.get("metadata", {})),
        )


class PipelineGovernor:
    """Pipeline selection governor — validates agent pipeline choices.

    Usage:
        governor = PipelineGovernor()
        governor.register(official_pipeline)

        # Validate before allowing agent to proceed
        verdict, reason, hitl_tier = governor.validate_selection(
            "produce_launch.js", agent_id="agent-01"
        )
        # -> ASK_USER, "Pipeline 'produce_launch.js' is EXPERIMENTAL...", P1_ESCALATE

    The governor can be integrated as a policy rule in GovernancePipeline,
    used as a standalone gate, or called from the TaskPreflight system.
    """

    def __init__(
        self,
        registry: dict[str, PipelineRegistration] | None = None,
        audit_callback: Callable[[str, str, str, str], None] | None = None,
    ) -> None:
        """Initialize with optional pre-populated registry.

        Args:
            registry: Pre-populated pipeline registry dict (id -> registration).
            audit_callback: Optional callback for audit logging.
                           Signature: (event_type, actor, detail, pipeline_id)
        """
        self._registry: dict[str, PipelineRegistration] = dict(registry or {})
        self._audit_callback = audit_callback

    def register(self, registration: PipelineRegistration) -> None:
        """Register a pipeline. Replaces any existing registration with the same id."""
        self._registry[registration.pipeline_id] = registration
        logger.info(
            "Pipeline registered: %s (%s) - tier=%s",
            registration.pipeline_id,
            registration.entry_point,
            registration.quality_tier.name,
        )

    def register_from_dict(self, data: dict[str, Any]) -> PipelineRegistration:
        """Create a PipelineRegistration from a dict and register it."""
        reg = PipelineRegistration.from_dict(data)
        self.register(reg)
        return reg

    def get_pipeline(self, pipeline_id: str) -> PipelineRegistration | None:
        """Look up a pipeline by id."""
        return self._registry.get(pipeline_id)

    @security_critical
    def validate_selection(
        self,
        selected_id: str,
        agent_id: str = "unknown",
    ) -> tuple[Verdict, str, HITLTier | None]:
        """Validate an agent's pipeline selection.

        Returns a (Verdict, reason, HITLTier) tuple compatible with
        GovernancePipeline policy rules.

        Validation rules:
          - Unregistered pipeline -> ASK_USER (unrecognised)
          - EXPERIMENTAL tier     -> ASK_USER (with warning)
          - DEPRECATED tier       -> DENY (must use replacement)
          - OFFICIAL/STABLE tier  -> ALLOW
        """
        reg = self._registry.get(selected_id)

        if reg is None:
            msg = (
                f"Pipeline '{selected_id}' is not registered in the pipeline registry. "
                f"Use a registered pipeline or register '{selected_id}' first."
            )
            self._audit("pipeline.unregistered", agent_id, msg, selected_id)
            return Verdict.ASK_USER, msg, HITLTier.P1_ESCALATE

        if reg.quality_tier == QualityTier.DEPRECATED:
            msg = (
                f"Pipeline '{selected_id}' ({reg.name}) is DEPRECATED. "
                f"Do not use. Check the registry for the replacement."
            )
            self._audit("pipeline.deprecated", agent_id, msg, selected_id)
            return Verdict.DENY, msg, HITLTier.P2_LOG

        if reg.quality_tier == QualityTier.EXPERIMENTAL:
            msg = (
                f"Pipeline '{selected_id}' ({reg.name}) is EXPERIMENTAL. "
                f"It has not been verified. Prefer an OFFICIAL pipeline."
            )
            self._audit("pipeline.experimental", agent_id, msg, selected_id)
            return Verdict.ASK_USER, msg, HITLTier.P1_ESCALATE

        if not reg.verified and reg.quality_tier == QualityTier.STABLE:
            msg = (
                f"Pipeline '{selected_id}' ({reg.name}) is STABLE but not verified. "
                f"Proceed with caution."
            )
            self._audit("pipeline.unverified", agent_id, msg, selected_id)
            return Verdict.ASK_USER, msg, HITLTier.P2_LOG

        self._audit("pipeline.allowed", agent_id, f"Pipeline '{selected_id}' allowed", selected_id)
        return Verdict.ALLOW, "", None

    def suggest_best(self, task_type: str) -> list[PipelineRegistration]:
        """Suggest the best pipeline(s) for a given task type.

        Args:
            task_type: A tag string matching the task (e.g. "video", "audio", "build").

        Returns:
            Sorted list of matching pipelines (best first by tier + verified status).
        """
        candidates = [
            r for r in self._registry.values()
            if task_type in r.tags
        ]
        candidates.sort(key=lambda r: (r.quality_tier.value, 0 if r.verified else 1))
        return candidates

    def list_pipelines(self) -> dict[str, PipelineRegistration]:
        """Return a copy of the full registry."""
        return dict(self._registry)

    def list_pipelines_by_tier(self, tier: QualityTier) -> list[PipelineRegistration]:
        """List all pipelines at a specific quality tier."""
        return [r for r in self._registry.values() if r.quality_tier == tier]

    def count(self) -> int:
        return len(self._registry)

    def _audit(self, event_type: str, actor: str, detail: str, pipeline_id: str) -> None:
        if self._audit_callback:
            self._audit_callback(event_type, actor, detail, pipeline_id)
