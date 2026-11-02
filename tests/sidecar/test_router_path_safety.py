"""Sidecar 路由路径穿越回归测试。

proposal/vaccine 路由把用户提供的 ID 拼进文件名，必须在写盘前拒绝
路径分隔符与 ``..``，否则可越出 data/ 目录写入任意 JSON 文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sidecar.proposal_router as proposal_router
import sidecar.vaccine_router as vaccine_router


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    proposal_dir = tmp_path / "proposals"
    proposal_dir.mkdir()
    vaccine_dir = tmp_path / "vaccines"
    safetygate_dir = vaccine_dir / "safetygate_rules"
    safetygate_dir.mkdir(parents=True)

    monkeypatch.setattr(proposal_router, "_PROPOSAL_DIR", proposal_dir)
    monkeypatch.setattr(
        proposal_router, "_INDEX_FILE", proposal_dir / "proposals_index.jsonl"
    )
    monkeypatch.setattr(vaccine_router, "_VACCINE_DIR", vaccine_dir)
    monkeypatch.setattr(vaccine_router, "_BATCH_LOG", vaccine_dir / "injection_log.jsonl")
    monkeypatch.setattr(vaccine_router, "_SAFETYGATE_DIR", safetygate_dir)
    monkeypatch.setattr(
        vaccine_router, "_FPR_LOG", vaccine_dir / "false_positive_log.jsonl"
    )

    app = FastAPI()
    app.include_router(proposal_router.router)
    app.include_router(vaccine_router.router)
    return TestClient(app)


def test_proposal_ingest_rejects_traversal(client: TestClient, tmp_path: Path) -> None:
    resp = client.post("/api/proposal/ingest", json={"proposal_id": "../../escape"})

    assert resp.status_code == 400
    assert not (tmp_path / "escape.json").exists()


def test_proposal_get_rejects_traversal(client: TestClient, tmp_path: Path) -> None:
    resp = client.get("/api/proposal/..escape")

    assert resp.status_code == 400
    assert not (tmp_path / "escape.json").exists()


def test_proposal_roundtrip_with_safe_id(client: TestClient) -> None:
    resp = client.post("/api/proposal/ingest", json={"proposal_id": "p-1"})
    assert resp.status_code == 200

    resp = client.get("/api/proposal/p-1")
    assert resp.status_code == 200
    assert resp.json()["proposal_id"] == "p-1"


def test_vaccine_inject_rejects_batch_traversal(
    client: TestClient, tmp_path: Path
) -> None:
    resp = client.post(
        "/api/vaccine/inject",
        json={"batch_id": "../escape", "vaccines": [{"vaccine_id": "v1"}]},
    )

    assert resp.status_code == 400
    assert not (tmp_path / "escape.json").exists()


def test_vaccine_inject_rejects_vaccine_id_traversal(
    client: TestClient, tmp_path: Path
) -> None:
    resp = client.post(
        "/api/vaccine/inject",
        json={
            "batch_id": "b1",
            "vaccines": [
                {"vaccine_id": "../../escape", "safetygate_rule": {"id": "r1"}}
            ],
        },
    )

    assert resp.status_code == 400
    assert not (tmp_path / "escape.json").exists()


def test_vaccine_inject_with_safe_ids(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(
        "/api/vaccine/inject",
        json={
            "batch_id": "b1",
            "vaccines": [{"vaccine_id": "v1", "safetygate_rule": {"id": "r1"}}],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["rules_written"] == 1
    assert (tmp_path / "vaccines" / "batch_b1.json").exists()
    assert (tmp_path / "vaccines" / "safetygate_rules" / "v1.json").exists()
