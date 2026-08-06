"""Tests for Pipeline Registry (pipeline_registry.py)."""

from __future__ import annotations

import pytest

from maref.governance.core_pipeline import Verdict
from maref.governance.pipeline_registry import (
    PipelineGovernor,
    PipelineRegistration,
    QualityTier,
)
from maref.integration.hitl import HITLTier


# ---------------------------------------------------------------------------
# PipelineRegistration
# ---------------------------------------------------------------------------


def test_pipeline_registration_minimal():
    reg = PipelineRegistration(
        pipeline_id="video_producer",
        name="官方点阵动画视频管线",
        entry_point="python pipeline.py produce-video",
        description="PIL 逐帧绘制 + ffmpeg 合成",
        quality_tier=QualityTier.OFFICIAL,
    )
    assert reg.pipeline_id == "video_producer"
    assert reg.quality_tier == QualityTier.OFFICIAL
    assert reg.verified is False
    assert reg.tags == []


def test_pipeline_registration_full():
    reg = PipelineRegistration(
        pipeline_id="video_producer",
        name="官方点阵动画视频管线",
        entry_point="python pipeline.py produce-video",
        description="PIL 逐帧绘制 + ffmpeg 合成",
        quality_tier=QualityTier.OFFICIAL,
        tags=["video", "animation", "production"],
        git_status="committed",
        commit_hash="abc123",
        verified=True,
        metadata={"author": "MAREF Team", "version": "2.0"},
    )
    assert reg.git_status == "committed"
    assert reg.commit_hash == "abc123"
    assert reg.verified is True
    assert "video" in reg.tags


def test_pipeline_registration_to_dict():
    reg = PipelineRegistration(
        pipeline_id="test",
        name="Test Pipeline",
        entry_point="./run.sh",
        description="A test pipeline",
        quality_tier=QualityTier.STABLE,
        tags=["test"],
        git_status="committed",
        verified=True,
    )
    d = reg.to_dict()
    assert d["pipeline_id"] == "test"
    assert d["quality_tier"] == "STABLE"
    assert d["quality_tier_id"] == 1
    assert d["verified"] is True


def test_pipeline_registration_from_dict():
    data = {
        "pipeline_id": "audio_mixer",
        "name": "音频混音管线",
        "entry_point": "python mix.py",
        "description": "多轨音频混音",
        "quality_tier": "OFFICIAL",
        "tags": ["audio", "production"],
        "git_status": "committed",
        "verified": True,
    }
    reg = PipelineRegistration.from_dict(data)
    assert reg.pipeline_id == "audio_mixer"
    assert reg.quality_tier == QualityTier.OFFICIAL
    assert reg.verified is True


def test_pipeline_registration_from_dict_numeric_tier():
    data = {
        "pipeline_id": "deprecated_pipe",
        "name": "Old Pipeline",
        "entry_point": "old.py",
        "description": "Old deprecated pipeline",
        "quality_tier": 3,
    }
    reg = PipelineRegistration.from_dict(data)
    assert reg.quality_tier == QualityTier.DEPRECATED


# ---------------------------------------------------------------------------
# PipelineGovernor
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_governor() -> PipelineGovernor:
    governor = PipelineGovernor()
    governor.register(
        PipelineRegistration(
            pipeline_id="video_producer",
            name="官方视频管线",
            entry_point="python pipeline.py produce-video",
            description="PIL 逐帧绘制",
            quality_tier=QualityTier.OFFICIAL,
            tags=["video"],
            git_status="committed",
            commit_hash="abc123",
            verified=True,
        )
    )
    governor.register(
        PipelineRegistration(
            pipeline_id="audio_mixer",
            name="音频混音管线",
            entry_point="python mix.py",
            description="多轨音频混音",
            quality_tier=QualityTier.STABLE,
            tags=["audio"],
            git_status="committed",
            verified=False,
        )
    )
    governor.register(
        PipelineRegistration(
            pipeline_id="produce_launch",
            name="实验性视频管线",
            entry_point="node produce_launch.js",
            description="HTML + Playwright 截图",
            quality_tier=QualityTier.EXPERIMENTAL,
            tags=["video"],
            git_status="never_committed",
            verified=False,
        )
    )
    governor.register(
        PipelineRegistration(
            pipeline_id="old_renderer",
            name="旧渲染管线",
            entry_point="python old_render.py",
            description="已弃用的渲染方案",
            quality_tier=QualityTier.DEPRECATED,
            tags=["video"],
            git_status="committed",
            verified=False,
        )
    )
    return governor


class TestPipelineGovernor:
    """Tests for PipelineGovernor registry operations and selection validation."""

    def test_register_and_get(self, sample_governor):
        reg = sample_governor.get_pipeline("video_producer")
        assert reg is not None
        assert reg.name == "官方视频管线"

    def test_get_nonexistent(self, sample_governor):
        reg = sample_governor.get_pipeline("nonexistent")
        assert reg is None

    def test_count(self, sample_governor):
        assert sample_governor.count() == 4

    def test_list_pipelines(self, sample_governor):
        all_pipes = sample_governor.list_pipelines()
        assert len(all_pipes) == 4
        assert "video_producer" in all_pipes

    def test_list_by_tier(self, sample_governor):
        officials = sample_governor.list_pipelines_by_tier(QualityTier.OFFICIAL)
        assert len(officials) == 1
        assert officials[0].pipeline_id == "video_producer"

        experimental = sample_governor.list_pipelines_by_tier(QualityTier.EXPERIMENTAL)
        assert len(experimental) == 1

    def test_register_from_dict(self, sample_governor):
        reg = sample_governor.register_from_dict({
            "pipeline_id": "new_pipe",
            "name": "New Pipeline",
            "entry_point": "new.py",
            "description": "A new pipeline",
            "quality_tier": "STABLE",
        })
        assert reg.pipeline_id == "new_pipe"
        assert sample_governor.count() == 5

    def test_register_replaces(self, sample_governor):
        """Re-registering same id replaces the existing entry."""
        sample_governor.register(
            PipelineRegistration(
                pipeline_id="video_producer",
                name="Updated Video Pipeline",
                entry_point="python pipeline.py produce-video",
                description="Updated description",
                quality_tier=QualityTier.OFFICIAL,
                verified=True,
            )
        )
        reg = sample_governor.get_pipeline("video_producer")
        assert reg is not None
        assert reg.name == "Updated Video Pipeline"

    # -----------------------------------------------------------------------
    # validate_selection tests — these map to the audit findings
    # -----------------------------------------------------------------------

    def test_validate_official_pipeline_allowed(self, sample_governor):
        """An OFFICIAL, verified pipeline should be ALLOWED."""
        verdict, reason, hitl_tier = sample_governor.validate_selection(
            "video_producer", agent_id="agent-01"
        )
        assert verdict == Verdict.ALLOW
        assert reason == ""
        assert hitl_tier is None

    def test_validate_experimental_asks_user(self, sample_governor):
        """This is the core audit finding: produce_launch is EXPERIMENTAL → ASK_USER."""
        verdict, reason, hitl_tier = sample_governor.validate_selection(
            "produce_launch", agent_id="agent-01"
        )
        assert verdict == Verdict.ASK_USER
        assert "EXPERIMENTAL" in reason
        assert hitl_tier == HITLTier.P1_ESCALATE

    def test_validate_deprecated_denied(self, sample_governor):
        """DEPRECATED pipelines should be DENIED."""
        verdict, reason, hitl_tier = sample_governor.validate_selection(
            "old_renderer", agent_id="agent-01"
        )
        assert verdict == Verdict.DENY
        assert "DEPRECATED" in reason
        assert hitl_tier == HITLTier.P2_LOG

    def test_validate_unregistered_pipeline(self, sample_governor):
        """An unregistered pipeline should trigger ASK_USER."""
        verdict, reason, hitl_tier = sample_governor.validate_selection(
            "maref_video_loop_v4.py", agent_id="agent-01"
        )
        assert verdict == Verdict.ASK_USER
        assert "not registered" in reason
        assert hitl_tier == HITLTier.P1_ESCALATE

    def test_validate_stable_unverified_warns(self, sample_governor):
        """STABLE but unverified pipeline should trigger ASK_USER (P2)."""
        verdict, reason, hitl_tier = sample_governor.validate_selection(
            "audio_mixer", agent_id="agent-01"
        )
        assert verdict == Verdict.ASK_USER
        assert "STABLE but not verified" in reason
        assert hitl_tier == HITLTier.P2_LOG

    def test_validate_with_empty_governor(self):
        """An empty governor rejects everything."""
        governor = PipelineGovernor()
        verdict, reason, hitl_tier = governor.validate_selection("anything", "agent-01")
        assert verdict == Verdict.ASK_USER
        assert "not registered" in reason

    def test_validate_with_audit_callback(self):
        """Audit callback is invoked on every validation."""
        events: list[tuple[str, str, str, str]] = []

        def audit_cb(etype, actor, detail, pid):
            events.append((etype, actor, detail, pid))

        governor = PipelineGovernor(audit_callback=audit_cb)
        governor.register(
            PipelineRegistration(
                pipeline_id="test_pipe",
                name="Test",
                entry_point="test.py",
                description="Test",
                quality_tier=QualityTier.OFFICIAL,
                verified=True,
            )
        )
        # ALLOW triggers audit
        governor.validate_selection("test_pipe", "agent-42")
        assert any(e[0] == "pipeline.allowed" for e in events)

        # Unregistered triggers audit
        governor.validate_selection("unknown", "agent-42")
        assert any(e[0] == "pipeline.unregistered" for e in events)

    # -----------------------------------------------------------------------
    # suggest_best
    # -----------------------------------------------------------------------

    def test_suggest_best_returns_official_first(self, sample_governor):
        """suggest_best should return OFFICIAL pipelines before EXPERIMENTAL ones."""
        suggestions = sample_governor.suggest_best("video")
        assert len(suggestions) >= 2
        # First should be OFFICIAL
        assert suggestions[0].quality_tier == QualityTier.OFFICIAL
        # OFFICIAL before EXPERIMENTAL
        tiers = [s.quality_tier for s in suggestions]
        assert tiers.index(QualityTier.OFFICIAL) < tiers.index(QualityTier.EXPERIMENTAL)

    def test_suggest_best_no_match(self, sample_governor):
        suggestions = sample_governor.suggest_best("nonexistent_task")
        assert suggestions == []

    def test_suggest_best_empty_governor(self):
        governor = PipelineGovernor()
        assert governor.suggest_best("video") == []
