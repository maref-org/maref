from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maref_lite.recursive_governance import (
    MAREFSelfAdapter,
    RecursiveGovernanceConfig,
    RecursiveGovernanceOverlay,
)
from sidecar.protocol import AgentId


class TestRecursiveGovernanceConfig:
    def test_defaults(self) -> None:
        config = RecursiveGovernanceConfig()
        assert config.max_recursion_depth == 4
        assert config.self_observation_cooldown == 5.0
        assert config.max_oscillation_rate == 10.0
        assert config.enable_meta_learning is True
        assert config.enable_policy_sandbox is True
        assert config.sandbox_auto_revert_minutes == 60
        assert config.circuit_breaker_cooldown == 15.0
        assert config.circuit_breaker_max_failures == 5
        assert config.enable_self_healing is True
        assert config.healing_check_interval_seconds == 300.0

    def test_to_dict(self) -> None:
        config = RecursiveGovernanceConfig()
        d = config.to_dict()
        assert d["max_recursion_depth"] == 4
        assert d["enable_meta_learning"] is True
        assert "enable_architecture_proposals" in d


class TestMAREFSelfAdapter:
    def test_list_agents(self) -> None:
        overlay = MagicMock()
        adapter = MAREFSelfAdapter(overlay)
        import asyncio

        agents = asyncio.run(adapter.list_agents())
        assert len(agents) == 1
        assert agents[0].name == "maref-core"
        assert agents[0].namespace == "self"

    def test_get_state(self) -> None:
        overlay = MagicMock()
        overlay.get_status.return_value = {
            "state": "OBSERVE",
            "anomaly_count": 2,
            "entropy": 3,
        }
        adapter = MAREFSelfAdapter(overlay)
        agent_id = AgentId(name="maref-core", namespace="self")
        import asyncio

        snapshot = asyncio.run(adapter.get_state(agent_id))
        assert snapshot is not None
        assert snapshot.state.value == "running"
        assert snapshot.current_task == "OBSERVE"
        assert snapshot.pending_messages == 2

    def test_get_state_wrong_id(self) -> None:
        overlay = MagicMock()
        adapter = MAREFSelfAdapter(overlay)
        agent_id = AgentId(name="other", namespace="other")
        import asyncio

        result = asyncio.run(adapter.get_state(agent_id))
        assert result is None

    def test_get_entropy(self) -> None:
        overlay = MagicMock()
        overlay.get_status.return_value = {"entropy": 4}
        adapter = MAREFSelfAdapter(overlay)
        agent_id = AgentId(name="maref-core", namespace="self")
        import asyncio

        reading = asyncio.run(adapter.get_entropy(agent_id))
        assert reading is not None
        assert reading.value == 4.0
        assert reading.level == "critical"

    def test_get_entropy_low(self) -> None:
        overlay = MagicMock()
        overlay.get_status.return_value = {"entropy": 1}
        adapter = MAREFSelfAdapter(overlay)
        agent_id = AgentId(name="maref-core", namespace="self")
        import asyncio

        reading = asyncio.run(adapter.get_entropy(agent_id))
        assert reading is not None
        assert reading.level == "normal"

    def test_get_entropy_wrong_id(self) -> None:
        overlay = MagicMock()
        adapter = MAREFSelfAdapter(overlay)
        agent_id = AgentId(name="other", namespace="other")
        import asyncio

        result = asyncio.run(adapter.get_entropy(agent_id))
        assert result is None


class TestRecursiveGovernanceOverlay:
    def test_init_defaults(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._config.max_recursion_depth == 4
        assert overlay._recursion_depth == 0
        assert overlay._consecutive_anomalies == 0

    def test_init_with_config(self) -> None:
        config = RecursiveGovernanceConfig(max_recursion_depth=2)
        overlay = RecursiveGovernanceOverlay(config=config)
        assert overlay._config.max_recursion_depth == 2

    def test_stop(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._running = True
        overlay.stop()
        assert overlay._running is False

    def test_detect_oscillation_false_by_default(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay._detect_oscillation() is False

    def test_detect_oscillation_true(self) -> None:
        overlay = RecursiveGovernanceOverlay(
            config=RecursiveGovernanceConfig(max_oscillation_rate=2)
        )
        overlay._state_changes = [1.0, 2.0, 3.0]
        assert overlay._detect_oscillation() is True

    def test_get_meta_decisions(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        assert overlay.get_meta_decisions() == []

    def test_get_meta_decisions_with_data(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._state_changes = [100.0, 200.0, 300.0]
        decisions = overlay.get_meta_decisions()
        assert len(decisions) == 3
        assert decisions[0]["type"] == "state_change"

    def test_get_recursive_status(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        status = overlay.get_recursive_status()
        assert "primary_status" in status
        assert "meta_status" in status
        assert "recursion_depth" in status
        assert "oscillation_detected" in status
        assert "state_change_rate" in status
        assert "circuit_breaker" in status
        assert "meta_learning" in status
        assert "sandbox" in status
        assert "self_healing" in status

    def test_on_self_observation_normal(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._last_observation_time = time.time()
        with (
            patch.object(overlay._primary, "get_status") as mock_status,
            patch.object(overlay._breaker, "record_success") as mock_success,
        ):
            mock_status.return_value = {"critical_count": 0}
            overlay._on_self_observation(MagicMock())
            assert overlay._recursion_depth == 1
            mock_success.assert_called_once()

    def test_on_self_observation_resets_after_60s(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._recursion_depth = 5
        overlay._consecutive_anomalies = 3
        overlay._last_observation_time = time.time() - 120.0

        with (
            patch.object(overlay._primary, "get_status") as mock_status,
            patch.object(overlay._breaker, "check_depth") as mock_check,
        ):
            mock_status.return_value = {"critical_count": 0}
            mock_check.return_value = True
            overlay._on_self_observation(MagicMock())
            assert overlay._recursion_depth == 1
            assert overlay._consecutive_anomalies == 0

    def test_on_self_observation_circuit_breaker_depth(self) -> None:
        overlay = RecursiveGovernanceOverlay(
            config=RecursiveGovernanceConfig(max_recursion_depth=1)
        )
        overlay._recursion_depth = 1

        with patch.object(overlay._breaker, "check_depth") as mock_check:
            mock_check.return_value = False
            overlay._on_self_observation(MagicMock())
            assert overlay._recursion_depth == 0
            assert overlay._breaker._failure_count > 0

    def test_on_self_observation_oscillation(self) -> None:
        overlay = RecursiveGovernanceOverlay(
            config=RecursiveGovernanceConfig(max_oscillation_rate=2)
        )
        overlay._state_changes = [1.0, 2.0, 3.0]

        with (
            patch.object(overlay._primary, "force_stabilize") as mock_stab,
            patch.object(overlay._breaker, "check_oscillation") as mock_check,
        ):
            mock_check.return_value = False
            overlay._on_self_observation(MagicMock())
            mock_stab.assert_called_once()

    def test_on_self_observation_consecutive_anomalies(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._last_observation_time = time.time()
        overlay._consecutive_anomalies = 4

        with (
            patch.object(overlay._primary, "get_status") as mock_status,
            patch.object(overlay._breaker, "check_depth") as mock_depth,
            patch.object(overlay._primary, "force_stabilize") as mock_stab,
        ):
            mock_status.return_value = {"critical_count": 5}
            mock_depth.return_value = True
            overlay._on_self_observation(MagicMock())
            assert overlay._consecutive_anomalies == 5
            mock_stab.assert_called_once()

    def test_on_self_observation_meta_transition(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        overlay._consecutive_anomalies = 2

        with (
            patch.object(overlay._primary, "get_status") as mock_status,
            patch.object(overlay._breaker, "check_depth") as mock_depth,
            patch.object(overlay._meta, "transition_state") as mock_trans,
        ):
            mock_status.return_value = {"critical_count": 1}
            mock_depth.return_value = True
            overlay._on_self_observation(MagicMock())
            mock_trans.assert_called_once()

    def test_handle_oscillation(self) -> None:
        overlay = RecursiveGovernanceOverlay()
        with (
            patch.object(overlay._primary, "force_stabilize") as mock_stab,
            patch.object(overlay._meta_learner, "record_decision") as mock_rec,
        ):
            overlay._state_changes = [1.0, 2.0, 3.0]
            overlay._handle_oscillation()
            mock_stab.assert_called_once()
            mock_rec.assert_called_once()

    def test_get_recursive_status_with_meta_disabled(self) -> None:
        config = RecursiveGovernanceConfig(
            enable_meta_learning=False,
            enable_policy_sandbox=False,
            enable_self_healing=False,
        )
        overlay = RecursiveGovernanceOverlay(config=config)
        status = overlay.get_recursive_status()
        assert status["meta_learning"] is None
        assert status["sandbox"] is None
        assert status["self_healing"] is None

    def test_init_with_healing_loop(self) -> None:
        config = RecursiveGovernanceConfig(enable_self_healing=True)
        overlay = RecursiveGovernanceOverlay(config=config)
        assert overlay._healing_loop is not None

    def test_init_without_healing_loop(self) -> None:
        config = RecursiveGovernanceConfig(enable_self_healing=False)
        overlay = RecursiveGovernanceOverlay(config=config)
        assert overlay._healing_loop is None
