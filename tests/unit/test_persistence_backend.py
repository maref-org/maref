"""Persistence backend tests for GaaS and Federation modules.

Validates that TenantManager, AuditLogService, TaskMeteringEngine and
FederatedSettlement survive process restarts when a db_path/log_path is
provided.  Memory mode (no path) remains unchanged and is covered by
existing tests in test_gaas.py / test_federation_settlement.py.
"""

from __future__ import annotations

import time

import pytest

from maref.federation.metering import TaskMeteringEngine, TaskMetric
from maref.federation.settlement import FederatedSettlement
from maref.gaas.audit_service import AuditLogService
from maref.gaas.tenant import Tenant, TenantManager

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_hmac_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """HMAC secret required by AuditLogService in all tests."""
    monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-secret-for-persistence")


# ------------------------------------------------------------------
# TenantManager persistence
# ------------------------------------------------------------------


class TestTenantManagerPersistence:
    def test_survives_restart(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "tenants.sqlite"
        tm1 = TenantManager(db_path=db)
        t = Tenant(tenant_id="t1", name="Acme", tier="business")
        key = tm1.register(t)
        assert tm1.get_by_id("t1") is not None

        # Simulate process restart with a fresh instance on the same DB.
        tm2 = TenantManager(db_path=db)
        loaded = tm2.get_by_id("t1")
        assert loaded is not None
        assert loaded.name == "Acme"
        assert loaded.tier == "business"
        assert tm2.get_by_api_key(key) is not None
        # Quota loaded correctly (business tier -> max_agents 100).
        assert tm2.check_quota("t1", "max_agents", 50) is True
        assert tm2.check_quota("t1", "max_agents", 100) is False
        assert len(tm2.list_tenants()) == 1

    def test_duplicate_register_after_restart(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "tenants.sqlite"
        tm1 = TenantManager(db_path=db)
        tm1.register(Tenant(tenant_id="t1", name="Acme"))
        tm2 = TenantManager(db_path=db)
        with pytest.raises(ValueError):
            tm2.register(Tenant(tenant_id="t1", name="Other"))

    def test_memory_mode_unchanged(self) -> None:
        tm = TenantManager()
        key = tm.register(Tenant(tenant_id="t1", name="Test"))
        assert tm.get_by_api_key(key) is not None
        assert tm.get_by_id("t1") is not None


# ------------------------------------------------------------------
# AuditLogService persistence
# ------------------------------------------------------------------


class TestAuditLogServicePersistence:
    def test_survives_restart(self, tmp_path: pytest.TempPathFactory) -> None:
        log_file = tmp_path / "audit.jsonl"
        svc1 = AuditLogService(log_path=log_file)
        svc1.log("t1", "a1", "file.read", "ALLOW")
        svc1.log("t1", "a2", "shell.exec", "DENY")
        svc1.log("t2", "a1", "file.read", "ALLOW")
        assert svc1.get_stats("t1")["total_entries"] == 2

        svc2 = AuditLogService(log_path=log_file)
        _, total_t1 = svc2.query("t1")
        assert total_t1 == 2
        _, total_t2 = svc2.query("t2")
        assert total_t2 == 1
        # HMAC integrity holds after reload from disk.
        assert svc2.verify_integrity("t1") is True
        assert svc2.verify_integrity("t2") is True

    def test_append_only_across_restarts(self, tmp_path: pytest.TempPathFactory) -> None:
        log_file = tmp_path / "audit.jsonl"
        svc1 = AuditLogService(log_path=log_file)
        svc1.log("t1", "a1", "act1", "ALLOW")
        svc2 = AuditLogService(log_path=log_file)
        svc2.log("t1", "a1", "act2", "DENY")
        svc3 = AuditLogService(log_path=log_file)
        results, total = svc3.query("t1")
        assert total == 2
        assert {e.action for e in results} == {"act1", "act2"}

    def test_memory_mode_unchanged(self) -> None:
        svc = AuditLogService()
        svc.log("t1", "a1", "act", "ALLOW")
        assert svc.get_stats("t1")["total_entries"] == 1


# ------------------------------------------------------------------
# TaskMeteringEngine persistence
# ------------------------------------------------------------------


class TestTaskMeteringEnginePersistence:
    def test_survives_restart(self, tmp_path: pytest.TempPathFactory) -> None:
        db = tmp_path / "metering.sqlite"
        m1 = TaskMeteringEngine(db_path=db)
        m1.record(
            task_id="task1",
            agent_did="did:maref:test:agent1",
            agent_aic="AIC-test",
            provider_org="Acme",
            consumer_org="Gamma",
            duration_ms=1500.0,
            token_count=500,
            success=True,
            complexity_score=0.7,
        )
        assert m1.metric_count == 1

        m2 = TaskMeteringEngine(db_path=db)
        assert m2.metric_count == 1
        metrics = m2.iter_all_metrics()
        assert metrics[0].task_id == "task1"
        assert metrics[0].provider_org == "Acme"
        assert metrics[0].success is True
        assert metrics[0].complexity_score == 0.7

    def test_memory_mode_unchanged(self) -> None:
        m = TaskMeteringEngine()
        m.record("t", "did", "aic", "A", "B", 100.0, 10, True, 0.5)
        assert m.metric_count == 1


# ------------------------------------------------------------------
# FederatedSettlement persistence
# ------------------------------------------------------------------


class TestFederatedSettlementPersistence:
    @staticmethod
    def _record_metric(metering: TaskMeteringEngine, task_id: str = "task1") -> TaskMetric:
        return metering.record(
            task_id=task_id,
            agent_did="did:maref:test:a1",
            agent_aic="AIC-test",
            provider_org="Acme",
            consumer_org="Gamma",
            duration_ms=1000.0,
            token_count=100,
            success=True,
            complexity_score=0.5,
        )

    def test_billing_and_ledger_survive_restart(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        db = tmp_path / "settlement.sqlite"
        metering = TaskMeteringEngine()
        s1 = FederatedSettlement(metering, db_path=db)
        metric = self._record_metric(metering)
        entry = s1.record_billing(metric)
        assert entry.entry_id != ""  # cross-org, not internal
        balance_before = s1.get_balance("Acme", "Gamma")
        assert balance_before > 0

        s2 = FederatedSettlement(metering, db_path=db)
        assert len(s2._billing_entries) == 1
        assert s2.get_balance("Acme", "Gamma") == balance_before
        assert len(s2.get_ledger()) == 1

    def test_proposal_lifecycle_survives_restart(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        db = tmp_path / "settlement.sqlite"
        metering = TaskMeteringEngine()
        s1 = FederatedSettlement(metering, db_path=db)
        metric = self._record_metric(metering, task_id="task2")
        s1.record_billing(metric)
        now = time.time()
        proposal = s1.generate_proposal("Acme", "Gamma", now - 60, now + 60)
        assert s1.accept_proposal(proposal.proposal_id) is True

        # Restart -> proposal status persists as "accepted".
        s2 = FederatedSettlement(metering, db_path=db)
        loaded = s2.get_proposal(proposal.proposal_id)
        assert loaded is not None
        assert loaded.status.value == "accepted"
        assert loaded.total_amount > 0

        # Settle on the restarted instance and verify across another restart.
        assert s2.settle_proposal(proposal.proposal_id) is True
        s3 = FederatedSettlement(metering, db_path=db)
        settled = s3.get_proposal(proposal.proposal_id)
        assert settled is not None
        assert settled.status.value == "settled"

    def test_memory_mode_unchanged(self) -> None:
        metering = TaskMeteringEngine()
        s = FederatedSettlement(metering)
        metric = self._record_metric(metering)
        entry = s.record_billing(metric)
        assert entry.entry_id != ""
