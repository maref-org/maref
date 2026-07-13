"""Smoke tests for maref.life_state.port_monitor."""
from __future__ import annotations

import pytest

from maref.life_state.port_monitor import PortCheckResult, PortMonitor, ServiceDef


class TestPortCheckResult:
    def test_init_default(self) -> None:
        result = PortCheckResult(host="localhost", port=8080)
        assert result.host == "localhost"
        assert result.port == 8080
        assert result.connected is False
        assert result.http_status is None
        assert result.functional is False
        assert result.error == ""

    def test_healthy_not_connected(self) -> None:
        result = PortCheckResult(host="localhost", port=8080)
        assert result.healthy is False

    def test_healthy_connected_no_path(self) -> None:
        result = PortCheckResult(host="localhost", port=8080, connected=True)
        assert result.healthy is True

    def test_healthy_connected_with_path(self) -> None:
        result = PortCheckResult(host="localhost", port=8080, connected=True, path="/health", functional=True)
        assert result.healthy is True

    def test_healthy_connected_with_path_not_functional(self) -> None:
        result = PortCheckResult(host="localhost", port=8080, connected=True, path="/health", functional=False)
        assert result.healthy is False


class TestServiceDef:
    def test_init_default(self) -> None:
        svc = ServiceDef(name="api", host="localhost", port=8080)
        assert svc.name == "api"
        assert svc.host == "localhost"
        assert svc.port == 8080
        assert svc.health_path == "/health"
        assert svc.timeout_ms == 5000.0
        assert svc.restart_command == ""

    def test_init_custom(self) -> None:
        svc = ServiceDef(
            name="web", host="0.0.0.0", port=3000,
            health_path="/api/health", timeout_ms=10000.0,
            restart_command="systemctl restart web", description="Web server",
        )
        assert svc.health_path == "/api/health"
        assert svc.timeout_ms == 10000.0
        assert svc.description == "Web server"

    def test_state_id(self) -> None:
        svc = ServiceDef(name="api", host="localhost", port=8080)
        assert svc.state_id == "port_api_8080"


class TestPortMonitor:
    def test_init_default(self) -> None:
        monitor = PortMonitor()
        assert monitor is not None
        assert monitor.services == []
        assert monitor.history == []

    def test_init_with_services(self) -> None:
        svc = ServiceDef(name="api", host="localhost", port=8080)
        monitor = PortMonitor(services=[svc])
        assert len(monitor.services) == 1
        assert monitor.services[0].name == "api"
