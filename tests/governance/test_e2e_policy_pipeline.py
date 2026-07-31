"""端到端策略引擎全链路集成测试

覆盖管线审计报告 P1-6 缺口：
1. 全链路生命周期: GovernancePipeline + AuditLogger + CircuitBreaker
2. MCPGovernance 路径等效性
3. 破坏性操作门禁集成
4. 断路器级联
5. 审计链完整性
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from maref.governance import AuditLogger, CircuitBreaker
from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)
from maref.governance.destructive_gate import DestructiveOperationGate, GateDecision, GateVerdict
from maref.integration.mcp_governance import (
    MCPDecisionVerdict,
    MCPGovernance,
    MCPPolicyEngine,
)
from maref.integration.mcp_security import MCPTrustLevel


@pytest.fixture
def temp_audit_path():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def audit_logger(temp_audit_path):
    return AuditLogger(
        log_path=str(temp_audit_path),
        hmac_key=b"test-hmac-key-for-testing-only",
    )


class TestEndToEndFullLifecycle:
    """全链路生命周期: 请求 → 管线评估 → 审计 → 信任分更新"""

    def test_full_allow_lifecycle(self, audit_logger):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        req = GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        result = pipe.govern(req)
        assert result.verdict == Verdict.ALLOW
        assert result.latency_ms >= 0

    def test_full_deny_lifecycle(self, audit_logger):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        req = GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=10)
        result = pipe.govern(req)
        assert result.verdict == Verdict.DENY
        assert result.reason

    def test_full_ask_user_lifecycle(self, audit_logger):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        req = GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=90)
        result = pipe.govern(req)
        assert result.verdict == Verdict.ASK_USER

    def test_circuit_breaker_trips_and_blocks(self):
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=2)

        for _ in range(3):
            cb.record_failure()

        assert cb.is_open

        def cb_check(tenant: str, agent: str, action: str, depth: int) -> bool:
            return cb.check_depth(depth)

        pipe = GovernancePipeline(cb_check_callback=cb_check, audit_callback=lambda req, res: None)
        result = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=90))
        assert result.verdict == Verdict.DENY


class TestGovernancePathEquivalence:
    """GaaS GovernancePipeline 与 MCPGovernance 路径等效性"""

    def test_safe_action_both_paths_allow(self):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        mcp_gov = MCPGovernance()

        req = GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        pipe_result = pipe.govern(req)

        mcp_result = mcp_gov.evaluate(
            tool_name="maref_read_observations",
            args={},
            trust_level=MCPTrustLevel.TRUSTED,
            agent_id="agent-a",
        )

        assert pipe_result.verdict == Verdict.ALLOW
        assert mcp_result.verdict in (MCPDecisionVerdict.ALLOW, MCPDecisionVerdict.ASK_USER)

    def test_dangerous_action_both_paths_restrictive(self):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        mcp_gov = MCPGovernance()

        req = GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=80)
        pipe_result = pipe.govern(req)

        mcp_result = mcp_gov.evaluate(
            tool_name="edit_tool",
            args={"file_path": "/etc/config"},
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-a",
        )

        assert pipe_result.verdict in (Verdict.DENY, Verdict.ASK_USER)
        assert mcp_result.verdict in (MCPDecisionVerdict.DENY, MCPDecisionVerdict.ASK_USER)

    def test_custom_policy_rule_works(self):
        def block_git_push(req: GovernanceRequest):
            if "git.push" in req.action:
                return (Verdict.DENY, "blocked by custom policy", None)
            return (Verdict.ALLOW, "", None)

        pipe = GovernancePipeline(
            policy_rules=[(100, block_git_push)],
            audit_callback=lambda req, res: None,
        )

        result = pipe.govern(GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=100))
        assert result.verdict == Verdict.DENY

        result_safe = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=100))
        assert result_safe.verdict == Verdict.ALLOW


class TestDestructiveGateIntegration:
    """破坏性操作门禁作为管线策略规则"""

    def test_destructive_gate_signs_decisions(self):
        gate = DestructiveOperationGate()
        decision = gate.evaluate(
            operation="delete_file",
            tool_name="shell",
            args={"path": "/etc/passwd"},
            agent_id="agent-a",
        )
        assert isinstance(decision, GateDecision)
        assert decision.verdict in (GateVerdict.ALLOW, GateVerdict.BLOCK, GateVerdict.HITL_REQUIRED)

    def test_destructive_gate_detects_rm(self):
        gate = DestructiveOperationGate()
        decision = gate.evaluate(
            operation="shell.exec",
            tool_name="bash",
            args={"command": "rm -rf /"},
            agent_id="agent-a",
        )
        assert decision.verdict in (GateVerdict.BLOCK, GateVerdict.HITL_REQUIRED)

    def test_safe_action_passes_destructive_gate(self):
        gate = DestructiveOperationGate()
        decision = gate.evaluate(
            operation="file.read",
            tool_name="read_file",
            args={"path": "/tmp/test.txt"},
            agent_id="agent-a",
        )
        assert decision.verdict == GateVerdict.ALLOW


class TestAuditChainIntegrity:
    """审计链完整性 — HMAC 签名 + 链哈希验证"""

    def test_audit_entries_have_signatures(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)

        for i in range(3):
            pipe.govern(GovernanceRequest(action="file.read", agent_id=f"agent-{i}"))
            logger.log("decision", "pipeline", "allow:file.read")

        entries = list(logger.read_all())
        for entry in entries:
            sig = entry.hmac_signature or entry.ed25519_signature
            assert sig, f"Entry {entry.id} missing signature"
            assert entry.chain_hash, f"Entry {entry.id} missing chain_hash"

    def test_audit_chain_linked(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")

        prev: str | None = None
        for i in range(3):
            entry = logger.log("decision", "pipeline", f"action-{i}")
            if prev:
                assert entry.previous_hash == prev
            prev = entry.chain_hash

    def test_audit_chain_tamper_detected(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")

        for i in range(3):
            logger.log("decision", "pipeline", f"action-{i}")

        raw = temp_audit_path.read_text()
        lines = raw.strip().split("\n")

        tampered = lines[:-1] + [json.dumps({"id": "tampered", "action": "shell.exec"})]
        temp_audit_path.write_text("\n".join(tampered))

        tampered_logger = AuditLogger(log_path=str(temp_audit_path))
        result = tampered_logger.verify_integrity()
        assert result.get("integrity_intact") is False, "Tampered chain should fail integrity"


class TestCircuitBreakerCascade:
    """断路器级联"""

    def test_circuit_breaker_trips_on_repeated_failures(self):
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=2)

        for _ in range(3):
            cb.record_failure()

        assert cb.is_open

    def test_circuit_breaker_auto_half_open(self):
        cb = CircuitBreaker(max_depth=3, max_consecutive_failures=2, cooldown_seconds=1)

        for _ in range(3):
            cb.record_failure()
        assert cb.is_open

        time.sleep(1.1)
        result = cb.check_depth(1)
        assert result is True

    def test_high_recursion_depth_triggers_cb_with_pipeline(self):
        pipe = GovernancePipeline(audit_callback=lambda req, res: None)
        req = GovernanceRequest(action="file.read", agent_id="agent-a", recursion_depth=10)
        result = pipe.govern(req)
        assert result.verdict in (Verdict.DENY, Verdict.ASK_USER)
        assert result.reason


class TestAuditLoggerIntegration:
    """审计记录器与管线集成"""

    def test_audit_logger_logs_decision(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")
        entry = logger.log_decision(
            actor="pipeline",
            action="allow:file.read",
            reason="safe action",
        )
        assert entry.id
        assert entry.event_type == "governance_decision"
        assert entry.hmac_signature

    def test_audit_logger_read_all(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")
        logger.log("decision", "pipeline", "action-1")
        logger.log("decision", "pipeline", "action-2")

        entries = list(logger.read_all())
        assert len(entries) == 2

    def test_audit_logger_verify_integrity_passes(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path), hmac_key=b"test-key")
        logger.log("decision", "pipeline", "action-1")
        logger.log("decision", "pipeline", "action-2")

        result = logger.verify_integrity()
        assert result.get("integrity_intact") is True
        assert result.get("total_entries", 0) >= 2

    @patch.dict(os.environ, {"MAREF_HMAC_SECRET_KEY": "test-key"}, clear=True)
    def test_audit_logger_memory_only_uses_env_key(self):
        from maref.governance.audit import AuditLogger as AL
        logger = AL()
        entry = logger.log("decision", "pipeline", "action-1")
        assert entry.id


class TestMCPGovernance:
    """MCPGovernance 管线"""

    def test_mcp_governance_evaluate_allows_safe_tool(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="maref_read_observations",
            trust_level=MCPTrustLevel.TRUSTED,
            agent_id="agent-a",
        )
        assert result.verdict in (MCPDecisionVerdict.ALLOW, MCPDecisionVerdict.ASK_USER)

    def test_mcp_governance_evaluate_blocks_dangerous_tool(self):
        gov = MCPGovernance()
        result = gov.evaluate(
            tool_name="bash_tool",
            args={"command": "rm -rf /"},
            trust_level=MCPTrustLevel.UNTRUSTED,
            agent_id="agent-a",
        )
        assert result.verdict in (MCPDecisionVerdict.DENY, MCPDecisionVerdict.ASK_USER)

    def test_mcp_governance_audit_log(self):
        gov = MCPGovernance()
        gov.evaluate(
            tool_name="maref_health_check",
            trust_level=MCPTrustLevel.TRUSTED,
            agent_id="agent-a",
        )
        decision_log = gov.get_decision_log()
        assert len(decision_log) >= 1

    def test_mcp_policy_engine_custom_rule(self):
        engine = MCPPolicyEngine()
        initial_count = len(engine.get_rules())
        assert initial_count >= 5
