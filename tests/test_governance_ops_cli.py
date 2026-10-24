"""CLI surface for governance operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from maref.governance.ops_service import (
    GovernanceOpsService,
    configure_ops_service,
    reset_ops_service,
)
from maref_lite.commands.governance_ops_cli import ops_app


@pytest.fixture()
def runner(tmp_path: Path) -> Any:
    service = GovernanceOpsService(
        audit_path=tmp_path / "audit.jsonl",
        provenance_path=tmp_path / "provenance.jsonl",
        feedback_path=tmp_path / "feedback.jsonl",
        hmac_key="test-key",
    )
    configure_ops_service(service)
    yield CliRunner()
    reset_ops_service()


def _json(result: Any) -> Any:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_status_json(runner: Any) -> None:
    data = _json(runner.invoke(ops_app, ["status", "--json"]))
    assert data["status"] == "ok"


def test_content_review_json(runner: Any) -> None:
    data = _json(
        runner.invoke(
            ops_app,
            [
                "content-review",
                "--platform",
                "xiaohongshu",
                "--text",
                "正常内容。",
                "--json",
            ],
        )
    )
    assert data["verdict"] == "allow"
    assert data["evidence_id"]


def test_provenance_register_and_check(runner: Any) -> None:
    registered = _json(
        runner.invoke(
            ops_app,
            [
                "provenance-register",
                "--asset-id",
                "a1",
                "--license",
                "MIT",
                "--content",
                "hello",
                "--json",
            ],
        )
    )
    assert registered["asset_id"] == "a1"

    checked = _json(
        runner.invoke(ops_app, ["provenance-check", "a1", "--json"])
    )
    assert checked["allowed"] is True


def test_org_and_marketplace_checks_require_configuration(runner: Any) -> None:
    failed = runner.invoke(
        ops_app,
        ["org-check", "--org", "acme", "--role", "admin", "--action", "read", "--json"],
    )
    assert failed.exit_code == 1
    assert "organization policy is not configured" in failed.output

    marketplace = _json(
        runner.invoke(
            ops_app,
            [
                "marketplace-check",
                "--capability",
                "summarize",
                "--license",
                "MIT",
                "--trust",
                "0.9",
                "--validated",
                "--json",
            ],
        )
    )
    assert marketplace["allowed"] is True


def test_evidence_and_flywheel_json(runner: Any) -> None:
    runner.invoke(
        ops_app,
        ["content-review", "--platform", "xiaohongshu", "--text", "正常内容。", "--json"],
    )
    bundle = _json(runner.invoke(ops_app, ["evidence-bundle", "--json"]))
    assert bundle["evidence_count"] >= 1

    report = _json(runner.invoke(ops_app, ["flywheel", "--json"]))
    assert report["kpis"]["decisions"] >= 1


def test_feedback_rejects_unknown_outcome(runner: Any) -> None:
    result = runner.invoke(
        ops_app,
        ["feedback", "--evidence-id", "e1", "--outcome", "bogus"],
    )
    assert result.exit_code == 1
    assert "unsupported feedback outcome" in result.output
