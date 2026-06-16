from __future__ import annotations

from maref.recursive.cross_system_adapter import (
    ENV_DEFAULTS,
    PROFILE_ADJUSTMENTS,
    AdaptationProfile,
    CrossSystemAdapter,
    EnvironmentSnapshot,
    EnvironmentType,
)


class TestEnvironmentTypes:
    def test_all_env_types(self):
        assert len(EnvironmentType) == 4

    def test_env_defaults_complete(self):
        for env in [
            EnvironmentType.STANDALONE,
            EnvironmentType.KUBERNETES,
            EnvironmentType.DISTRIBUTED,
        ]:
            defaults = ENV_DEFAULTS[env]
            assert "observation_frequency_hz" in defaults
            assert "instrumentation_depth" in defaults
            assert "consensus_nodes" in defaults

    def test_standalone_minimal(self):
        defaults = ENV_DEFAULTS[EnvironmentType.STANDALONE]
        assert defaults["consensus_nodes"] == 1
        assert defaults["instrumentation_depth"] == 2

    def test_distributed_scale(self):
        defaults = ENV_DEFAULTS[EnvironmentType.DISTRIBUTED]
        assert defaults["consensus_nodes"] > defaults.get("instrumentation_depth", 0)
        assert defaults["max_concurrent_tasks"] > 32


class TestAdaptationProfiles:
    def test_all_profiles(self):
        assert len(AdaptationProfile) == 4

    def test_profile_adjustments(self):
        assert PROFILE_ADJUSTMENTS[AdaptationProfile.BALANCED]["observation_frequency_hz"] == 1.0
        assert PROFILE_ADJUSTMENTS[AdaptationProfile.PERFORMANCE]["max_concurrent_tasks"] > 1.0


class TestCrossSystemAdapterInit:
    def test_default_init(self):
        adapter = CrossSystemAdapter("agent_1")
        assert adapter.current_env == EnvironmentType.STANDALONE
        assert adapter.current_config.env_type == EnvironmentType.STANDALONE

    def test_init_with_kubernetes(self):
        adapter = CrossSystemAdapter("agent_1", initial_env=EnvironmentType.KUBERNETES)
        assert adapter.current_env == EnvironmentType.KUBERNETES
        assert adapter.current_config.consensus_nodes >= 3


class TestEnvironmentDetection:
    def test_detect_standalone(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = EnvironmentSnapshot(EnvironmentType.STANDALONE, 1, 512, 2, 1.0)
        result = adapter.detect_environment(snapshot)
        assert result == EnvironmentType.STANDALONE

    def test_detect_kubernetes(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = EnvironmentSnapshot(EnvironmentType.KUBERNETES, 3, 2048, 4, 5.0)
        result = adapter.detect_environment(snapshot)
        assert result == EnvironmentType.KUBERNETES

    def test_detect_distributed(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = EnvironmentSnapshot(EnvironmentType.DISTRIBUTED, 10, 8192, 8, 10.0)
        result = adapter.detect_environment(snapshot)
        assert result == EnvironmentType.DISTRIBUTED


class TestAdaptation:
    def test_adapt_to_kubernetes(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        assert event is not None
        assert event.success
        assert adapter.current_env == EnvironmentType.KUBERNETES

    def test_adapt_to_distributed(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.adapt_to_environment(EnvironmentType.DISTRIBUTED)
        assert event is not None
        assert event.success
        assert adapter.current_env == EnvironmentType.DISTRIBUTED

    def test_adapt_no_change_returns_none(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.adapt_to_environment(EnvironmentType.STANDALONE)
        assert event is None

    def test_adapt_with_profile(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.adapt_to_environment(
            EnvironmentType.KUBERNETES, profile=AdaptationProfile.PERFORMANCE
        )
        assert event is not None
        assert adapter.current_config.profile == AdaptationProfile.PERFORMANCE

    def test_config_changes_on_adaptation(self):
        adapter = CrossSystemAdapter("agent_1")
        old_consensus = adapter.current_config.consensus_nodes
        adapter.adapt_to_environment(EnvironmentType.DISTRIBUTED)
        assert adapter.current_config.consensus_nodes > old_consensus


class TestMigration:
    def test_migrate_standalone_to_k8s(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.migrate(EnvironmentType.STANDALONE, EnvironmentType.KUBERNETES)
        assert event is not None
        assert event.success
        assert event.from_env == EnvironmentType.STANDALONE
        assert event.to_env == EnvironmentType.KUBERNETES

    def test_migrate_k8s_to_distributed(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        event = adapter.migrate(EnvironmentType.KUBERNETES, EnvironmentType.DISTRIBUTED)
        assert event is not None
        assert event.success

    def test_migration_event_to_dict(self):
        adapter = CrossSystemAdapter("agent_1")
        event = adapter.migrate(EnvironmentType.STANDALONE, EnvironmentType.KUBERNETES)
        assert event is not None
        d = event.to_dict()
        assert d["from_env"] == "standalone"
        assert d["to_env"] == "kubernetes"
        assert d["success"]

    def test_migration_history(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.migrate(EnvironmentType.STANDALONE, EnvironmentType.KUBERNETES)
        adapter.migrate(EnvironmentType.KUBERNETES, EnvironmentType.DISTRIBUTED)
        history = adapter.get_migration_history()
        assert len(history) == 2


class TestAutoAdaptation:
    def test_auto_adapt_detects_env(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.take_snapshot(node_count=10, memory_mb=8192)
        config = adapter.auto_adapt()
        assert config.env_type == EnvironmentType.DISTRIBUTED

    def test_auto_adapt_stays_on_same_env(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.take_snapshot(node_count=1)
        config = adapter.auto_adapt()
        assert config.env_type == EnvironmentType.STANDALONE


class TestRecommendations:
    def test_recommendations_standalone(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = EnvironmentSnapshot(EnvironmentType.STANDALONE, 1, 512, 2, 1.0)
        recs = adapter.get_adaptation_recommendations(snapshot)
        assert recs["recommended_env"] == "standalone"
        assert not recs["needs_migration"]

    def test_recommendations_needs_migration(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = EnvironmentSnapshot(EnvironmentType.DISTRIBUTED, 10, 8192, 8, 10.0)
        recs = adapter.get_adaptation_recommendations(snapshot)
        assert recs["recommended_env"] == "distributed"
        assert recs["needs_migration"]


class TestSnapshot:
    def test_take_snapshot(self):
        adapter = CrossSystemAdapter("agent_1")
        snapshot = adapter.take_snapshot(node_count=3, memory_mb=2048)
        assert snapshot.node_count == 3
        assert snapshot.available_memory_mb == 2048

    def test_get_snapshots(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.take_snapshot()
        adapter.take_snapshot(node_count=3)
        snapshots = adapter.get_snapshots()
        assert len(snapshots) == 2


class TestConfig:
    def test_config_to_dict(self):
        adapter = CrossSystemAdapter("agent_1")
        d = adapter.current_config.to_dict()
        assert "env_type" in d
        assert "profile" in d

    def test_adapter_to_dict(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.adapt_to_environment(EnvironmentType.KUBERNETES)
        d = adapter.to_dict()
        assert d["current_env"] == "kubernetes"
        assert d["migration_count"] == 1


class TestReset:
    def test_reset_returns_to_standalone(self):
        adapter = CrossSystemAdapter("agent_1")
        adapter.adapt_to_environment(EnvironmentType.DISTRIBUTED)
        adapter.take_snapshot(node_count=10)
        adapter.reset()
        assert adapter.current_env == EnvironmentType.STANDALONE
        assert len(adapter.get_migration_history()) == 0
        assert len(adapter.get_snapshots()) == 0
