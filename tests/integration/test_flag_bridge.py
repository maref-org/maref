from __future__ import annotations

from maref.integration.flag_bridge import (
    FeatureFlag,
    FlagBridge,
    PolicySnapshot,
    RolloutStage,
)


class TestRolloutStage:
    def test_values(self) -> None:
        assert RolloutStage.CANARY_1.value == 1
        assert RolloutStage.CANARY_10.value == 10
        assert RolloutStage.CANARY_50.value == 50
        assert RolloutStage.FULL.value == 100
        assert RolloutStage.ROLLED_BACK.value == 0

    def test_ordering(self) -> None:
        assert RolloutStage.CANARY_1.value < RolloutStage.CANARY_10.value


class TestFeatureFlag:
    def test_to_growthbook_json(self) -> None:
        flag = FeatureFlag(
            key="test_flag",
            description="test",
            enabled=True,
            variations=[{"name": "baseline", "config": {}}],
            rules=[{"name": "canary_1pct", "force": 1}],
        )
        gb = flag.to_growthbook_json()
        assert gb["key"] == "test_flag"
        assert gb["enabled"] is True
        assert gb["variations"] == [{"name": "baseline", "config": {}}]

    def test_to_json(self) -> None:
        flag = FeatureFlag(key="test", description="desc")
        json_str = flag.to_json()
        assert isinstance(json_str, str)
        assert "test" in json_str


class TestPolicySnapshot:
    def test_to_dict(self) -> None:
        snapshot = PolicySnapshot(
            config={"threshold": 0.5},
            source="test",
            metrics={"accuracy": 0.95},
        )
        d = snapshot.to_dict()
        assert d["config"] == {"threshold": 0.5}
        assert d["source"] == "test"
        assert d["metrics"] == {"accuracy": 0.95}
        assert "timestamp" in d

    def test_default_source(self) -> None:
        snapshot = PolicySnapshot(config={})
        assert snapshot.source == "meta_learner"


class TestFlagBridge:
    def test_create_flag_minimal(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"version": 1})
        candidate = PolicySnapshot(config={"version": 2})
        flag = bridge.create_flag(baseline, candidate)
        assert flag.key.startswith("maref_policy_")
        assert flag.enabled is True
        assert len(flag.variations) == 2
        assert flag.variations[0]["name"] == "baseline"
        assert flag.variations[1]["name"] == "candidate"

    def test_create_flag_with_name(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={})
        candidate = PolicySnapshot(config={})
        flag = bridge.create_flag(baseline, candidate, policy_name="test_policy")
        assert flag.key == "maref_policy_test_policy"

    def test_create_flag_canary_rules(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
            initial_stage=RolloutStage.CANARY_10,
        )
        assert len(flag.rules) == 1
        assert flag.rules[0]["coverage"] == 0.1

    def test_create_flag_full_no_rules(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
            initial_stage=RolloutStage.FULL,
        )
        assert flag.rules == []

    def test_advance_stage_to_full(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
        )
        bridge.advance_stage(flag, RolloutStage.FULL)
        assert flag.rules == []
        assert flag.default_variation == 1
        assert flag.metadata["stage"] == 100
        assert flag.metadata["stage_name"] == "FULL"

    def test_advance_stage_to_canary_50(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
            initial_stage=RolloutStage.CANARY_1,
        )
        bridge.advance_stage(flag, RolloutStage.CANARY_50)
        assert len(flag.rules) == 1
        assert flag.rules[0]["coverage"] == 0.5

    def test_advance_stage_with_reason(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
        )
        bridge.advance_stage(flag, RolloutStage.FULL, reason="all_metrics_green")
        assert flag.metadata["stage_reason"] == "all_metrics_green"

    def test_rollback(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
        )
        bridge.rollback(flag, reason="fnr_increased")
        assert flag.metadata["stage"] == 0
        assert flag.metadata["stage_name"] == "ROLLED_BACK"
        assert flag.metadata["stage_reason"] == "fnr_increased"

    def test_export_all(self) -> None:
        bridge = FlagBridge()
        bridge.create_flag(PolicySnapshot(config={}), PolicySnapshot(config={}))
        bridge.create_flag(
            PolicySnapshot(config={}), PolicySnapshot(config={}), policy_name="flag2"
        )
        exported = bridge.export_all()
        assert len(exported) == 2

    def test_export_json(self) -> None:
        bridge = FlagBridge()
        bridge.create_flag(PolicySnapshot(config={}), PolicySnapshot(config={}))
        json_str = bridge.export_json()
        assert isinstance(json_str, str)
        assert "maref_policy" in json_str

    def test_get_flag_exists(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={})
        candidate = PolicySnapshot(config={})
        bridge.create_flag(baseline, candidate, policy_name="myflag")
        flag = bridge.get_flag("maref_policy_myflag")
        assert flag is not None
        assert flag.key == "maref_policy_myflag"

    def test_get_flag_not_found(self) -> None:
        bridge = FlagBridge()
        assert bridge.get_flag("nonexistent") is None

    def test_get_active_flags(self) -> None:
        bridge = FlagBridge()
        bridge.create_flag(PolicySnapshot(config={}), PolicySnapshot(config={}))
        active = bridge.get_active_flags()
        assert len(active) == 1

    def test_get_stats(self) -> None:
        bridge = FlagBridge()
        bridge.create_flag(PolicySnapshot(config={}), PolicySnapshot(config={}))
        bridge.create_flag(
            PolicySnapshot(config={}), PolicySnapshot(config={}), policy_name="flag2"
        )
        stats = bridge.get_stats()
        assert stats["total_flags"] == 2
        assert stats["active_count"] == 2
        assert "CANARY_1" in stats["by_stage"]

    def test_build_canary_pipeline(self) -> None:
        bridge = FlagBridge()
        baseline = PolicySnapshot(config={"v": 1})
        candidate = PolicySnapshot(config={"v": 2})
        pipeline = bridge.build_canary_pipeline(baseline, candidate, "test")
        assert len(pipeline) == 4
        assert pipeline[0]["stage"] == 1
        assert pipeline[0]["percentage"] == 1.0
        assert pipeline[1]["stage"] == 10
        assert pipeline[1]["promote_condition"] == "all_metrics_better_than_baseline"
        assert pipeline[2]["stage"] == 50
        assert pipeline[3]["stage"] == 100

    def test_custom_prefix(self) -> None:
        bridge = FlagBridge(flag_prefix="custom_")
        flag = bridge.create_flag(
            PolicySnapshot(config={}), PolicySnapshot(config={}), policy_name="x"
        )
        assert flag.key == "custom_x"

    def test_create_flag_metadata(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}, metrics={"acc": 0.9}),
            PolicySnapshot(config={}, metrics={"acc": 0.95}),
            initial_stage=RolloutStage.CANARY_1,
        )
        assert flag.metadata["stage"] == 1
        assert flag.metadata["stage_name"] == "CANARY_1"
        assert flag.metadata["baseline_metrics"] == {"acc": 0.9}
        assert flag.metadata["candidate_metrics"] == {"acc": 0.95}

    def test_advance_stage_preserves_updated_at(self) -> None:
        bridge = FlagBridge()
        flag = bridge.create_flag(
            PolicySnapshot(config={}),
            PolicySnapshot(config={}),
        )
        before = flag.metadata.get("updated_at")
        bridge.advance_stage(flag, RolloutStage.FULL)
        assert flag.metadata["updated_at"] >= (before or 0)
