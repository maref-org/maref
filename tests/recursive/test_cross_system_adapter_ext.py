"""Tests for cross_system_adapter.py — env detection, adaptation, migration."""
from __future__ import annotations

import pytest

from maref.recursive.cross_system_adapter import (
    AdaptationConfig,
    AdaptationProfile,
    CrossSystemAdapter,
    EnvironmentSnapshot,
    EnvironmentType,
    MigrationEvent,
)


class TestCrossSystemAdapter:
    def test_initial_state(self):
        adapter = CrossSystemAdapter("agent-1")
        assert adapter.agent_id == "agent-1"
        assert adapter.current_env == EnvironmentType.STANDALONE
        assert adapter.current_config.env_type == EnvironmentType.STANDALONE

    def test_initial_config_values(self):
        adapter = CrossSystemAdapter("agent-1")
        cfg = adapter.current_config
        assert cfg.observation_frequency_hz == 0.5
        assert cfg.consensus_nodes == 1
        assert cfg.max_concurrent_tasks == 4

    def test_adapt_to_environment_same(self):
        adapter = CrossSystemAdapter("agent-1")
        result = adapter.adapt_to_environment(EnvironmentType.STANDALONE)
        assert result is None

    def test_adapt_to_environment_new(self):
        adapter = CrossSystemAdapter("agent-1")
        result = adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        assert result is not None
        assert result.to_env == EnvironmentType.KUBERNETES
        assert result.success is True
        assert adapter.current_env == EnvironmentType.KUBERNETES

    def test_adapt_to_environment_with_profile(self):
        adapter = CrossSystemAdapter("agent-1")
        result = adapter.adapt_to_environment(EnvironmentType.DISTRIBUTED, AdaptationProfile.MINIMAL)
        assert result is not None
        assert result.success is True
        cfg = adapter.current_config
        assert cfg.env_type == EnvironmentType.DISTRIBUTED
        assert cfg.profile == AdaptationProfile.MINIMAL

    def test_adapt_to_environment_standalone_profile(self):
        adapter = CrossSystemAdapter("agent-1", profile=AdaptationProfile.PERFORMANCE)
        cfg = adapter.current_config
        assert cfg.max_concurrent_tasks == 8

    def test_config_to_dict(self):
        adapter = CrossSystemAdapter("agent-1")
        d = adapter.current_config.to_dict()
        assert d["env_type"] == "standalone"
        assert d["profile"] == "balanced"

    def test_detect_environment(self):
        adapter = CrossSystemAdapter("agent-1")
        assert adapter.detect_environment(EnvironmentSnapshot(
            EnvironmentType.KUBERNETES, node_count=1, available_memory_mb=512,
            cpu_cores=2, network_latency_ms=1.0,
        )) == EnvironmentType.STANDALONE

        assert adapter.detect_environment(EnvironmentSnapshot(
            EnvironmentType.KUBERNETES, node_count=3, available_memory_mb=512,
            cpu_cores=2, network_latency_ms=1.0,
        )) == EnvironmentType.KUBERNETES

        assert adapter.detect_environment(EnvironmentSnapshot(
            EnvironmentType.KUBERNETES, node_count=10, available_memory_mb=512,
            cpu_cores=2, network_latency_ms=1.0,
        )) == EnvironmentType.DISTRIBUTED

    def test_take_snapshot(self):
        adapter = CrossSystemAdapter("agent-1")
        snap = adapter.take_snapshot(node_count=3, memory_mb=1024)
        assert snap.node_count == 3
        assert snap.available_memory_mb == 1024.0
        assert len(adapter.get_snapshots()) == 1

    def test_take_snapshot_with_env_type(self):
        adapter = CrossSystemAdapter("agent-1")
        snap = adapter.take_snapshot(env_type=EnvironmentType.KUBERNETES)
        assert snap.env_type == EnvironmentType.KUBERNETES

    def test_migrate(self):
        adapter = CrossSystemAdapter("agent-1")
        adapter.migrate(
            EnvironmentType.STANDALONE,
            EnvironmentType.KUBERNETES,
            AdaptationProfile.RESILIENCE,
        )
        assert adapter.current_env == EnvironmentType.KUBERNETES
        assert adapter.current_config.profile == AdaptationProfile.RESILIENCE

    def test_migrate_to_same(self):
        adapter = CrossSystemAdapter("agent-1")
        result = adapter.migrate(EnvironmentType.STANDALONE, EnvironmentType.STANDALONE)
        assert result is None

    def test_auto_adapt_no_snapshot(self):
        adapter = CrossSystemAdapter("agent-1")
        cfg = adapter.auto_adapt()
        assert cfg.env_type == EnvironmentType.STANDALONE

    def test_auto_adapt_with_snapshot(self):
        adapter = CrossSystemAdapter("agent-1")
        adapter.take_snapshot(node_count=10)
        cfg = adapter.auto_adapt()
        assert cfg.env_type == EnvironmentType.DISTRIBUTED

    def test_get_adaptation_recommendations(self):
        adapter = CrossSystemAdapter("agent-1")
        snap = EnvironmentSnapshot(
            EnvironmentType.KUBERNETES, node_count=5, available_memory_mb=2048,
            cpu_cores=8, network_latency_ms=2.0,
        )
        recs = adapter.get_adaptation_recommendations(snap)
        assert recs["recommended_env"] == "kubernetes"
        assert "needs_migration" in recs

    def test_get_migration_history(self):
        adapter = CrossSystemAdapter("agent-1")
        assert adapter.get_migration_history() == []
        adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        assert len(adapter.get_migration_history()) == 1

    def test_to_dict(self):
        adapter = CrossSystemAdapter("agent-1")
        d = adapter.to_dict()
        assert d["agent_id"] == "agent-1"
        assert d["current_env"] == "standalone"
        assert d["migration_count"] == 0
        assert d["snapshot_count"] == 0

    def test_reset(self):
        adapter = CrossSystemAdapter("agent-1")
        adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        adapter.take_snapshot()
        adapter.reset()
        assert adapter.current_env == EnvironmentType.STANDALONE
        assert len(adapter.get_migration_history()) == 0
        assert len(adapter.get_snapshots()) == 0

    def test_environment_snapshot_to_dict(self):
        snap = EnvironmentSnapshot(
            EnvironmentType.KUBERNETES, node_count=3, available_memory_mb=2048,
            cpu_cores=8, network_latency_ms=2.5,
            pod_status={"running": 3},
        )
        d = snap.to_dict()
        assert d["env_type"] == "kubernetes"
        assert d["network_latency_ms"] == 2.5

    def test_migration_event_to_dict(self):
        event = MigrationEvent(
            from_env=EnvironmentType.STANDALONE,
            to_env=EnvironmentType.KUBERNETES,
            from_config={"a": 1},
            to_config={"b": 2},
            success=True,
        )
        d = event.to_dict()
        assert d["from_env"] == "standalone"
        assert d["to_env"] == "kubernetes"
        assert d["success"] is True

    @pytest.mark.parametrize("profile,expected_obs_freq", [
        (AdaptationProfile.MINIMAL, 0.25),
        (AdaptationProfile.BALANCED, 0.5),
        (AdaptationProfile.PERFORMANCE, 1.0),
        (AdaptationProfile.RESILIENCE, 0.75),
    ])
    def test_profile_adjustments(self, profile, expected_obs_freq):
        adapter = CrossSystemAdapter("agent-1", initial_env=EnvironmentType.STANDALONE, profile=profile)
        assert adapter.current_config.observation_frequency_hz == expected_obs_freq
