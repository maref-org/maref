"""端到端策略引擎集成测试

测试全链路：GovernancePipeline 8 步管线 + 审计回调 + 断路器回调 +
权限矩阵 + HITL 路由 + PipelineRegistry 选择治理。

对齐真实 API（core_pipeline.govern 的 8 步流程）：
  1. 断路器深度检查（cb_check_callback）
  2. 权限矩阵（role 角色访问）
  3-4. 策略规则评估（policy_rules 优先级降序）
  5. HITL 路由（ASK_USER → hitl_event_id）
  6. 审计回调
  7. 信任更新
  8. 断路器成功/失败记录
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from maref.governance import AuditLogger
from maref.governance.core_pipeline import GovernancePipeline, GovernanceRequest, GovernanceResult, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.pipeline_registry import (
    PipelineGovernor,
    PipelineRegistration,
    QualityTier,
)
from maref.integration.hitl import HITLTier
from maref.recursive.permission_matrix import PermissionMatrix


@pytest.fixture
def temp_audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


@pytest.fixture
def permission_matrix() -> PermissionMatrix:
    return PermissionMatrix()


@pytest.fixture
def audit_events() -> list[tuple[GovernanceRequest, GovernanceResult]]:
    return []


@pytest.fixture
def plain_pipeline(audit_events: list[tuple[GovernanceRequest, GovernanceResult]]) -> GovernancePipeline:
    def on_audit(req: GovernanceRequest, result: GovernanceResult) -> None:
        audit_events.append((req, result))

    return GovernancePipeline(audit_callback=on_audit)


class TestPipelineIntegration:
    """真实 API 的 8 步管线行为验证。"""

    def test_basic_allow_flow(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        )
        assert result.verdict == Verdict.ALLOW

    def test_dangerous_action_low_trust_asks_user(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=10)
        )
        assert result.verdict == Verdict.ASK_USER
        assert result.hitl_event_id, "ASK_USER 必须产生 HITL 事件"

    def test_dangerous_action_trusted_allowed(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=90)
        )
        assert result.verdict == Verdict.ALLOW

    def test_git_push_requires_human(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=95)
        )
        assert result.verdict == Verdict.ASK_USER
        assert result.hitl_tier == HITLTier.P0_RESPONSE

    def test_low_trust_denied(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=10)
        )
        assert result.verdict == Verdict.DENY
        assert "Trust score too low" in result.reason

    def test_high_recursion_asks_user(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="file.read", agent_id="agent-a", recursion_depth=10)
        )
        assert result.verdict == Verdict.ASK_USER
        assert "recursion" in result.reason.lower()

    def test_permission_matrix_denies_write(self, plain_pipeline: GovernancePipeline) -> None:
        # 角色「坎」禁止 write 工具 → 权限矩阵先于策略规则拒绝
        result = plain_pipeline.govern(
            GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=80, role="坎")
        )
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "permission_matrix"

    def test_unknown_action_default_allow(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="unknown.action.12345", agent_id="agent-a", trust_score=50)
        )
        assert result.verdict == Verdict.ALLOW

    def test_empty_action_handled(self, plain_pipeline: GovernancePipeline) -> None:
        result = plain_pipeline.govern(
            GovernanceRequest(action="", agent_id="agent-a", trust_score=50)
        )
        assert result.verdict is not None

    def test_audit_callback_invoked(
        self,
        plain_pipeline: GovernancePipeline,
        audit_events: list[tuple[GovernanceRequest, GovernanceResult]],
    ) -> None:
        plain_pipeline.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert len(audit_events) == 1
        req, result = audit_events[0]
        assert req.action == "file.read"
        assert result.verdict == Verdict.ALLOW

    def test_cb_open_blocks(self) -> None:
        def cb_check(_tenant: str, _agent: str, _action: str, _depth: int) -> bool:
            return False

        pipe = GovernancePipeline(cb_check_callback=cb_check)
        result = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=90))
        assert result.verdict == Verdict.DENY
        assert result.matched_rule == "circuit_breaker_depth"

    def test_cb_record_invoked(self) -> None:
        records: list[tuple[str, str, str, bool]] = []

        def cb_check(_tenant: str, _agent: str, _action: str, _depth: int) -> bool:
            return True

        def cb_record(tenant: str, agent: str, action: str, success: bool) -> None:
            records.append((tenant, agent, action, success))

        pipe = GovernancePipeline(cb_check_callback=cb_check, cb_record_callback=cb_record)
        pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert records, "断路器必须记录决策结果"
        assert records[-1][3] is True  # ALLOW → success=True

    def test_trust_callback_allow(self) -> None:
        updates: list[tuple[str, str, float, str]] = []

        def on_trust(tenant: str, agent: str, score: float, source: str) -> None:
            updates.append((tenant, agent, score, source))

        pipe = GovernancePipeline(trust_callback=on_trust)
        pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert updates, "ALLOW 必须触发信任更新"
        assert updates[-1][2] == 80.5  # +0.5

    def test_trust_callback_deny(self) -> None:
        updates: list[tuple[str, str, float, str]] = []

        def on_trust(tenant: str, agent: str, score: float, source: str) -> None:
            updates.append((tenant, agent, score, source))

        pipe = GovernancePipeline(trust_callback=on_trust)
        pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=10))
        assert updates, "DENY 必须触发信任更新"
        assert updates[-1][2] == 9.0  # -1.0

    def test_custom_policies_override_defaults(self) -> None:
        def block_git_push(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if "git.push" in req.action:
                return Verdict.DENY, "git push blocked by custom policy", None
            return Verdict.ALLOW, "", None

        pipe = GovernancePipeline(policy_rules=[(100, block_git_push)])
        result = pipe.govern(
            GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=95)
        )
        assert result.verdict == Verdict.DENY
        assert "custom policy" in result.reason

    def test_multiple_policies_priority(self) -> None:
        def high_priority_block(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            if req.trust_score < 50:
                return Verdict.DENY, "low trust blocked by high-priority rule", None
            return Verdict.ALLOW, "", None

        def low_priority_allow(req: GovernanceRequest) -> tuple[Verdict, str, HITLTier | None]:
            return Verdict.ALLOW, "allow by low-priority rule", None

        pipe = GovernancePipeline(
            policy_rules=[
                (200, high_priority_block),
                (10, low_priority_allow),
            ],
        )
        result_low = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=30))
        assert result_low.verdict == Verdict.DENY
        result_high = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert result_high.verdict == Verdict.ALLOW

    def test_pipeline_timing(self) -> None:
        pipe = GovernancePipeline()
        start = time.perf_counter()
        for _ in range(100):
            pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a"))
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0

    def test_permission_matrix_custom_role(self, permission_matrix: PermissionMatrix) -> None:
        entry = permission_matrix.get_permissions("坎")
        assert entry is not None
        assert entry.role == "坎"
        assert entry.max_entropy >= 0

    def test_pipeline_with_permission_matrix(self, permission_matrix: PermissionMatrix) -> None:
        pipe = GovernancePipeline(permission=permission_matrix)
        result = pipe.govern(
            GovernanceRequest(
                action="file.write",
                agent_id="agent-a",
                trust_score=80,
                role="坎",
            )
        )
        assert result.verdict is not None
        assert result.verdict == Verdict.DENY  # 坎 禁止 write

    def test_pipeline_registry_quality_tier(self) -> None:
        governor = PipelineGovernor()
        governor.register(
            PipelineRegistration(
                pipeline_id="test-pipe",
                name="test",
                entry_point="test.py",
                description="test pipeline",
                quality_tier=QualityTier.OFFICIAL,
                verified=True,
            )
        )
        verdict, _reason, _hitl = governor.validate_selection("test-pipe")
        assert verdict == Verdict.ALLOW

    def test_pipeline_registry_deprecated_blocks(self) -> None:
        governor = PipelineGovernor()
        governor.register(
            PipelineRegistration(
                pipeline_id="deprecated-pipe",
                name="deprecated",
                entry_point="deprecated.py",
                description="deprecated pipeline",
                quality_tier=QualityTier.DEPRECATED,
            )
        )
        verdict, _reason, _hitl = governor.validate_selection("deprecated-pipe")
        assert verdict == Verdict.DENY

    def test_pipeline_registry_unregistered_asks(self) -> None:
        governor = PipelineGovernor()
        verdict, reason, _hitl = governor.validate_selection("never-registered")
        assert verdict == Verdict.ASK_USER
        assert "not registered" in reason


class TestGovernedPipeline:
    """Batteries-included 组装（审计 + HITL + 权限 + 断路器池 + 管线）。"""

    def test_full_governed_pipeline_assembly(self, temp_audit_path: Path) -> None:
        gp = GovernedPipeline(audit_path=str(temp_audit_path))
        result = gp.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert result.verdict == Verdict.ALLOW

    def test_governed_pipeline_git_push_asks_user(self, temp_audit_path: Path) -> None:
        gp = GovernedPipeline(audit_path=str(temp_audit_path))
        result = gp.govern(GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=95))
        assert result.verdict == Verdict.ASK_USER
        assert result.hitl_event_id

    def test_governed_pipeline_writes_audit(self, temp_audit_path: Path) -> None:
        gp = GovernedPipeline(audit_path=str(temp_audit_path))
        gp.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        entries = list(gp.audit.read_all())
        assert entries, "治理决策必须写入审计日志"
        entry = entries[-1]
        sig = entry.ed25519_signature or entry.hmac_signature
        assert sig, "审计条目必须带签名"
        assert entry.chain_hash, "审计条目必须带链哈希"
        assert gp.audit.verify_integrity()["integrity_intact"] is True


class TestAuditLoggerIntegration:
    """独立 AuditLogger + 断言（沿用旧测试意图）。"""

    def test_audit_logger_writes_signed_entries(self, temp_audit_path: Path) -> None:
        logger = AuditLogger(log_path=str(temp_audit_path))
        logger.log_decision(
            event_type="decision",
            actor="agent-a",
            action="file.read",
            details="allow",
        )
        entries = list(logger.read_all())
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry.event_type == "governance_decision"
        sig = entry.ed25519_signature or entry.hmac_signature
        assert sig
        assert logger.verify_integrity()["integrity_intact"] is True

    def test_audit_chain_tamper_detected(self, temp_audit_path: Path) -> None:
        logger = AuditLogger(log_path=str(temp_audit_path))
        logger.log_decision(actor="agent-a", action="file.read", reason="allow")
        logger.log_decision(actor="agent-a", action="file.write", reason="deny")
        # 篡改中间条目
        lines = temp_audit_path.read_text().strip().split("\n")
        import json

        entry = json.loads(lines[0])
        entry["details"] = "tampered"
        lines[0] = json.dumps(entry)
        temp_audit_path.write_text("\n".join(lines) + "\n")
        assert logger.verify_integrity()["integrity_intact"] is False
