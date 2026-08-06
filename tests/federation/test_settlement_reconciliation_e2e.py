"""Phase 3.2 — distributed settlement reconciliation.

Covers the two sub-goals of task 3.2:

1. **Merkle-roots for settlement** — :class:`FederatedSettlement` computes
   a deterministic Merkle root over billing content (fingerprints exclude
   server-local fields), so two independent servers hash identical charges
   identically.
2. **Cross-server reconciliation + arbitration** — :class:`SettlementReconciler`
   compares two servers' ledgers (missing entries / amount mismatches /
   root hash mismatch) and arbitrates conflicts against the authoritative
   metering source.

The E2E test boots **two real HTTP servers** (provider + consumer), both
bill the same cross-org task, reconciles them over HTTP (consistent), then
tampers one server's ledger and verifies the conflict is detected and
arbitrated.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI

from maref.federation.federation_http import (
    FederationHTTPClient,
    create_federation_app,
)
from maref.federation.gateway import FederationGateway
from maref.federation.metering import TaskMeteringEngine
from maref.federation.policy import FederationPolicyEngine
from maref.federation.policy_subscriber import FederatedPolicySubscriber
from maref.federation.settlement import (
    BillingEntry,
    FederatedSettlement,
    billing_charge_key,
    billing_fingerprint,
    merkle_root,
)
from maref.federation.settlement_reconciler import SettlementReconciler
from maref.federation.trust import FederatedTrustEngine
from maref.recursive.trust_engine_v2 import TrustEngineV2

HEALTH_PATH = "/api/v1/federation/health"


# ── Shared helpers ───────────────────────────────────────────────────────


def _build_settlement_app(
    org: str,
    settlement: FederatedSettlement,
) -> FastAPI:
    gateway = FederationGateway()
    trust_engine = FederatedTrustEngine(local_engine=TrustEngineV2())
    subscriber = FederatedPolicySubscriber(local_engine=FederationPolicyEngine(), local_org=org)
    return create_federation_app(
        gateway,
        trust_engine,
        subscriber,
        server_id=org,
        settlement=settlement,
    )


class ThreadedFederationServer:
    """Run a federation FastAPI app under uvicorn in a background thread."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self.base_url = ""

    def start(self) -> None:
        config = uvicorn.Config(self._app, host="127.0.0.1", port=0, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 15.0
        while time.time() < deadline:
            if self._server.started and self._server.servers:
                port = self._server.servers[0].sockets[0].getsockname()[1]
                self.base_url = f"http://127.0.0.1:{port}"
                deadline2 = time.time() + 5.0
                while time.time() < deadline2:
                    try:
                        response = httpx.get(f"{self.base_url}{HEALTH_PATH}", timeout=1.0)
                        if response.status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                return
            time.sleep(0.05)
        raise RuntimeError("threaded federation server failed to start")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)


def _record_cross_org_task(
    engine: TaskMeteringEngine,
    task_id: str = "task-1",
    provider_org: str = "OrgA",
    consumer_org: str = "OrgB",
) -> None:
    engine.record(
        task_id=task_id,
        agent_did=f"did:maref:{provider_org}:agent-1",
        agent_aic=f"aic:{task_id}",
        provider_org=provider_org,
        consumer_org=consumer_org,
        duration_ms=1000.0,
        token_count=100,
        success=True,
        complexity_score=0.5,
    )


def _build_settlement_with_ledger(
    task_ids: list[str],
) -> FederatedSettlement:
    metering = TaskMeteringEngine()
    for task_id in task_ids:
        _record_cross_org_task(metering, task_id=task_id)
    settlement = FederatedSettlement(metering=metering)
    settlement.generate_billing_from_metering()
    return settlement


# ── Component tests: fingerprints + Merkle root ──────────────────────────


def test_billing_fingerprint_excludes_server_local_fields() -> None:
    """Identical charges on different servers hash equal (entry_id/metric_id ignored)."""
    entry_a = BillingEntry(
        entry_id="bill_aaaa",
        provider_org="OrgA",
        consumer_org="OrgB",
        task_id="task-1",
        agent_did="did:agent-1",
        amount=1.515,
        metric_id="met_aaaa",
        timestamp=1000.0,
    )
    entry_b = BillingEntry(
        entry_id="bill_bbbb",
        provider_org="OrgA",
        consumer_org="OrgB",
        task_id="task-1",
        agent_did="did:agent-1",
        amount=1.515,
        metric_id="met_bbbb",
        timestamp=9999.0,
    )
    assert billing_fingerprint(entry_a) == billing_fingerprint(entry_b)
    assert billing_charge_key(entry_a) == billing_charge_key(entry_b) == "OrgA|OrgB|task-1"

    tampered = dataclasses.replace(entry_b, amount=3.03)
    assert billing_fingerprint(tampered) != billing_fingerprint(entry_a)


def test_merkle_root_order_independent_and_deterministic() -> None:
    fp1 = billing_fingerprint(BillingEntry("e1", "OrgA", "OrgB", "t1", "did:1", 1.0, "m1"))
    fp2 = billing_fingerprint(BillingEntry("e2", "OrgA", "OrgB", "t2", "did:1", 2.0, "m2"))
    fp3 = billing_fingerprint(BillingEntry("e3", "OrgA", "OrgB", "t3", "did:1", 3.0, "m3"))
    assert merkle_root([fp1, fp2, fp3]) == merkle_root([fp3, fp1, fp2])
    assert merkle_root([fp1, fp2]) != merkle_root([fp1, fp2, fp3])
    assert merkle_root([]) is None


def test_settlement_root_identical_across_servers() -> None:
    """Two servers billing the same tasks produce the same Merkle root."""
    settlement_a = _build_settlement_with_ledger(["t1", "t2"])
    settlement_b = _build_settlement_with_ledger(["t2", "t1"])  # different order
    root_a = settlement_a.compute_settlement_root()
    root_b = settlement_b.compute_settlement_root()
    assert root_a["root_hash"] == root_b["root_hash"]
    assert root_a["tree_size"] == root_b["tree_size"] == 2


# ── Component tests: reconciler ──────────────────────────────────────────


def test_reconciler_consistent_when_ledgers_identical() -> None:
    settlement_a = _build_settlement_with_ledger(["t1", "t2"])
    settlement_b = _build_settlement_with_ledger(["t1", "t2"])
    reconciler = SettlementReconciler()
    report = reconciler.reconcile(
        {"server_id": "a", **settlement_a.ledger_snapshot()},
        {"server_id": "b", **settlement_b.ledger_snapshot()},
    )
    assert report.is_consistent is True
    assert report.discrepancies == []
    assert report.root_hash_a == report.root_hash_b


def test_reconciler_detects_amount_mismatch() -> None:
    settlement_a = _build_settlement_with_ledger(["t1"])
    settlement_b = _build_settlement_with_ledger(["t1"])
    # Tamper B's ledger: double the charge.
    entry = settlement_b._billing_entries[0]
    settlement_b._billing_entries[0] = dataclasses.replace(entry, amount=entry.amount * 2.0)

    report = SettlementReconciler().reconcile(
        {"server_id": "a", **settlement_a.ledger_snapshot()},
        {"server_id": "b", **settlement_b.ledger_snapshot()},
    )
    assert report.is_consistent is False
    types = {d["type"] for d in report.discrepancies}
    assert "root_hash_mismatch" in types
    assert "amount_mismatch" in types
    mismatch = [d for d in report.discrepancies if d["type"] == "amount_mismatch"][0]
    assert mismatch["charge_key"] == "OrgA|OrgB|t1"
    assert mismatch["amount_a"] != mismatch["amount_b"]


def test_reconciler_detects_missing_entry() -> None:
    settlement_a = _build_settlement_with_ledger(["t1", "t2"])
    settlement_b = _build_settlement_with_ledger(["t1"])

    report = SettlementReconciler().reconcile(
        {"server_id": "a", **settlement_a.ledger_snapshot()},
        {"server_id": "b", **settlement_b.ledger_snapshot()},
    )
    assert report.is_consistent is False
    types = {d["type"] for d in report.discrepancies}
    assert "tree_size_mismatch" in types
    assert "missing_entry" in types
    missing = [d for d in report.discrepancies if d["type"] == "missing_entry"][0]
    assert missing["charge_key"] == "OrgA|OrgB|t2"
    assert missing["present_side"] == "a"


# ── Component tests: arbitration ─────────────────────────────────────────


def test_arbitration_resolves_amount_conflict_against_authoritative() -> None:
    settlement_a = _build_settlement_with_ledger(["t1"])
    settlement_b = _build_settlement_with_ledger(["t1"])
    entry = settlement_b._billing_entries[0]
    settlement_b._billing_entries[0] = dataclasses.replace(entry, amount=entry.amount * 2.0)

    reconciler = SettlementReconciler()
    report = reconciler.reconcile(
        {"server_id": "org-provider", **settlement_a.ledger_snapshot()},
        {"server_id": "org-consumer", **settlement_b.ledger_snapshot()},
    )
    reconciler.arbitrate(
        report,
        {"server_id": "org-provider", **settlement_a.authoritative_snapshot()},
    )

    assert report.arbitration["verdict"] == "resolved"
    assert report.arbitration["all_resolved"] is True
    amount_resolutions = [
        r for r in report.arbitration["resolutions"] if r["discrepancy_type"] == "amount_mismatch"
    ]
    assert amount_resolutions[0]["verdict"] == "a_matches_authoritative"
    assert "org-consumer" in amount_resolutions[0]["correction"]


def test_arbitration_flags_spurious_entry() -> None:
    """B bills a task the authoritative metering never saw → spurious."""
    settlement_a = _build_settlement_with_ledger(["t1"])
    settlement_b = _build_settlement_with_ledger(["t1", "t2"])  # t2 is bogus

    reconciler = SettlementReconciler()
    report = reconciler.reconcile(
        {"server_id": "a", **settlement_a.ledger_snapshot()},
        {"server_id": "b", **settlement_b.ledger_snapshot()},
    )
    reconciler.arbitrate(
        report,
        {"server_id": "a", **settlement_a.authoritative_snapshot()},
    )

    assert report.is_consistent is False
    assert report.arbitration["verdict"] == "resolved"
    missing = [
        r for r in report.arbitration["resolutions"] if r["discrepancy_type"] == "missing_entry"
    ][0]
    assert missing["verdict"] == "entry_spurious"
    assert "remove from b" in missing["correction"]


# ── Two-server E2E ───────────────────────────────────────────────────────


def test_two_server_ledger_reconciliation_e2e() -> None:
    """Provider + consumer servers: consistent by default, arbitrated on tamper."""
    metering_a = TaskMeteringEngine()
    settlement_a = FederatedSettlement(metering=metering_a)
    metering_b = TaskMeteringEngine()
    settlement_b = FederatedSettlement(metering=metering_b)

    server_a = ThreadedFederationServer(_build_settlement_app("org-provider", settlement_a))
    server_b = ThreadedFederationServer(_build_settlement_app("org-consumer", settlement_b))
    server_a.start()
    server_b.start()
    try:
        # 1) Both servers observe the same cross-org task and bill it.
        for engine in (metering_a, metering_b):
            _record_cross_org_task(engine)
        for settlement in (settlement_a, settlement_b):
            settlement.generate_billing_from_metering()

        # 2) Roots agree over HTTP → reconciliation is consistent.
        with FederationHTTPClient(server_a.base_url) as client_a:
            root_a = client_a.fetch_settlement_root()
            assert root_a["server_id"] == "org-provider"
            assert root_a["tree_size"] == 1
            assert root_a["root_hash"] is not None
            assert client_a.fetch_settlement_ledger()["tree_size"] == 1
            assert client_a.fetch_settlement_summary()["settlement"]["total_billing_entries"] == 1

            report = client_a.run_settlement_reconcile(server_b.base_url)
        assert report["is_consistent"] is True
        assert report["server_a"] == "org-provider"
        assert report["server_b"] == "org-consumer"
        assert report["root_hash_a"] == report["root_hash_b"]

        # 3) Tamper server B's ledger (in-process) → conflict + arbitration.
        entry = settlement_b._billing_entries[0]
        settlement_b._billing_entries[0] = dataclasses.replace(entry, amount=entry.amount * 2.0)

        with FederationHTTPClient(server_a.base_url) as client_a:
            report = client_a.run_settlement_reconcile(server_b.base_url, arbitrate=True)
        assert report["is_consistent"] is False
        types = {d["type"] for d in report["discrepancies"]}
        assert "root_hash_mismatch" in types
        assert "amount_mismatch" in types
        arbitration = report["arbitration"]
        assert arbitration["verdict"] == "resolved"
        assert arbitration["all_resolved"] is True
        amount_resolutions = [
            r for r in arbitration["resolutions"] if r["discrepancy_type"] == "amount_mismatch"
        ]
        assert amount_resolutions[0]["verdict"] == "a_matches_authoritative"
        assert "org-consumer" in amount_resolutions[0]["correction"]
    finally:
        server_a.stop()
        server_b.stop()
