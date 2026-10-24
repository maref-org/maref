"""Governance operations API: content, provenance, policy, evidence, flywheel."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from maref.governance.ops_service import GovernanceOpsService
from maref.governance.org_policy import OrganizationPolicy
from sidecar.governance_ops_router import create_governance_ops_router


@pytest.fixture()
def service(tmp_path: Path) -> GovernanceOpsService:
    policy = OrganizationPolicy.from_dict(
        {
            "organizations": {
                "acme": {
                    "roles": {
                        "admin": {"allow": ["*"]},
                        "viewer": {"allow": ["read.*"], "deny": ["write.*"]},
                    }
                }
            },
            "strict": True,
        }
    )
    return GovernanceOpsService(
        audit_path=tmp_path / "audit.jsonl",
        provenance_path=tmp_path / "provenance.jsonl",
        feedback_path=tmp_path / "feedback.jsonl",
        hmac_key="test-key",
        org_policy=policy,
    )


@pytest.fixture()
def client(service: GovernanceOpsService) -> TestClient:
    app = FastAPI()
    app.include_router(create_governance_ops_router(service))
    return TestClient(app)


def test_status(client: TestClient) -> None:
    response = client.get("/api/v1/governance/ops/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["org_policy_loaded"] is True
    assert "xiaohongshu" in data["platforms"]


def test_content_review_allow_and_review(client: TestClient) -> None:
    allow = client.post(
        "/api/v1/governance/ops/content/review",
        json={"platform": "xiaohongshu", "text": "分享一个治理框架。"},
    )
    assert allow.status_code == 200
    assert allow.json()["verdict"] == "allow"
    assert allow.json()["evidence_id"]

    review = client.post(
        "/api/v1/governance/ops/content/review",
        json={"platform": "xiaohongshu", "text": "全网最低价的治理课程。"},
    )
    assert review.status_code == 200
    assert review.json()["verdict"] == "review"
    assert review.json()["hitl_event_id"]


def test_content_review_blocks_pii(client: TestClient) -> None:
    response = client.post(
        "/api/v1/governance/ops/content/review",
        json={"platform": "x", "text": "联系我 13800138000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "block"
    assert data["redacted_text"] == "联系我 [REDACTED:phone]"


def test_provenance_lifecycle(client: TestClient) -> None:
    created = client.post(
        "/api/v1/governance/ops/provenance/assets",
        json={
            "asset_id": "a1",
            "content": "hello",
            "license": "MIT",
            "ai_generated": True,
            "model": "m1",
            "prompt_hash": hashlib.sha256(b"prompt").hexdigest(),
        },
    )
    assert created.status_code == 200
    assert created.json()["content_hash"] == hashlib.sha256(b"hello").hexdigest()

    child = client.post(
        "/api/v1/governance/ops/provenance/assets",
        json={"asset_id": "a2", "content": "child", "license": "MIT", "parent_ids": ["a1"]},
    )
    assert child.status_code == 200

    fetched = client.get("/api/v1/governance/ops/provenance/assets/a1")
    assert fetched.status_code == 200

    lineage = client.get("/api/v1/governance/ops/provenance/assets/a2/lineage")
    assert lineage.status_code == 200
    assert lineage.json()["lineage"][0]["asset_id"] == "a1"

    publishable = client.post(
        "/api/v1/governance/ops/provenance/publishable", json={"asset_id": "a2"}
    )
    assert publishable.status_code == 200
    assert publishable.json()["allowed"] is True

    manifest = client.get("/api/v1/governance/ops/provenance/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["asset_count"] == 2
    assert manifest.json()["integrity"] is True


def test_provenance_rejects_unknown_parent(client: TestClient) -> None:
    response = client.post(
        "/api/v1/governance/ops/provenance/assets",
        json={"asset_id": "a1", "content": "x", "license": "MIT", "parent_ids": ["missing"]},
    )
    assert response.status_code == 400


def test_org_check(client: TestClient) -> None:
    allowed = client.post(
        "/api/v1/governance/ops/org/check",
        json={"org_id": "acme", "role": "viewer", "action": "read.report"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["decision"] == "allow"

    denied = client.post(
        "/api/v1/governance/ops/org/check",
        json={"org_id": "acme", "role": "viewer", "action": "write.report"},
    )
    assert denied.status_code == 200
    assert denied.json()["decision"] == "deny"


def test_marketplace_preflight(client: TestClient) -> None:
    response = client.post(
        "/api/v1/governance/ops/marketplace/preflight",
        json={
            "capability": "summarize",
            "license": "MIT",
            "publisher_trust": 0.9,
            "validation": {"all_passed": True},
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True

    high_risk = client.post(
        "/api/v1/governance/ops/marketplace/preflight",
        json={
            "capability": "shell.exec",
            "license": "MIT",
            "publisher_trust": 0.9,
            "validation": {"all_passed": True},
        },
    )
    assert high_risk.status_code == 200
    assert high_risk.json()["allowed"] is False
    assert high_risk.json()["risk_level"] == "high"


def test_evidence_and_flywheel(client: TestClient) -> None:
    client.post(
        "/api/v1/governance/ops/content/review",
        json={"platform": "xiaohongshu", "text": "正常内容。"},
    )
    bundle = client.get("/api/v1/governance/ops/evidence/bundle")
    assert bundle.status_code == 200
    assert bundle.json()["evidence_count"] >= 1

    report = client.get("/api/v1/governance/ops/flywheel/report")
    assert report.status_code == 200
    assert report.json()["kpis"]["decisions"] >= 1

    evidence_id = bundle.json()["evidence_ids"][0]
    feedback = client.post(
        "/api/v1/governance/ops/flywheel/feedback",
        json={"evidence_id": evidence_id, "outcome": "approve", "reviewer": "qa"},
    )
    assert feedback.status_code == 200
    assert feedback.json()["outcome"] == "approve"


def test_router_is_mounted_in_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sidecar.collector import MockAgentAdapter, ObservationCollector
    from sidecar.monitor import CompositeMonitor
    from sidecar.server import create_app

    monkeypatch.setenv("MAREF_MCP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("MAREF_GOVERNANCE_DATA_DIR", str(tmp_path))
    app = create_app(
        ObservationCollector(MockAgentAdapter()),
        CompositeMonitor(),
        allow_unauthenticated=True,
    )
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/v1/governance/ops/content/review" in paths
    assert "/api/v1/governance/ops/evidence/bundle" in paths
