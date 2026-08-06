"""Unit tests for the ObsBridge (observation bridge) module."""

from __future__ import annotations

import asyncio
import tempfile
from unittest.mock import MagicMock

import pytest

from maref.obs import MarefObsClient, TelemetryLevel
from sidecar.obs_bridge import ObsBridge


class TestObsBridge:
    @pytest.fixture
    def obs_client(self) -> MarefObsClient:
        MarefObsClient.reset_default()
        tmpdir = tempfile.mkdtemp(prefix="maref_obs_bridge_")
        return MarefObsClient(level=TelemetryLevel.BASIC, base_dir=tmpdir)

    @pytest.fixture
    def bridge(self, obs_client: MarefObsClient) -> ObsBridge:
        return ObsBridge(client=obs_client)

    def test_init(self, bridge: ObsBridge) -> None:
        assert bridge.get_client() is not None

    def test_get_client_returns_client(self, bridge: ObsBridge, obs_client: MarefObsClient) -> None:
        assert bridge.get_client() is obs_client

    def test_wire_state_machine(self, bridge: ObsBridge) -> None:
        sm = MagicMock()
        sm.add_callback = MagicMock()
        bridge.wire_state_machine(sm)
        sm.add_callback.assert_called_once()

    def test_wire_circuit_breaker(self, bridge: ObsBridge) -> None:
        cb = MagicMock()
        cb.check_depth = MagicMock(return_value=False)
        bridge.wire_circuit_breaker(cb)
        result = cb.check_depth(5)
        assert result is False

    def test_wire_oscillation_loop(self, bridge: ObsBridge) -> None:
        loop = MagicMock()

        async def mock_detect_and_fix(
            rate: float, entropy: int, current_state: str,
        ) -> dict:
            return {"oscillations": []}

        loop.detect_and_fix = mock_detect_and_fix
        bridge.wire_oscillation_loop(loop)
        result = asyncio.run(loop.detect_and_fix(1.0, 0, "test"))
        assert result == {"oscillations": []}

    def test_wire_multiple_components(self, bridge: ObsBridge) -> None:
        sm = MagicMock()
        sm.add_callback = MagicMock()
        cb = MagicMock()
        cb.check_depth = MagicMock(return_value=False)
        osc_loop = MagicMock()

        async def mock_detect_and_fix(
            rate: float, entropy: int, current_state: str,
        ) -> dict:
            return {"oscillations": []}

        osc_loop.detect_and_fix = mock_detect_and_fix

        bridge.wire_multiple_components({
            "state_machine": sm,
            "circuit_breaker": cb,
            "oscillation_loop": osc_loop,
        })

        sm.add_callback.assert_called_once()
        assert cb.check_depth(3) is False
        result = asyncio.run(osc_loop.detect_and_fix(2.0, 1, "test"))
        assert result == {"oscillations": []}

    def test_wire_multiple_components_empty(self, bridge: ObsBridge) -> None:
        bridge.wire_multiple_components({})

    def test_wire_multiple_components_partial(self, bridge: ObsBridge) -> None:
        sm = MagicMock()
        sm.add_callback = MagicMock()
        bridge.wire_multiple_components({"state_machine": sm})
        sm.add_callback.assert_called_once()

    def test_wire_state_machine_stores_callback(self, bridge: ObsBridge) -> None:
        sm = MagicMock()
        sm.add_callback = MagicMock()
        bridge.wire_state_machine(sm)
        assert len(bridge._state_machine_callbacks) == 1

    def test_default_client(self) -> None:
        MarefObsClient.reset_default()
        bridge = ObsBridge()
        assert bridge.get_client() is not None
