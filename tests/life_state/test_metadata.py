"""Tests for C31: Life State Metadata model."""

from __future__ import annotations

import time

from maref.life_state.metadata import (
    LifeStateCapability,
    LifeStateMetadata,
    LifeStateType,
)


class TestLifeStateType:
    def test_all_types_defined(self):
        assert LifeStateType.AGENT.value == "agent"
        assert LifeStateType.SERVICE.value == "service"
        assert LifeStateType.PIPELINE.value == "pipeline"
        assert LifeStateType.KNOWLEDGE.value == "knowledge"
        assert LifeStateType.GOVERNANCE.value == "governance"

    def test_type_count(self):
        assert len(list(LifeStateType)) == 5


class TestLifeStateCapability:
    def test_all_capabilities_defined(self):
        assert LifeStateCapability.COMPUTE.value == "compute"
        assert LifeStateCapability.REASON.value == "reason"
        assert LifeStateCapability.LEARN.value == "learn"
        assert LifeStateCapability.COMMUNICATE.value == "communicate"
        assert LifeStateCapability.HEAL.value == "heal"
        assert LifeStateCapability.REPRODUCE.value == "reproduce"
        assert LifeStateCapability.OBSERVE.value == "observe"
        assert LifeStateCapability.GOVERN.value == "govern"
        assert LifeStateCapability.EVOLVE.value == "evolve"

    def test_capability_count(self):
        assert len(list(LifeStateCapability)) == 9


class TestLifeStateMetadata:
    def test_default_creation(self):
        meta = LifeStateMetadata()
        assert len(meta.state_id) == 16
        assert meta.state_type == LifeStateType.AGENT
        assert meta.version == "0.1.0"
        assert meta.capabilities == set()
        assert meta.health_score == 100.0
        assert meta.lineage is None
        assert meta.labels == {}
        assert meta.metadata_version == "1.0"

    def test_creation_with_custom_values(self):
        meta = LifeStateMetadata(
            state_id="custom-id-123",
            state_type=LifeStateType.SERVICE,
            version="1.2.3",
            capabilities={LifeStateCapability.COMPUTE, LifeStateCapability.COMMUNICATE},
            health_score=85.5,
            lineage="parent-id-456",
            labels={"env": "prod", "team": "core"},
        )
        assert meta.state_id == "custom-id-123"
        assert meta.state_type == LifeStateType.SERVICE
        assert meta.version == "1.2.3"
        assert meta.has_capability(LifeStateCapability.COMPUTE)
        assert meta.has_capability(LifeStateCapability.COMMUNICATE)
        assert not meta.has_capability(LifeStateCapability.LEARN)
        assert meta.health_score == 85.5
        assert meta.lineage == "parent-id-456"
        assert meta.labels == {"env": "prod", "team": "core"}

    def test_health_clamping(self):
        meta = LifeStateMetadata(health_score=150.0)
        assert meta.health_score == 100.0

        meta.update_health(-20.0)
        assert meta.health_score == 0.0

        meta.update_health(50.0)
        assert meta.health_score == 50.0

    def test_add_remove_capability(self):
        meta = LifeStateMetadata()
        meta.add_capability(LifeStateCapability.REASON)
        assert meta.has_capability(LifeStateCapability.REASON)

        meta.remove_capability(LifeStateCapability.REASON)
        assert not meta.has_capability(LifeStateCapability.REASON)

        meta.remove_capability(LifeStateCapability.REASON)

    def test_label_operations(self):
        meta = LifeStateMetadata()
        meta.set_label("region", "us-east")
        assert meta.get_label("region") == "us-east"
        assert meta.get_label("missing", "default") == "default"

    def test_age_seconds(self):
        past = time.time() - 10.0
        meta = LifeStateMetadata(birth_time=past)
        age = meta.age_seconds()
        assert age >= 10.0
        assert age < 11.0

    def test_to_dict(self):
        meta = LifeStateMetadata(
            state_id="test-id",
            state_type=LifeStateType.GOVERNANCE,
            capabilities={LifeStateCapability.GOVERN, LifeStateCapability.OBSERVE},
            health_score=92.0,
        )
        d = meta.to_dict()
        assert d["state_id"] == "test-id"
        assert d["state_type"] == "governance"
        assert d["version"] == "0.1.0"
        assert sorted(d["capabilities"]) == ["govern", "observe"]
        assert d["health_score"] == 92.0
        assert d["lineage"] is None
        assert d["metadata_version"] == "1.0"

    def test_from_dict_roundtrip(self):
        original = LifeStateMetadata(
            state_id="roundtrip-id",
            state_type=LifeStateType.PIPELINE,
            version="2.0.0",
            capabilities={LifeStateCapability.COMPUTE, LifeStateCapability.LEARN},
            health_score=77.7,
            lineage="parent-abc",
            labels={"key": "val"},
        )
        d = original.to_dict()
        restored = LifeStateMetadata.from_dict(d)
        assert restored.state_id == original.state_id
        assert restored.state_type == original.state_type
        assert restored.version == original.version
        assert restored.capabilities == original.capabilities
        assert restored.health_score == original.health_score
        assert restored.lineage == original.lineage
        assert restored.labels == original.labels

    def test_from_dict_defaults(self):
        restored = LifeStateMetadata.from_dict({})
        assert len(restored.state_id) == 16
        assert restored.state_type == LifeStateType.AGENT
        assert restored.health_score == 100.0

    def test_all_five_types_can_be_created(self):
        for st in LifeStateType:
            meta = LifeStateMetadata(state_type=st)
            assert meta.state_type == st

    def test_capabilities_from_list_post_init(self):
        meta = LifeStateMetadata(capabilities=[LifeStateCapability.HEAL])
        assert meta.has_capability(LifeStateCapability.HEAL)
