"""Tests for @governed decorator (governance/decorators.py)."""

from __future__ import annotations

import pytest

from maref.governance.core_pipeline import (
    GovernancePipeline,
    GovernanceRequest,
    Verdict,
)
from maref.governance.decorators import (
    GovernanceDeniedError,
    governed,
    set_default_pipeline,
    get_default_pipeline,
)


@pytest.fixture(autouse=True)
def reset_default_pipeline():
    """Reset default pipeline after each test."""
    yield
    set_default_pipeline(None)


@pytest.fixture
def default_pipeline():
    pipe = GovernancePipeline()
    set_default_pipeline(pipe)
    return pipe


def test_governed_decorator_allows(default_pipeline):
    @governed(require="file.read")
    def read_file(path):
        return "content"

    assert read_file("/tmp/test.txt") == "content"


def test_governed_decorator_blocks():
    pipe = GovernancePipeline(policy_rules=[
        (999, lambda req: (Verdict.DENY, "always deny", None))
    ])
    set_default_pipeline(pipe)

    @governed(require="any.action")
    def do_something():
        return "done"

    with pytest.raises(GovernanceDeniedError) as exc:
        do_something()
    assert "denied" in str(exc.value).lower()


def test_governed_decorator_with_custom_pipeline():
    """Custom pipeline supplied directly to decorator."""
    custom = GovernancePipeline()
    denier = GovernancePipeline(policy_rules=[
        (999, lambda req: (Verdict.DENY, "always deny", None))
    ])
    set_default_pipeline(custom)

    @governed(pipeline=denier, require="file.read")
    def delete_file(path):
        return "deleted"

    with pytest.raises(GovernanceDeniedError):
        delete_file("/tmp/test.txt")


def test_governed_no_pipeline_fallback():
    """Without any pipeline, @governed should warn but not block."""
    set_default_pipeline(None)  # ensure None

    @governed(require="file.write")
    def write(path):
        return "written"

    assert write("/tmp/test.txt") == "written"


def test_governed_asks_user_does_not_block():
    """ASK_USER verdict does not raise — it's advisory."""
    pipe = GovernancePipeline()
    set_default_pipeline(pipe)

    @governed(require="git.push")
    def push():
        return "pushed"

    assert push() == "pushed"


def test_governed_agent_id_and_tenant():
    pipe = GovernancePipeline()
    set_default_pipeline(pipe)

    @governed(require="file.read", agent_id="custom-agent", tenant_id="custom-tenant")
    def read():
        return "data"

    assert read() == "data"


def test_governed_requires_action_argument():
    """Without require/action, decorator should raise."""
    with pytest.raises(ValueError):
        @governed()
        def f():
            pass


def test_governed_set_default_pipeline(default_pipeline):
    assert get_default_pipeline() is default_pipeline


def test_governed_get_default_none():
    set_default_pipeline(None)
    assert get_default_pipeline() is None
