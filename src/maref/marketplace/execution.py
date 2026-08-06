from __future__ import annotations

from typing import Any

from maref.marketplace.adapter import ManifestAdapter
from maref.marketplace.loader import MarketplaceSkillLoader
from maref.marketplace.registry import SkillManifest, SkillStatus
from maref.recursive.skill_executor import ExecutionResult, ExecutionStatus, SkillExecutor


def execute_skill(
    skill_id: str,
    context: dict[str, Any] | None = None,
    loader: MarketplaceSkillLoader | None = None,
    executor: SkillExecutor | None = None,
) -> ExecutionResult:
    if loader is None:
        loader = MarketplaceSkillLoader()
    if executor is None:
        executor = SkillExecutor()

    status = loader.get_status(skill_id)
    if status is None:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            handler_used="__lookup__",
            error=f"Skill {skill_id} not found in registry",
        )
    if status != SkillStatus.APPROVED:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            handler_used="__gate__",
            error=f"Skill {skill_id} status is {status.value}, must be approved",
        )

    manifest = loader.get_manifest(skill_id)
    if manifest is None:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            handler_used="__lookup__",
            error=f"Skill {skill_id} manifest not found",
        )

    maref = ManifestAdapter.to_maref(manifest)
    return executor.execute(maref, context)


def approve_and_execute(
    manifest: SkillManifest,
    context: dict[str, Any] | None = None,
    loader: MarketplaceSkillLoader | None = None,
    executor: SkillExecutor | None = None,
) -> ExecutionResult:
    if loader is None:
        loader = MarketplaceSkillLoader()
    if executor is None:
        executor = SkillExecutor()

    loader.register_and_approve(manifest)
    return execute_skill(manifest.skill_id, context, loader, executor)
