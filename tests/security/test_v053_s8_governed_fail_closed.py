"""v0.53 S8: @governed 无 pipeline 时必须 fail-closed（不再默认放行）。"""

from __future__ import annotations

import pytest

from maref.governance.core_pipeline import (
    GovernancePipeline,
    Verdict,
)
from maref.governance.decorators import (
    GovernanceDeniedError,
    governed,
    set_default_pipeline,
)


@pytest.fixture(autouse=True)
def reset_default_pipeline():
    yield
    set_default_pipeline(None)


def test_no_pipeline_denies_fail_closed():
    @governed(require="file.write")
    def write(path: str) -> str:
        return "written"

    with pytest.raises(GovernanceDeniedError) as exc:
        write("/tmp/x")
    assert "no governance pipeline configured" in str(exc.value)


def test_explicit_pipeline_works_without_default():
    pipe = GovernancePipeline()

    @governed(pipeline=pipe, require="file.read")
    def read(path: str) -> str:
        return "content"

    assert read("/tmp/x") == "content"


def test_default_pipeline_restores_after_deny():
    @governed(require="file.read")
    def read(path: str) -> str:
        return "content"

    with pytest.raises(GovernanceDeniedError):
        read("/tmp/x")

    set_default_pipeline(GovernancePipeline())
    assert read("/tmp/x") == "content"


def test_deny_pipeline_raises_governance_denied():
    denier = GovernancePipeline(
        policy_rules=[(999, lambda req: (Verdict.DENY, "always deny", None))]
    )
    set_default_pipeline(denier)

    @governed(require="any.action")
    def do_it() -> str:
        return "done"

    with pytest.raises(GovernanceDeniedError):
        do_it()
