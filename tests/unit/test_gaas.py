"""Unit tests for MAREF GaaS (Governance-as-a-Service) core modules.

Covers: TenantManager, CircuitBreakerPool, AuditLogService, TrustScoreService,
HITLService, GovernanceRouter, BillingService.
"""

from __future__ import annotations

import os
import time

import pytest

from maref.gaas.audit_service import AuditLogService
from maref.gaas.billing import BillingService
from maref.gaas.cb_pool import CircuitBreakerPool
from maref.gaas.governance_router import GovernanceRouter
from maref.gaas.models import (
    CircuitBreakerState,
    GovernanceContext,
    GovernRequest,
    Verdict,
)
from maref.gaas.models import (
    HITLTier as ModelHITLTier,
)
from maref.gaas.tenant import Tenant, TenantManager
from maref.gaas.trust_service import TrustScoreService
from maref.integration.hitl import HITLRouter, HITLStatus

# ------------------------------------------------------------------
# TenantManager
# ------------------------------------------------------------------


class TestTenantManager:
    def test_register_and_get(self) -> None:
        tm = TenantManager()
        t = Tenant(tenant_id="t1", name="Test")
        key = tm.register(t)
        assert key.startswith("mk_")
        assert tm.get_by_id("t1") is not None
        assert tm.get_by_api_key(key) is not None

    def test_duplicate_register_raises(self) -> None:
        tm = TenantManager()
        t = Tenant(tenant_id="t1", name="Test")
        tm.register(t)
        with pytest.raises(ValueError):
            tm.register(Tenant(tenant_id="t1", name="Test2"))

    def test_quota_check(self) -> None:
        tm = TenantManager()
        t = Tenant(tenant_id="t1", name="Test", tier="free")
        tm.register(t)
        assert tm.check_quota("t1", "max_agents", 0) is True
        assert tm.check_quota("t1", "max_agents", 1) is False
        assert tm.check_quota("t1", "max_agents", 999) is False

    def test_enterprise_unlimited_quota(self) -> None:
        tm = TenantManager()
        t = Tenant(tenant_id="t1", name="Test", tier="enterprise")
        tm.register(t)
        assert tm.check_quota("t1", "max_agents", 999999) is True


# ------------------------------------------------------------------
# CircuitBreakerPool
# ------------------------------------------------------------------


class TestCircuitBreakerPool:
    def test_isolation(self) -> None:
        pool = CircuitBreakerPool()
        allowed1, state1 = pool.check("t1", "a1", "act1", depth=0)
        allowed2, state2 = pool.check("t2", "a1", "act1", depth=0)
        assert allowed1 is True
        assert allowed2 is True
        # Trip t1
        for _ in range(5):
            pool.record_failure("t1", "a1", "act1")
        allowed1, _ = pool.check("t1", "a1", "act1", depth=0)
        allowed2, _ = pool.check("t2", "a1", "act1", depth=0)
        assert allowed1 is False
        assert allowed2 is True

    def test_cleanup_idle(self) -> None:
        pool = CircuitBreakerPool()
        pool.check("t1", "a1", "act1")
        removed = pool.cleanup_idle(idle_seconds=0)
        assert removed == 1

    def test_get_status(self) -> None:
        pool = CircuitBreakerPool()
        status = pool.get_status("t1", "a1", "act1")
        assert status["state"] == "CLOSED"
        assert status["failure_count"] == 0


# ------------------------------------------------------------------
# AuditLogService
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_env_secret():
    """Set HMAC secret for AuditLogService in all tests, restoring the prior value."""
    saved = os.environ.get("MAREF_HMAC_SECRET_KEY")
    os.environ["MAREF_HMAC_SECRET_KEY"] = "test-secret-for-testing"
    yield
    if saved:
        os.environ["MAREF_HMAC_SECRET_KEY"] = saved
    else:
        os.environ.pop("MAREF_HMAC_SECRET_KEY", None)


class TestAuditLogService:
    def test_log_and_query(self) -> None:
        svc = AuditLogService()
        entry = svc.log("t1", "a1", "file.read", "ALLOW")
        assert entry.action == "file.read"
        assert svc.verify_integrity("t1") is True
        results, total = svc.query("t1")
        assert total == 1
        assert results[0].action == "file.read"

    def test_query_filters(self) -> None:
        svc = AuditLogService()
        svc.log("t1", "a1", "file.read", "ALLOW")
        svc.log("t1", "a2", "shell.exec", "DENY")
        svc.log("t2", "a1", "file.read", "ALLOW")
        results, total = svc.query("t1", agent_id="a1")
        assert total == 1
        results, total = svc.query("t1", action="shell.exec")
        assert total == 1
        results, total = svc.query("t2")
        assert total == 1

    def test_integrity_verification(self) -> None:
        svc = AuditLogService()
        svc.log("t1", "a1", "act", "ALLOW")
        assert svc.verify_integrity("t1") is True
        assert svc.verify_integrity("t2") is True  # No entries = vacuously true

    def test_no_secret_signs_with_empty_hmac(self) -> None:
        """No secret → service still works but entries carry no HMAC signature."""
        saved = os.environ.pop("MAREF_HMAC_SECRET_KEY", None)
        try:
            svc = AuditLogService()
            entry = svc.log("t1", "a1", "file.read", "ALLOW")
            assert entry.hmac_signature == ""
        finally:
            if saved:
                os.environ["MAREF_HMAC_SECRET_KEY"] = saved
            else:
                os.environ.pop("MAREF_HMAC_SECRET_KEY", None)


# ------------------------------------------------------------------
# TrustScoreService
# ------------------------------------------------------------------


class TestTrustScoreService:
    def test_set_and_get(self) -> None:
        svc = TrustScoreService()
        svc.set_score("t1", "a1", 75.0, "test")
        assert svc.get_score("t1", "a1") == 75.0
        assert svc.get_score("t2", "a1") is None

    def test_tenant_isolation(self) -> None:
        svc = TrustScoreService()
        svc.set_score("t1", "a1", 75.0)
        svc.set_score("t2", "a1", 25.0)
        assert svc.get_score("t1", "a1") == 75.0
        assert svc.get_score("t2", "a1") == 25.0

    def test_history(self) -> None:
        svc = TrustScoreService()
        svc.set_score("t1", "a1", 50.0)
        svc.set_score("t1", "a1", 60.0)
        hist = svc.get_history("t1", "a1")
        assert len(hist) == 2

    def test_decay(self) -> None:
        svc = TrustScoreService()
        svc.set_score("t1", "a1", 100.0)
        svc.decay_scores("t1", decay_factor=0.9)
        assert svc.get_score("t1", "a1") == 90.0


# ------------------------------------------------------------------
# HITLService
# ------------------------------------------------------------------


class TestHITLService:
    def test_request_and_approve(self) -> None:
        svc = HITLRouter()
        event = svc.request("t1", "a1", "file.delete", "Delete file?")
        assert event.status == HITLStatus.PENDING
        result = svc.gaas_approve("t1", event.event_id)
        assert result == HITLStatus.APPROVED
        assert svc.get_tenant_pending("t1") == []

    def test_reject(self) -> None:
        svc = HITLRouter()
        event = svc.request("t1", "a1", "file.delete", "Delete file?")
        result = svc.gaas_reject("t1", event.event_id, "No")
        assert result == HITLStatus.REJECTED

    def test_tenant_isolation(self) -> None:
        svc = HITLRouter()
        e1 = svc.request("t1", "a1", "act", "desc")
        svc.request("t2", "a1", "act", "desc")
        assert len(svc.get_tenant_pending("t1")) == 1
        assert len(svc.get_tenant_pending("t2")) == 1
        svc.gaas_approve("t1", e1.event_id)
        assert len(svc.get_tenant_pending("t1")) == 0
        assert len(svc.get_tenant_pending("t2")) == 1

    def test_auto_approve(self) -> None:
        svc = HITLRouter()
        event = svc.request("t1", "a1", "act", "desc", auto_approve_seconds=0.0)
        auto_approved = svc.process_auto_approvals()
        assert event.event_id in auto_approved
        assert event.status == HITLStatus.AUTO_APPROVED

    def test_cross_tenant_approve_denied(self) -> None:
        svc = HITLRouter()
        event = svc.request("t1", "a1", "act", "desc")
        result = svc.gaas_approve("t2", event.event_id)
        assert result == HITLStatus.REJECTED


# ------------------------------------------------------------------
# GovernanceRouter
# ------------------------------------------------------------------


class TestGovernanceRouter:
    def test_allow_trusted_agent(self) -> None:
        tm = TenantManager()
        tm.register(Tenant(tenant_id="t1", name="Test", tier="business"))
        router = GovernanceRouter(tenant_manager=tm)
        req = GovernRequest(
            tenant_id="t1",
            agent_id="a1",
            action="file.read",
            context=GovernanceContext(trust_score=80.0),
        )
        resp = router.govern(req)
        assert resp.verdict == Verdict.ALLOW
        assert resp.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert resp.audit_log_id != ""

    def test_deny_unknown_tenant(self) -> None:
        router = GovernanceRouter()
        req = GovernRequest(
            tenant_id="unknown",
            agent_id="a1",
            action="file.read",
        )
        resp = router.govern(req)
        assert resp.verdict == Verdict.DENY
        assert "Unknown tenant" in resp.reason

    def test_dangerous_action_ask_user(self) -> None:
        tm = TenantManager()
        tm.register(Tenant(tenant_id="t1", name="Test", tier="business"))
        router = GovernanceRouter(tenant_manager=tm)
        req = GovernRequest(
            tenant_id="t1",
            agent_id="a1",
            action="shell.exec",
            context=GovernanceContext(trust_score=50.0),
        )
        resp = router.govern(req)
        assert resp.verdict == Verdict.ASK_USER
        assert resp.required_hitl_tier == ModelHITLTier.P0

    def test_low_trust_deny(self) -> None:
        tm = TenantManager()
        tm.register(Tenant(tenant_id="t1", name="Test", tier="business"))
        router = GovernanceRouter(tenant_manager=tm)
        req = GovernRequest(
            tenant_id="t1",
            agent_id="a1",
            action="file.read",
            context=GovernanceContext(trust_score=10.0),
        )
        resp = router.govern(req)
        assert resp.verdict == Verdict.DENY
        assert "Trust score too low" in resp.reason

    def test_quota_exceeded(self) -> None:
        tm = TenantManager()
        tm.register(Tenant(tenant_id="t1", name="Test", tier="free"))
        router = GovernanceRouter(tenant_manager=tm)
        # Exhaust quota
        for _ in range(1001):
            req = GovernRequest(
                tenant_id="t1",
                agent_id="a1",
                action="file.read",
            )
            router.govern(req)
        req = GovernRequest(tenant_id="t1", agent_id="a1", action="file.read")
        resp = router.govern(req)
        assert resp.verdict == Verdict.DENY
        assert "Quota exceeded" in resp.reason

    def test_trust_score_update(self) -> None:
        tm = TenantManager()
        tm.register(Tenant(tenant_id="t1", name="Test", tier="business"))
        router = GovernanceRouter(tenant_manager=tm)
        req = GovernRequest(
            tenant_id="t1",
            agent_id="a1",
            action="file.read",
            context=GovernanceContext(trust_score=50.0),
        )
        router.govern(req)
        score = router._trust.get_score("t1", "a1")
        assert score is not None
        assert score > 50.0


# ------------------------------------------------------------------
# BillingService
# ------------------------------------------------------------------


class TestBillingService:
    def test_record_and_get_usage(self) -> None:
        svc = BillingService()
        svc.record("t1", "govern_check", 5)
        svc.record("t1", "govern_check", 3)
        assert svc.get_usage("t1", "govern_check") == 8

    def test_quota_check(self) -> None:
        svc = BillingService()
        svc.record("t1", "govern_check", 5)
        within, current, limit = svc.check_quota("t1", "govern_check", 10)
        assert within is True
        assert current == 5
        assert limit == 10

    def test_generate_bill(self) -> None:
        svc = BillingService()
        now = time.time()
        svc.record("t1", "govern_check", 5)
        bill = svc.generate_bill("t1", now - 3600, now + 3600)
        assert bill.items["govern_check"] == 5
        assert bill.total_quantity == 5

    def test_multi_tenant_isolation(self) -> None:
        svc = BillingService()
        svc.record("t1", "govern_check", 5)
        svc.record("t2", "govern_check", 3)
        assert svc.get_usage("t1", "govern_check") == 5
        assert svc.get_usage("t2", "govern_check") == 3
