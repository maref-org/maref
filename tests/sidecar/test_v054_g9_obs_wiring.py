"""Tests for ObsBridge wiring (INC-2026-08-13-001 / G9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maref.obs.client import MarefObsClient
from maref.obs.levels import TelemetryLevel
from sidecar.obs_bridge import ObsBridge


class _FakeStateMachine:
    def __init__(self) -> None:
        self.current_entropy = 2
        self._callbacks: list = []

    def add_callback(self, cb) -> None:  # noqa: ANN001
        self._callbacks.append(cb)


class _FakeTransition:
    def __init__(self) -> None:
        self.from_state = type("S", (), {"value": 1, "name": "OBSERVE"})()
        self.to_state = type("S", (), {"value": 2, "name": "ANALYZE"})()
        self.reason = "test"


class _FakeCB:
    def __init__(self) -> None:
        self._trips = [type("T", (), {"reason": "depth_exceeded", "entropy": 2})()]

    def check_depth(self, depth: int) -> bool:
        return True


class TestObsBridgeWiring:
    def test_wire_state_machine_adds_callback(self, tmp_path: Path) -> None:
        client = MarefObsClient(
            level=TelemetryLevel.DETAILED,
            base_dir=tmp_path / "obs",
        )
        bridge = ObsBridge(client=client)
        sm = _FakeStateMachine()
        bridge.wire_state_machine(sm)
        assert len(sm._callbacks) == 1
        # 触发状态机转换 → 产生行为事件
        sm._callbacks[0](_FakeTransition())
        today = Path(client.get_buffer_path())
        assert today.exists()
        content = today.read_text()
        assert "state_transition" in content or "STATE_TRANSITION" in content

    def test_wire_circuit_breaker_wraps(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.OFF)
        bridge = ObsBridge(client=client)
        cb = _FakeCB()
        bridge.wire_circuit_breaker(cb)
        assert cb.check_depth(3) is True

    def test_wire_multiple_components(self) -> None:
        client = MarefObsClient(level=TelemetryLevel.OFF)
        bridge = ObsBridge(client=client)
        sm = _FakeStateMachine()
        bridge.wire_multiple_components({"state_machine": sm})
        assert len(sm._callbacks) == 1


class TestSidecarAutoWiring:
    def test_create_app_wires_obs_bridge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """create_app 传入 obs_bridge 时自动 wire 状态机（G9 核心）。"""
        monkeypatch.setenv("MAREF_HMAC_SECRET_KEY", "test-key")
        monkeypatch.setenv("MAREF_TELEMETRY_LEVEL", "off")
        from sidecar.server import create_app

        client = MarefObsClient(level=TelemetryLevel.OFF)
        bridge = ObsBridge(client=client)
        with patch("pathlib.Path.cwd", return_value=tmp_path), \
             patch("pathlib.Path.home", return_value=tmp_path):
            app = create_app(
                collector=None,  # type: ignore[arg-type]
                monitor=None,  # type: ignore[arg-type]
                obs_bridge=bridge,
            )
        wired = getattr(app.state, "obs_wired", [])
        assert "state_machine" in wired
