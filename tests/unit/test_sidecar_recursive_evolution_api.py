from __future__ import annotations

from fastapi.testclient import TestClient

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


def make_client() -> TestClient:
    adapter = MockAgentAdapter(num_agents=1)
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    return TestClient(create_app(collector, monitor))


def test_evolution_status_endpoint() -> None:
    client = make_client()
    response = client.get("/api/v1/evolution/status")

    assert response.status_code == 200
    data = response.json()
    assert data["real_writes_enabled"] is False
    assert "metrics_mode" in data


def test_evolution_dry_run_endpoint() -> None:
    client = make_client()
    response = client.post("/api/v1/evolution/dry-run")

    assert response.status_code == 200
    data = response.json()
    assert data["dry_run"] is True
    assert data["real_writes_enabled"] is False
    assert "stop_reason" in data


def test_evolution_approve_proposal_requires_explicit_approval() -> None:
    client = make_client()
    response = client.post("/api/v1/evolution/approve-proposal", json={"proposal_id": "p1"})

    assert response.status_code == 403
    assert "explicit approval" in response.json()["detail"]
