"""Task Preflight 2.0 — task-level governance gate before execution.

Implements "方案 C" from the pipeline governance audit:
  - PreflightCheck: individual check (read README, evaluate pipelines, check git, etc.)
  - TaskPreflight: orchestrator that runs all checks before a task executes
  - Integration with PipelineGovernor for pipeline selection validation

This is NOT a replacement for GovernancePipeline. It runs BEFORE the
governance pipeline, at the task-planning level, answering:
  1. Has the agent familiarised itself with the project?
  2. Has the agent evaluated alternative approaches?
  3. Is the selected approach consistent with project conventions?
  4. Has the agent checked relevant git history?
  5. Is the decision auditable?
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from maref.governance.pipeline_registry import PipelineGovernor, QualityTier

logger = logging.getLogger(__name__)


class PreflightCheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class PreflightCheckResult:
    """Result of a single preflight check."""

    check_name: str
    status: PreflightCheckStatus
    description: str
    evidence: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status.value,
            "description": self.description,
            "evidence": self.evidence,
            "details": dict(self.details),
        }


@dataclass
class PreflightResult:
    """Aggregated result of all preflight checks for a task."""

    passed: bool
    checks: list[PreflightCheckResult]
    agent_id: str
    task_description: str
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "agent_id": self.agent_id,
            "task_description": self.task_description,
            "timestamp": self.timestamp or time.time(),
        }

    @property
    def failed_checks(self) -> list[PreflightCheckResult]:
        return [c for c in self.checks if c.status == PreflightCheckStatus.FAIL]

    @property
    def warn_checks(self) -> list[PreflightCheckResult]:
        return [c for c in self.checks if c.status == PreflightCheckStatus.WARN]

    @property
    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.status == PreflightCheckStatus.PASS)
        failed = len(self.failed_checks)
        warns = len(self.warn_checks)
        return f"{'PASS' if self.passed else 'FAIL'} — {passed}/{total} passed, {failed} failed, {warns} warnings"


class PreflightCheck:
    """Base class for a single preflight check.

    Subclasses must set `name` and implement `execute()`.
    """

    name: str = ""

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete check implementations
# ---------------------------------------------------------------------------


class ReadmeReadCheck(PreflightCheck):
    """Check that the agent has read the project README.

    Context key: ``readme_read`` (bool) — whether the agent read the README.
    Context key: ``readme_summary`` (str, optional) — evidence of reading.
    """

    name = "readme_read"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        has_read = bool(context.get("readme_read", False))
        summary = context.get("readme_summary", "")

        if has_read and summary:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description="README 已阅读并理解项目架构与管线入口",
                evidence=summary[:200],
                details={"has_read": True, "summary_length": len(summary)},
            )
        if has_read:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description="README 已标记为已读，但缺少摘要证据",
                evidence="",
                details={"has_read": True, "has_summary": False},
            )

        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.FAIL,
            description="未阅读 README.md — 代理必须先了解项目架构和管线入口后才可执行任务",
            evidence="",
            details={"has_read": False},
        )


class PipelineSelectionCheck(PreflightCheck):
    """Check that the agent selected an appropriate pipeline.

    Uses PipelineGovernor to validate the selection against the registry.
    If no governor is provided, falls back to a basic check.

    Context key: ``selected_pipeline`` (str) — the pipeline ID the agent chose.
    Context key: ``pipeline_governor`` (PipelineGovernor, optional) — registry.
    Context key: ``task_type`` (str, optional) — type tag for suggestions.
    """

    name = "pipeline_selection"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        selected = context.get("selected_pipeline", "")
        governor: PipelineGovernor | None = context.get("pipeline_governor")

        if not selected:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.FAIL,
                description="未选择管线 — 代理必须指定要使用的管线",
                evidence="",
                details={"selected_pipeline": ""},
            )

        if governor is None:
            # Fallback: basic existence check
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description=f"选择了管线 '{selected}'，但未提供 PipelineGovernor 进行注册验证",
                evidence=selected,
                details={"selected_pipeline": selected, "governor_available": False},
            )

        reg = governor.get_pipeline(selected)
        if reg is None:
            task_type = context.get("task_type", "")
            suggestions = governor.suggest_best(task_type) if task_type else []
            suggestion_text = ""
            if suggestions:
                best = suggestions[0]
                suggestion_text = (
                    f"推荐使用官方管线 '{best.pipeline_id}' ({best.name})"
                )

            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.FAIL,
                description=(
                    f"管线 '{selected}' 未在注册表中注册。"
                    + (f" {suggestion_text}" if suggestion_text else "")
                ),
                evidence=f"selected={selected}",
                details={
                    "selected_pipeline": selected,
                    "registered_pipelines": list(governor.list_pipelines().keys()),
                    "suggestions": [s.pipeline_id for s in suggestions],
                },
            )

        if reg.quality_tier == QualityTier.DEPRECATED:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.FAIL,
                description=f"管线 '{selected}' ({reg.name}) 已标记为 DEPRECATED，不应使用",
                evidence=f"tier={reg.quality_tier.name}",
                details={"selected_pipeline": selected, "tier": "DEPRECATED"},
            )

        if reg.quality_tier == QualityTier.EXPERIMENTAL:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description=f"管线 '{selected}' ({reg.name}) 是 EXPERIMENTAL 管线，建议使用 OFFICIAL 管线",
                evidence=f"tier={reg.quality_tier.name}",
                details={"selected_pipeline": selected, "tier": "EXPERIMENTAL"},
            )

        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.PASS,
            description=f"管线 '{selected}' ({reg.name}) — tier={reg.quality_tier.name}，选择合理",
            evidence=f"tier={reg.quality_tier.name}, verified={reg.verified}",
            details={
                "selected_pipeline": selected,
                "tier": reg.quality_tier.name,
                "verified": reg.verified,
            },
        )


class GitHistoryCheck(PreflightCheck):
    """Check that the agent has consulted git history for context.

    Context key: ``git_log_consulted`` (bool) — whether agent checked git log.
    Context key: ``git_log_entries`` (int, optional) — number of entries reviewed.
    Context key: ``git_files_checked`` (list[str], optional) — files reviewed.
    """

    name = "git_history"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        consulted = bool(context.get("git_log_consulted", False))
        entries = context.get("git_log_entries", 0)
        files = context.get("git_files_checked", [])

        if consulted and entries > 0:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description=f"已查阅 Git 历史 ({entries} 条提交记录)",
                evidence=f"entries={entries}, files={files}",
                details={"entries_consulted": entries, "files_checked": files},
            )

        if consulted:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description="已查阅 Git 历史，但无具体条目数",
                evidence="",
                details={"entries_consulted": 0},
            )

        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.FAIL,
            description="未查阅 Git 历史 — 代理应先了解相关文件的提交历史和变更记录",
            evidence="",
            details={"git_log_consulted": False},
        )


class AlternativesComparedCheck(PreflightCheck):
    """Check that the agent compared alternative approaches before choosing.

    Context key: ``alternatives_considered`` (list[str]) — approaches considered.
    Context key: ``alternatives_rationale`` (str, optional) — why chosen.
    """

    name = "alternatives_compared"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        alternatives = context.get("alternatives_considered", [])
        rationale = context.get("alternatives_rationale", "")

        if len(alternatives) >= 2 and rationale:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description=f"已比较 {len(alternatives)} 种方案并记录了选择理由",
                evidence=f"alternatives={alternatives}, rationale={rationale[:100]}",
                details={
                    "alternatives_count": len(alternatives),
                    "alternatives": alternatives,
                    "has_rationale": True,
                },
            )

        if len(alternatives) >= 2:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description=f"已比较 {len(alternatives)} 种方案但未记录选择理由",
                evidence=f"alternatives={alternatives}",
                details={
                    "alternatives_count": len(alternatives),
                    "alternatives": alternatives,
                    "has_rationale": False,
                },
            )

        if len(alternatives) == 1:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.FAIL,
                description="只考虑了 1 种方案 — 代理应至少比较 2 种以上方案",
                evidence=f"alternatives={alternatives}",
                details={
                    "alternatives_count": 1,
                    "alternatives": alternatives,
                },
            )

        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.FAIL,
            description="未比较任何备选方案 — 代理必须评估多种方案后才可选择执行路径",
            evidence="",
            details={"alternatives_count": 0},
        )


class DecisionLoggedCheck(PreflightCheck):
    """Check that the decision was logged for audit trail.

    Context key: ``decision_logged`` (bool) — whether decision was recorded.
    Context key: ``decision_log_location`` (str, optional) — where logged.
    """

    name = "decision_logged"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        logged = bool(context.get("decision_logged", False))
        location = context.get("decision_log_location", "")

        if logged and location:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description=f"决策已记录至审计日志: {location}",
                evidence=location,
                details={"logged": True, "location": location},
            )

        if logged:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.WARN,
                description="决策已标记为已记录，但未指定日志位置",
                evidence="",
                details={"logged": True, "location": ""},
            )

        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.FAIL,
            description="决策未被记录到审计日志 — 所有任务决策必须有可追溯的审计记录",
            evidence="",
            details={"logged": False},
        )


class RiskAuthorizationCheck(PreflightCheck):
    """决策分级授权检查（方案 D）。

    依据动作风险分级与授权范围证书判定是否放行：
    - LOW/MEDIUM：自动放行
    - HIGH：需 scope 显式授权，否则 FAIL（触发 HITL）
    - IRREVERSIBLE：强制多验证者/HITL，无授权则 FAIL

    Context keys:
    - ``action`` (str)：待执行动作标识
    - ``authorization_scope`` (AuthorizationScope | dict)：授权范围证书
    - ``risk_metadata`` (dict, optional)：风险分级上下文
    """

    name = "risk_authorization"

    def execute(self, context: dict[str, Any]) -> PreflightCheckResult:
        from maref.governance.trust_boundary import TrustBoundaryManager

        action = context.get("action", "")
        if not action:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description="无待执行动作 — 分级授权检查跳过",
                evidence="",
            )

        metadata = context.get("risk_metadata", {}) or {}
        scope_data = context.get("authorization_scope")
        scope = None
        if scope_data is not None:
            from maref.identity.credential import AuthorizationScope

            if isinstance(scope_data, AuthorizationScope):
                scope = scope_data
            elif isinstance(scope_data, dict):
                scope = AuthorizationScope(
                    subject_did=scope_data.get("subject_did", ""),
                    max_risk_level=scope_data.get("max_risk_level", "LOW"),
                    allowed_actions=scope_data.get("allowed_actions", []),
                    valid_until=scope_data.get("valid_until"),
                    jurisdiction=scope_data.get("jurisdiction", "local"),
                    issuer=scope_data.get("issuer", ""),
                )

        # S1 接线：风险分级 + 授权范围 + 目标域白名单统一交给
        # TrustBoundaryManager 强制裁决（fail-closed）。
        boundary = TrustBoundaryManager(
            scope=scope,
            allowed_domains=context.get("allowed_domains"),
            fail_closed=True,
        )
        decision = boundary.check_no_raise(
            action,
            agent_id=str(context.get("agent_id", "unknown")),
            metadata=metadata,
        )
        assessment = decision.assessment
        base_details = {
            "action": action,
            "risk_level": assessment.risk_level.value,
            "reasons": list(assessment.reasons),
        }

        if decision.allowed:
            return PreflightCheckResult(
                check_name=self.name,
                status=PreflightCheckStatus.PASS,
                description=(
                    f"动作 {action} 风险等级 {assessment.risk_level.value} — 放行"
                    f"（{decision.reason}）"
                ),
                evidence=decision.reason,
                details={**base_details, "authorized": True},
            )

        details: dict[str, Any] = {
            **base_details,
            "authorized": False,
            "action_required": "HITL",
        }
        if scope is not None:
            details["max_risk_level"] = scope.max_risk_level
        return PreflightCheckResult(
            check_name=self.name,
            status=PreflightCheckStatus.FAIL,
            description=(
                f"动作 {action} 风险等级 {assessment.risk_level.value} 越界阻断："
                f"{decision.reason}"
            ),
            evidence=decision.reason,
            details=details,
        )


# ---------------------------------------------------------------------------
# TaskPreflight — orchestrator
# ---------------------------------------------------------------------------


class TaskPreflight:
    """Task-level preflight orchestrator.

    Runs a battery of checks before a task is allowed to execute.
    Mirrors the preflight protocol described in OSS Execution Norm 1.1,
    upgraded to enforce task-level governance (Pre-flight 2.0).

    Usage:
        preflight = TaskPreflight()
        result = preflight.execute({
            "agent_id": "agent-01",
            "task_description": "Generate launch video",
            "readme_read": True,
            "readme_summary": "Project has video_producer.py...",
            "selected_pipeline": "video_producer",
            "pipeline_governor": my_governor,
            "git_log_consulted": True,
            "git_log_entries": 5,
            "alternatives_considered": ["produce_launch.js", "video_producer.py"],
            "alternatives_rationale": "video_producer.py is the official pipeline...",
            "decision_logged": True,
            "decision_log_location": "audit://20260716/launch-video",
        })
        if result.passed:
            # proceed with execution
        else:
            # show result.summary and blocked checks
    """

    def __init__(
        self,
        checks: list[PreflightCheck] | None = None,
    ) -> None:
        """Initialize with optional custom check list.

        Args:
            checks: Custom list of PreflightCheck instances.
                    Defaults to the standard 5 checks.
        """
        self._checks = checks if checks is not None else self._default_checks()

    @staticmethod
    def _default_checks() -> list[PreflightCheck]:
        """Standard preflight checks matching the audit findings."""
        return [
            ReadmeReadCheck(),
            PipelineSelectionCheck(),
            GitHistoryCheck(),
            AlternativesComparedCheck(),
            DecisionLoggedCheck(),
            RiskAuthorizationCheck(),
        ]

    def execute(self, context: dict[str, Any]) -> PreflightResult:
        """Run all preflight checks against the given context.

        Args:
            context: Dictionary with evidence from the agent's planning phase.
                     See class docstring for required/optional keys.

        Returns:
            PreflightResult with aggregated pass/fail status.
        """
        results = [check.execute(context) for check in self._checks]
        passed = all(r.status != PreflightCheckStatus.FAIL for r in results)

        result = PreflightResult(
            passed=passed,
            checks=results,
            agent_id=context.get("agent_id", "unknown"),
            task_description=context.get("task_description", ""),
            timestamp=time.time(),
        )

        if passed:
            logger.info(
                "TaskPreflight PASS: agent=%s task=%s",
                result.agent_id,
                result.task_description[:60],
            )
        else:
            failed = [c.check_name for c in result.failed_checks]
            logger.warning(
                "TaskPreflight FAIL: agent=%s task=%s failed=%s",
                result.agent_id,
                result.task_description[:60],
                failed,
            )

        return result

    @property
    def checks(self) -> list[PreflightCheck]:
        """Return the list of checks this preflight will run."""
        return list(self._checks)
