"""Tests for GovernedPipeline (governance/governed_pipeline.py)."""

from __future__ import annotations

import pytest

from maref.governance.decorators import get_default_pipeline, governed, GovernanceDenied
from maref.governance.governed_pipeline import GovernedPipeline


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure no leftover default pipeline between tests."""
    from maref.governance.decorators import set_default_pipeline
    yield
    set_default_pipeline(None)


def test_governed_pipeline_default_assembly():
    pipeline = GovernedPipeline()
    assert hasattr(pipeline, "pipeline")
    assert hasattr(pipeline, "audit")
    assert hasattr(pipeline, "hitl")
    assert hasattr(pipeline, "permission")
    assert hasattr(pipeline, "cb_pool")


def test_governed_pipeline_set_as_default():
    pipeline = GovernedPipeline()
    pipeline.set_as_default()
    assert get_default_pipeline() is pipeline.pipeline


def test_governed_pipeline_govern_allows():
    pipeline = GovernedPipeline()
    from maref.governance.core_pipeline import GovernanceRequest, Verdict
    result = pipeline.govern(GovernanceRequest(action="file.read", agent_id="test", trust_score=80))
    assert result.verdict == Verdict.ALLOW


def test_governed_pipeline_govern_denies():
    pipeline = GovernedPipeline()
    from maref.governance.core_pipeline import GovernanceRequest
    result = pipeline.govern(GovernanceRequest(action="shell.exec", agent_id="test", trust_score=10))
    assert result.verdict.value in ("DENY", "ASK_USER")


def test_governed_pipeline_integration_with_decorator():
    """GovernedPipeline set_as_default makes @governed work end-to-end."""
    pipeline = GovernedPipeline()
    pipeline.set_as_default()

    @governed(require="file.read")
    def read_file(path):
        return "content"

    assert read_file("/tmp/test.txt") == "content"


def test_governed_pipeline_decorator_blocks():
    pipeline = GovernedPipeline()
    pipeline.set_as_default()
    from maref.governance.decorators import set_default_pipeline
    from maref.governance.core_pipeline import GovernancePipeline, Verdict
    # Override with deny-all pipeline for the block test
    deny_pipe = GovernancePipeline(policy_rules=[
        (999, lambda req: (Verdict.DENY, "always deny", None))
    ])
    set_default_pipeline(deny_pipe)

    @governed(require="any.action")
    def do_something():
        return "done"

    with pytest.raises(GovernanceDeniedError):
        do_something()
