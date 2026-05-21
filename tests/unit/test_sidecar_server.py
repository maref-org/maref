"""Unit tests for the MAREF Sidecar Server (FastAPI)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.protocol import (
    EntropyReading,
    Observation,
    ObservationType,
)
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
        import asyncio

        response = client.get("/api/observations")
        data = response.json()
        assert data["count"] >= 0
