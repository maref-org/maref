"""Unit tests for the MAREF Sidecar Server (FastAPI)."""

from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from maref.obs import MarefObsClient, TelemetryLevel
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.obs_bridge import ObsBridge
from sidecar.server import SidecarFastAPI


class TestSidecarFastAPI:
    """Tests for the FastAPI-based Sidecar server."""

    @pytest.fixture
    def client(self) -> TestClient:
        adapter = MockAgentAdapter(num_agents=2)
        collector = ObservationCollector(adapter)
        monitor = CompositeMonitor()
        app = SidecarFastAPI(collector, monitor)
        return TestClient(app)

    def test_health_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_agents_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_observations_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/observations")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "observations" in data

    def test_anomalies_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/anomalies")
        assert response.status_code == 200
        data = response.json()
        assert "anomalies" in data

    def test_metrics_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/metrics")
        assert response.status_code == 200
        assert "maref_observations_total" in response.text

    def test_observations_with_data(self, client: TestClient) -> None:

        response = client.get("/api/observations")
        data = response.json()
        assert data["count"] >= 0


class TestObsStatus:
    """Tests for the /api/obs/status endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        adapter = MockAgentAdapter(num_agents=2)
        collector = ObservationCollector(adapter)
        monitor = CompositeMonitor()
        app = SidecarFastAPI(collector, monitor)
        return TestClient(app)

    def test_obs_status_default(self, client: TestClient) -> None:
        """Without ObsBridge, status should show bridge_connected=False."""
        response = client.get("/api/obs/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "level" in data
        assert "bridge_connected" in data
        assert data["bridge_connected"] is False

    def test_obs_status_with_bridge(self) -> None:
        """With ObsBridge + collector, bridge_connected should be True."""
        MarefObsClient.reset_default()
        tmpdir = tempfile.mkdtemp(prefix="maref_obs_status_")
        adapter = MockAgentAdapter(num_agents=1)
        collector = ObservationCollector(adapter)
        monitor = CompositeMonitor()

        obs_client = MarefObsClient(level=TelemetryLevel.BASIC, base_dir=tmpdir)
        bridge = ObsBridge(client=obs_client)
        app = SidecarFastAPI(collector, monitor, obs_bridge=bridge)
        test_client = TestClient(app)

        response = test_client.get("/api/obs/status")
        assert response.status_code == 200
        data = response.json()
        assert data["bridge_connected"] is True
        assert data["level"] == "basic"
