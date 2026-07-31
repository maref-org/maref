"""端到端策略引擎集成测试

测试全链路：GovernancePipeline + AuditLogger + CircuitBreaker + PermissionMatrix
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from maref.governance import AuditLogger, CircuitBreaker, GovernanceStateMachine
from maref.governance.core_pipeline import GovernancePipeline, GovernanceRequest, Verdict
from maref.governance.governed_pipeline import GovernedPipeline
from maref.governance.pipeline_registry import PipelineGovernor, PipelineRegistry, QualityTier
from maref.recursive.permission_matrix import IChingRole, PermissionMatrix


@pytest.fixture
def temp_audit_path():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def audit_logger(temp_audit_path):
    return AuditLogger(log_path=str(temp_audit_path))


@pytest.fixture
def circuit_breaker():
    return CircuitBreaker(max_depth=3)


@pytest.fixture
def state_machine():
    return GovernanceStateMachine()


@pytest.fixture
def permission_matrix():
    return PermissionMatrix()


class TestPipelineIntegration:
    def test_basic_allow_flow(self, audit_logger, circuit_breaker):
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=circuit_breaker)
        req = GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        result = pipe.govern(req)
        assert result.verdict == Verdict.ALLOW

    def test_basic_deny_flow(self, audit_logger, circuit_breaker):
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=circuit_breaker)
        req = GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=10)
        result = pipe.govern(req)
        assert result.verdict == Verdict.DENY

    def test_ask_user_flow(self, audit_logger, circuit_breaker):
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=circuit_breaker)
        req = GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=50)
        result = pipe.govern(req)
        assert result.verdict == Verdict.ASK_USER

    def test_audit_logger_integration(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path))
        pipe = GovernancePipeline(audit_logger=logger)
        pipe.govern(GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=80))
        entries = list(logger.read_all())
        assert len(entries) >= 1
        entry = entries[-1]
        assert entry.event_type == "decision"
        assert "ALLOW" in entry.details or "allow" in entry.details.lower()

    def test_circuit_breaker_records_failures(self, audit_logger):
        cb = CircuitBreaker(max_depth=3)
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=cb)
        for _ in range(5):
            pipe.govern(GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=10))
        assert cb.state_name == "OPEN"

    def test_circuit_breaker_blocks_when_open(self, audit_logger):
        cb = CircuitBreaker(max_depth=2)
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=cb)
        for _ in range(3):
            pipe.govern(GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=10))
        assert cb.is_open
        result = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=90))
        assert result.verdict == Verdict.DENY

    def test_custom_policies_override_defaults(self, audit_logger):
        def block_git_push(req):
            if "git.push" in req.action:
                return (Verdict.DENY, "git push blocked by custom policy", None)
            return (Verdict.ALLOW, "", None)

        pipe = GovernancePipeline(
            audit_logger=audit_logger,
            policy_rules=[(100, block_git_push)],
        )
        req = GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=95)
        result = pipe.govern(req)
        assert result.verdict == Verdict.DENY

    def test_multiple_policies_priority(self, audit_logger):
        def high_priority_block(req):
            if req.trust_score < 50:
                return (Verdict.DENY, "low trust blocked by high-priority rule", None)
            return None

        def low_priority_allow(req):
            return (Verdict.ALLOW, "allow by low-priority rule", None)

        pipe = GovernancePipeline(
            audit_logger=audit_logger,
            policy_rules=[
                (200, high_priority_block),
                (10, low_priority_allow),
            ],
        )
        result_low = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=30))
        assert result_low.verdict == Verdict.DENY
        result_high = pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80))
        assert result_high.verdict == Verdict.ALLOW

    def test_permission_matrix_custom_role(self, permission_matrix):
        pm = permission_matrix
        role = pm.get_role("kan")
        assert role is not None
        assert role.role is IChingRole.KAN
        assert role.max_recursion_depth > 0

    def test_pipeline_with_permission_matrix(self, audit_logger, permission_matrix):
        pipe = GovernancePipeline(
            audit_logger=audit_logger,
            permission_matrix=permission_matrix,
        )
        req = GovernanceRequest(
            action="file.write",
            agent_id="agent-a",
            trust_score=80,
            metadata={"role": "kan"},
        )
        result = pipe.govern(req)
        assert result.verdict is not None

    def test_pipeline_timing(self, audit_logger):
        import time
        pipe = GovernancePipeline(audit_logger=audit_logger)
        start = time.perf_counter()
        for _ in range(100):
            pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a"))
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0

    def test_high_recursion_depth(self, audit_logger, circuit_breaker):
        pipe = GovernancePipeline(audit_logger=audit_logger, circuit_breaker=circuit_breaker)
        req = GovernanceRequest(action="file.read", agent_id="agent-a", recursion_depth=10)
        result = pipe.govern(req)
        assert result.verdict in (Verdict.DENY, Verdict.ASK_USER)

    def test_full_governed_pipeline_assembly(self, temp_audit_path):
        gp = GovernedPipeline(audit_log_path=str(temp_audit_path))
        req = GovernanceRequest(action="file.read", agent_id="agent-a", trust_score=80)
        result = gp.govern(req)
        assert result.verdict == Verdict.ALLOW

    def test_pipeline_registry_quality_tier(self):
        registry = PipelineRegistry()
        pipe = GovernancePipeline()
        registry.register("test-pipe", pipe, tier=QualityTier.OFFICIAL)
        governor = PipelineGovernor(registry)
        result = governor.validate_selection("test-pipe")
        assert result.allowed is True

    def test_pipeline_registry_deprecated_blocks(self):
        registry = PipelineRegistry()
        pipe = GovernancePipeline()
        registry.register("deprecated-pipe", pipe, tier=QualityTier.DEPRECATED)
        governor = PipelineGovernor(registry)
        result = governor.validate_selection("deprecated-pipe")
        assert result.allowed is False

    def test_pipeline_agent_id_isolation(self, audit_logger):
        pipe = GovernancePipeline(audit_logger=audit_logger)
        req_a = GovernanceRequest(action="shell.exec", agent_id="agent-a", trust_score=90)
        req_b = GovernanceRequest(action="shell.exec", agent_id="agent-b", trust_score=10)
        result_a = pipe.govern(req_a)
        result_b = pipe.govern(req_b)
        assert result_a.verdict == Verdict.ALLOW
        assert result_b.verdict == Verdict.DENY

    def test_hitl_decision_routing(self, audit_logger):
        pipe = GovernancePipeline(audit_logger=audit_logger)
        req = GovernanceRequest(action="git.push", agent_id="agent-a", trust_score=90)
        result = pipe.govern(req)
        assert result.verdict == Verdict.ASK_USER
        assert result.needs_human is True

    def test_empty_action_handling(self, audit_logger):
        pipe = GovernancePipeline(audit_logger=audit_logger)
        req = GovernanceRequest(action="", agent_id="agent-a")
        result = pipe.govern(req)
        assert result.verdict is not None

    def test_unknown_action_handling(self, audit_logger):
        pipe = GovernancePipeline(audit_logger=audit_logger)
        req = GovernanceRequest(action="unknown.action.12345", agent_id="agent-a", trust_score=50)
        result = pipe.govern(req)
        assert result.verdict in (Verdict.ALLOW, Verdict.ASK_USER)

    @pytest.mark.parametrize("score,expected", [
        (100, Verdict.ALLOW),
        (70, Verdict.ALLOW),
        (50, Verdict.ASK_USER),
        (30, Verdict.ASK_USER),
        (10, Verdict.DENY),
    ])
    def test_trust_score_thresholds(self, audit_logger, score, expected):
        pipe = GovernancePipeline(audit_logger=audit_logger)
        req = GovernanceRequest(action="file.write", agent_id="agent-a", trust_score=score)
        result = pipe.govern(req)
        assert result.verdict == expected

    def test_audit_entries_have_signatures(self, temp_audit_path):
        logger = AuditLogger(log_path=str(temp_audit_path))
        pipe = GovernancePipeline(audit_logger=logger)
        pipe.govern(GovernanceRequest(action="file.read", agent_id="agent-a"))
        raw = temp_audit_path.read_text()
        lines = [l for l in raw.strip().split("\n") if l]
        for line in lines[-3:]:
            entry = json.loads(line)
            sig = entry.get("ed25519_signature") or entry.get("hmac_signature")
            assert sig, f"Entry {entry.get('id')} missing signature"
            assert entry.get("chain_hash"), f"Entry {entry.get('id')} missing chain_hash"
