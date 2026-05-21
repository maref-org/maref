from __future__ import annotations

import pytest

from maref.security.trust_boundary import (
    TrustBoundaryManager,
    TrustDomain,
    TrustPolicy,
    BoundaryEventType,
    BoundaryReport,
)


class TestTrustDomain:
    def test_create_domain(self):
        domain = TrustDomain(name="test-domain", policy=TrustPolicy.STRICT)
        assert domain.name == "test-domain"
        assert domain.policy == TrustPolicy.STRICT

    def test_add_remove_agents(self):
        domain = TrustDomain(name="test-domain")
        domain.add_agent("agent-001")
        assert domain.contains_agent("agent-001")
        domain.remove_agent("agent-001")
        assert not domain.contains_agent("agent-001")


class TestTrustBoundaryManager:
    def test_create_and_register(self):
        manager = TrustBoundaryManager()
        domain = manager.create_domain("domain-a", TrustPolicy.STRICT)
        result = manager.register_agent("agent-001", domain.domain_id)
        assert result is True
        assert manager.get_agent_domain("agent-001") == domain.domain_id

    def test_register_invalid_domain(self):
        manager = TrustBoundaryManager()
        result = manager.register_agent("agent-001", "invalid-domain")
        assert result is False

    def test_cross_domain_detection(self):
        manager = TrustBoundaryManager()
        domain_a = manager.create_domain("domain-a")
        domain_b = manager.create_domain("domain-b")

        manager.register_agent("agent-a1", domain_a.domain_id)
        manager.register_agent("agent-b1", domain_b.domain_id)

        event = manager.check_cross_domain("agent-a1", "agent-b1")
        assert event is not None
        assert event.event_type == BoundaryEventType.CROSS_DOMAIN_CALL
        assert event.source_domain == domain_a.domain_id
        assert event.target_domain == domain_b.domain_id

    def test_same_domain_no_event(self):
        manager = TrustBoundaryManager()
        domain = manager.create_domain("same-domain")
        manager.register_agent("agent-001", domain.domain_id)
        manager.register_agent("agent-002", domain.domain_id)

        event = manager.check_cross_domain("agent-001", "agent-002")
        assert event is None

    def test_boundary_report_generation(self):
        manager = TrustBoundaryManager()
        domain_a = manager.create_domain("domain-a")
        domain_b = manager.create_domain("domain-b")

        manager.register_agent("agent-a1", domain_a.domain_id)
        manager.register_agent("agent-b1", domain_b.domain_id)

        manager.check_cross_domain("agent-a1", "agent-b1")
        manager.check_cross_domain("agent-a1", "agent-b1")

        report = manager.generate_report(domain_a.domain_id, domain_b.domain_id)
        assert report.total_crossings == 2
        assert report.source_domain == domain_a.domain_id


class TestBoundaryReport:
    def test_add_event(self):
        from maref.security.trust_boundary import BoundaryEvent

        report = BoundaryReport(source_domain="dom-1", target_domain="dom-2")
        event = BoundaryEvent(agent_id="agent-001", risk_score=0.8)
        report.add_event(event)
        assert report.total_crossings == 1
        assert report.high_risk_count == 1
        assert report.reverification_required == 1


class TestA2Assertions:
    """A2: 信任边界强制执行"""

    def test_strict_to_permissive_risk_score_at_least_0_6(self):
        manager = TrustBoundaryManager()
        strict = manager.create_domain("strict", TrustPolicy.STRICT)
        perm = manager.create_domain("perm", TrustPolicy.PERMISSIVE)
        manager.register_agent("agent-s", strict.domain_id)
        manager.register_agent("agent-p", perm.domain_id)

        event = manager.check_cross_domain("agent-s", "agent-p")
        assert event is not None
        assert event.risk_score >= 0.6

    def test_moderate_to_moderate_risk_score_lower(self):
        manager = TrustBoundaryManager()
        mod_a = manager.create_domain("mod-a", TrustPolicy.MODERATE)
        mod_b = manager.create_domain("mod-b", TrustPolicy.MODERATE)
        manager.register_agent("agent-a", mod_a.domain_id)
        manager.register_agent("agent-b", mod_b.domain_id)

        event = manager.check_cross_domain("agent-a", "agent-b")
        assert event is not None
        assert event.risk_score < 0.6

    def test_audit_logger_records_cross_domain(self, tmp_path):
        from maref.governance.audit import AuditLogger

        audit = AuditLogger(tmp_path / "audit.jsonl")
        manager = TrustBoundaryManager(audit_logger=audit)
        dom_a = manager.create_domain("a")
        dom_b = manager.create_domain("b")
        manager.register_agent("agent-a", dom_a.domain_id)
        manager.register_agent("agent-b", dom_b.domain_id)

        manager.check_cross_domain("agent-a", "agent-b")
        entries = audit.read_all()
        assert len(entries) >= 1
        assert entries[0].event_type == "cross_domain_call"
        assert "risk_score" in entries[0].metadata

    def test_circuit_breaker_records_high_risk(self, tmp_path):
        from maref.governance.audit import AuditLogger
        from maref.governance.circuit_breaker import CircuitBreaker

        audit = AuditLogger(tmp_path / "audit.jsonl")
        cb = CircuitBreaker(max_consecutive_failures=3)
        manager = TrustBoundaryManager(audit_logger=audit, circuit_breaker=cb)
        strict = manager.create_domain("strict", TrustPolicy.STRICT)
        perm = manager.create_domain("perm", TrustPolicy.PERMISSIVE)
        manager.register_agent("agent-s", strict.domain_id)
        manager.register_agent("agent-p", perm.domain_id)

        # 3 high-risk calls should trip the breaker
        for _ in range(3):
            manager.check_cross_domain("agent-s", "agent-p")

        assert cb.is_open

    def test_no_audit_or_cb_when_not_configured(self):
        manager = TrustBoundaryManager()
        dom_a = manager.create_domain("a")
        dom_b = manager.create_domain("b")
        manager.register_agent("agent-a", dom_a.domain_id)
        manager.register_agent("agent-b", dom_b.domain_id)

        # Should not raise even without audit_logger or circuit_breaker
        event = manager.check_cross_domain("agent-a", "agent-b")
        assert event is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])