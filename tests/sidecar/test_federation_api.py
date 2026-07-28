"""End-to-end tests for the Federated Audit HTTP API."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


def _make_client(tmp_path: Path) -> TestClient:
    os.environ["MAREF_FEDERATED_STATE"] = str(tmp_path / "federated-state.json")
    adapter = MockAgentAdapter()
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    app = create_app(collector, monitor, None, federated=True)
    return TestClient(app)


def _hash(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


class TestFederationStatus:
    def test_empty_status(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/federation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_count"] == 0
        assert data["federated_root"] is None

    def test_status_after_submit(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"), "tree_size": 10,
        })
        resp = client.get("/api/v1/federation/status")
        data = resp.json()
        assert data["org_count"] == 1
        assert data["federated_root"] is not None
        assert len(data["organizations"]) == 1
        assert data["organizations"][0]["org_id"] == "org-a"


class TestFederationSubmit:
    def test_submit_requires_org_id(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post("/api/v1/federation/submit", json={"root_hash": "x"})
        assert resp.status_code == 400

    def test_submit_requires_root_hash(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post("/api/v1/federation/submit", json={"org_id": "x"})
        assert resp.status_code == 400

    def test_submit_success(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"), "tree_size": 42,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["org_id"] == "org-a"
        assert data["org_count"] == 1

    def test_submit_update_existing_org(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"),
        })
        resp = client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a-updated"),
        })
        assert resp.status_code == 200
        assert resp.json()["org_count"] == 1


class TestFederationProof:
    def test_get_proof_missing_org(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/federation/proof/unknown")
        assert resp.status_code == 404

    def test_get_proof_success(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"),
        })
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-b", "root_hash": _hash("org-b"),
        })
        resp = client.get("/api/v1/federation/proof/org-a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == "org-a"
        assert data["org_root_hash"] == _hash("org-a")
        assert data["org_count"] == 2
        assert data["federated_root_hash"] is not None
        assert len(data["proof_path"]) >= 1

    def test_proof_verifiable_offline(self, tmp_path: Path) -> None:
        from maref.eivl.federated_merkle import FederatedProof

        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"),
        })
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-b", "root_hash": _hash("org-b"),
        })
        resp = client.get("/api/v1/federation/proof/org-a")
        proof = FederatedProof.from_dict(resp.json())
        assert proof.verify() is True


class TestFederationDelete:
    def test_delete_missing_org(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.delete("/api/v1/federation/proof/unknown")
        assert resp.status_code == 404

    def test_delete_org(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"),
        })
        resp = client.delete("/api/v1/federation/proof/org-a")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"
        status = client.get("/api/v1/federation/status").json()
        assert status["org_count"] == 0


class TestFederationRoot:
    def test_root_empty(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        resp = client.get("/api/v1/federation/root")
        assert resp.status_code == 200
        assert resp.json()["federated_root"] is None
        assert resp.json()["org_count"] == 0

    def test_root_after_submit(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        client.post("/api/v1/federation/submit", json={
            "org_id": "org-a", "root_hash": _hash("org-a"),
        })
        resp = client.get("/api/v1/federation/root")
        data = resp.json()
        assert data["federated_root"] == _hash("org-a")
        assert data["org_count"] == 1
