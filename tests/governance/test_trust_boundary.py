"""TrustBoundaryManager — 单 Agent 权限边界强制实施层（v0.44.0 S1）。"""

from __future__ import annotations

import pytest

from maref.exceptions import ErrorCode
from maref.governance.trust_boundary import (
    BoundaryViolationError,
    TrustBoundaryManager,
)
from maref.identity.credential import AuthorizationScope


class TestTrustBoundaryLowRisk:
    def test_low_risk_auto_allow(self) -> None:
        boundary = TrustBoundaryManager()
        decision = boundary.check("file.read", agent_id="agent-01")
        assert decision.allowed is True
        assert decision.assessment.risk_level.value == "LOW"

    def test_medium_risk_auto_allow_without_scope(self) -> None:
        boundary = TrustBoundaryManager()
        decision = boundary.check("file.write", agent_id="agent-01")
        assert decision.allowed is True
        assert decision.assessment.risk_level.value == "MEDIUM"


class TestTrustBoundaryFailClosed:
    def test_high_risk_no_scope_fail_closed(self) -> None:
        boundary = TrustBoundaryManager()
        with pytest.raises(BoundaryViolationError) as excinfo:
            boundary.check("deploy:app", agent_id="agent-01")
        assert excinfo.value.code == ErrorCode.BOUNDARY_VIOLATION
        assert excinfo.value.http_status == 403
        assert "fail-closed" in excinfo.value.details["reason"]

    def test_irreversible_no_scope_fail_closed(self) -> None:
        boundary = TrustBoundaryManager()
        with pytest.raises(BoundaryViolationError):
            boundary.check("payment:transfer", agent_id="agent-01")

    def test_fail_closed_false_allows_high_risk(self) -> None:
        boundary = TrustBoundaryManager(fail_closed=False)
        decision = boundary.check("deploy:app", agent_id="agent-01")
        assert decision.allowed is True


class TestTrustBoundaryScope:
    def test_in_scope_high_risk_allowed(self) -> None:
        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
        )
        boundary = TrustBoundaryManager(scope=scope)
        decision = boundary.check("network:medical_record", agent_id="agent-01")
        assert decision.allowed is True

    def test_out_of_scope_high_risk_blocked(self) -> None:
        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent-01",
            max_risk_level="MEDIUM",
            allowed_actions=["network:medical_record"],
        )
        boundary = TrustBoundaryManager(scope=scope)
        with pytest.raises(BoundaryViolationError) as excinfo:
            boundary.check("payment:transfer", agent_id="agent-01")
        assert "超出授权范围" in excinfo.value.details["reason"]

    def test_expired_scope_blocked(self) -> None:
        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            ttl_seconds=1,
        )
        scope.valid_until = 0.0
        boundary = TrustBoundaryManager(scope=scope)
        with pytest.raises(BoundaryViolationError) as excinfo:
            boundary.check("deploy:app", agent_id="agent-01")
        assert "已过期" in excinfo.value.details["reason"]


class TestTrustBoundaryDomains:
    def test_unallowed_impact_scope_blocked(self) -> None:
        boundary = TrustBoundaryManager()
        with pytest.raises(BoundaryViolationError) as excinfo:
            boundary.check(
                "file.read",
                agent_id="agent-01",
                metadata={"impact_scope": "cross_org"},
            )
        assert "允许域" in excinfo.value.details["reason"]

    def test_custom_allowed_domains(self) -> None:
        scope = AuthorizationScope.issue(
            subject_did="did:maref:agent-01",
            max_risk_level="HIGH",
            allowed_actions=["network:medical_record"],
        )
        boundary = TrustBoundaryManager(
            allowed_domains={"local", "cross_org"},
            scope=scope,
        )
        decision = boundary.check_no_raise(
            "network:medical_record",
            agent_id="agent-01",
            metadata={"impact_scope": "cross_org"},
        )
        assert decision.allowed is True


class TestTrustBoundaryCheckNoRaise:
    def test_check_no_raise_returns_blocked_decision(self) -> None:
        boundary = TrustBoundaryManager()
        decision = boundary.check_no_raise("payment:transfer", agent_id="agent-01")
        assert decision.allowed is False
        assert decision.reason != ""

    def test_check_no_raise_does_not_raise(self) -> None:
        boundary = TrustBoundaryManager()
        boundary.check_no_raise("deploy:app", agent_id="agent-01")
        boundary.check_no_raise("file.read", agent_id="agent-01")
        assert boundary.blocked_count() == 1


class TestTrustBoundaryAudit:
    def test_audit_logger_receives_blocked_event(self) -> None:
        class FakeAudit:
            def __init__(self) -> None:
                self.entries: list[dict] = []

            def append(self, entry: dict) -> None:
                self.entries.append(entry)

        audit = FakeAudit()
        boundary = TrustBoundaryManager(audit_logger=audit)
        with pytest.raises(BoundaryViolationError):
            boundary.check("payment:transfer", agent_id="agent-01")
        assert len(audit.entries) == 1
        assert audit.entries[0]["event_type"] == "trust_boundary_check"
        assert audit.entries[0]["outcome"] == "blocked"

    def test_audit_logger_receives_allowed_event(self) -> None:
        class FakeAudit:
            def __init__(self) -> None:
                self.entries: list[dict] = []

            def append(self, entry: dict) -> None:
                self.entries.append(entry)

        audit = FakeAudit()
        boundary = TrustBoundaryManager(audit_logger=audit)
        boundary.check("file.read", agent_id="agent-01")
        assert audit.entries[0]["outcome"] == "allowed"

    def test_broken_audit_logger_does_not_break_check(self) -> None:
        class BrokenAudit:
            def append(self, entry: dict) -> None:
                raise RuntimeError("audit down")

        boundary = TrustBoundaryManager(audit_logger=BrokenAudit())
        decision = boundary.check("file.read", agent_id="agent-01")
        assert decision.allowed is True


class TestTrustBoundaryDecisionHistory:
    def test_decisions_history_and_blocked_count(self) -> None:
        boundary = TrustBoundaryManager()
        boundary.check("file.read", agent_id="agent-01")
        boundary.check_no_raise("deploy:app", agent_id="agent-01")
        assert len(boundary.decisions) == 2
        assert boundary.blocked_count() == 1
        assert len(boundary.recent_decisions(limit=1)) == 1

    def test_decision_to_dict(self) -> None:
        boundary = TrustBoundaryManager()
        decision = boundary.check("file.read", agent_id="agent-01")
        d = decision.to_dict()
        assert d["action"] == "file.read"
        assert d["allowed"] is True
        assert d["risk_level"] == "LOW"
