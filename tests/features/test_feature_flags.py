from __future__ import annotations

import os
import tempfile

from maref.features.feature_flags import (
    FeatureFlag,
    FeatureFlagConfig,
    FeatureFlagManager,
    InMemoryFeatureFlagStore,
)


class TestFeatureFlagManager:
    def setup_method(self) -> None:
        FeatureFlagManager._instance = None
        self.manager = FeatureFlagManager()

    def test_default_state(self) -> None:
        for flag in FeatureFlag:
            assert self.manager.is_enabled(flag) is False

    def test_enable_disable(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        assert self.manager.is_enabled(flag) is False

        self.manager.set_enabled(flag, True)
        assert self.manager.is_enabled(flag) is True

        self.manager.set_enabled(flag, False)
        assert self.manager.is_enabled(flag) is False

    def test_rollout_zero_percent(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 0)
        assert self.manager.is_enabled(flag, user_id="user_a") is False

    def test_rollout_hundred_percent(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 100)
        assert self.manager.is_enabled(flag, user_id="user_a") is True
        assert self.manager.is_enabled(flag, user_id="user_b") is True

    def test_rollout_fifty_percent(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 50)
        results = [self.manager.is_enabled(flag, user_id=f"user_{i}") for i in range(1000)]
        enabled_count = sum(results)
        assert 350 < enabled_count < 650

    def test_user_id_consistency(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 30)
        result_1 = self.manager.is_enabled(flag, user_id="consistent_user")
        result_2 = self.manager.is_enabled(flag, user_id="consistent_user")
        assert result_1 == result_2

    def test_rollout_boundary_values(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 1)
        assert self.manager.is_enabled(flag, user_id="user_a") is not None

        self.manager.set_rollout_percentage(flag, 99)
        assert self.manager.is_enabled(flag, user_id="user_b") is not None

    def test_rollout_clamping(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_rollout_percentage(flag, -10)
        config = self.manager.get_config(flag)
        assert config is not None
        assert config.rollout_percentage == 0

        self.manager.set_rollout_percentage(flag, 150)
        config = self.manager.get_config(flag)
        assert config is not None
        assert config.rollout_percentage == 100

    def test_whitelist_bypass_percentage(self) -> None:
        flag = FeatureFlag.CANARY_RELEASE
        self.manager.set_enabled(flag, True)
        self.manager.set_rollout_percentage(flag, 0)
        assert self.manager.is_enabled(flag, user_id="whitelisted_user") is False

        self.manager.add_to_whitelist(flag, "whitelisted_user")
        assert self.manager.is_enabled(flag, user_id="whitelisted_user") is True

        self.manager.remove_from_whitelist(flag, "whitelisted_user")
        assert self.manager.is_enabled(flag, user_id="whitelisted_user") is False

    def test_get_all_flags(self) -> None:
        all_flags = self.manager.get_all_flags()
        assert len(all_flags) == len(FeatureFlag)
        for flag in FeatureFlag:
            assert flag.value in all_flags
            assert "enabled" in all_flags[flag.value]
            assert "rollout_percentage" in all_flags[flag.value]
            assert "whitelist" in all_flags[flag.value]

    def test_save_and_load_config(self) -> None:
        self.manager.set_enabled(FeatureFlag.CANARY_RELEASE, True)
        self.manager.set_rollout_percentage(FeatureFlag.CANARY_RELEASE, 50)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            self.manager.save(tmp_path)

            FeatureFlagManager._instance = None
            new_manager = FeatureFlagManager()
            new_manager.load(tmp_path)

            config = new_manager.get_config(FeatureFlag.CANARY_RELEASE)
            assert config is not None
            assert config.enabled is True
            assert config.rollout_percentage == 50
        finally:
            os.unlink(tmp_path)

    def test_load_nonexistent_file(self) -> None:
        FeatureFlagManager._instance = None
        manager = FeatureFlagManager()
        manager.load("/tmp/nonexistent_file_xyz.json")
        for flag in FeatureFlag:
            assert manager.is_enabled(flag) is False

    def test_reset(self) -> None:
        self.manager.set_enabled(FeatureFlag.CANARY_RELEASE, True)
        self.manager.set_rollout_percentage(FeatureFlag.ENHANCED_AUDIT, 75)
        assert self.manager.is_enabled(FeatureFlag.CANARY_RELEASE) is True

        self.manager.reset()
        for flag in FeatureFlag:
            assert self.manager.is_enabled(flag) is False
            config = self.manager.get_config(flag)
            assert config is not None
            assert config.rollout_percentage == 0


class TestInMemoryFeatureFlagStore:
    def test_get_set(self) -> None:
        store = InMemoryFeatureFlagStore()
        assert store.get("test_flag") is None

        config = FeatureFlagConfig(flag=FeatureFlag.CANARY_RELEASE, enabled=True)
        store.set("test_flag", config)
        assert store.get("test_flag") is config

    def test_all(self) -> None:
        store = InMemoryFeatureFlagStore()
        assert store.all() == {}

        config = FeatureFlagConfig(flag=FeatureFlag.CANARY_RELEASE)
        store.set("f1", config)
        assert "f1" in store.all()

    def test_clear(self) -> None:
        store = InMemoryFeatureFlagStore()
        store.set("f1", FeatureFlagConfig(flag=FeatureFlag.CANARY_RELEASE))
        store.clear()
        assert store.all() == {}


class TestFeatureFlagSingleton:
    def setup_method(self) -> None:
        FeatureFlagManager._instance = None

    def test_singleton(self) -> None:
        m1 = FeatureFlagManager()
        m2 = FeatureFlagManager()
        assert m1 is m2

    def test_singleton_state_shared(self) -> None:
        m1 = FeatureFlagManager()
        m2 = FeatureFlagManager()
        m1.set_enabled(FeatureFlag.CANARY_RELEASE, True)
        assert m2.is_enabled(FeatureFlag.CANARY_RELEASE) is True


class TestUserHashDistribution:
    def setup_method(self) -> None:
        FeatureFlagManager._instance = None
        self.manager = FeatureFlagManager()

    def test_hash_distribution_uniformity(self) -> None:
        buckets = [0] * 100
        for i in range(10000):
            h = FeatureFlagManager._hash_user(f"user_{i}")
            buckets[h] += 1
        for count in buckets:
            assert 70 <= count <= 130

    def test_different_users_different_hashes(self) -> None:
        hashes = {FeatureFlagManager._hash_user(f"user_{i}") for i in range(100)}
        assert len(hashes) > 1
