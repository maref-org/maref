"""v0.53 I2: A2A 强制验签接线。

验证：
1. 配置 MAREF_A2A_PEER_PUBLIC_KEYS 后，无签名 / 错误签名的写操作返回 401
2. 正确 Ed25519 签名通过（send/cancel/state/push_notification）
3. 未配置 peer keys 时旧行为不回归（legacy 放行）
4. 读操作（task_get / agent-card）不受验签影响
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maref.signing.signing_key import ReportSigningKey
from sidecar.collector import MockAgentAdapter, ObservationCollector
from sidecar.monitor import CompositeMonitor
from sidecar.server import create_app


def _make_client(tmp_path: Path, peer_keys: dict[str, str] | None = None) -> TestClient:
    os.environ.pop("MAREF_A2A_PEER_PUBLIC_KEYS", None)
    if peer_keys is not None:
        os.environ["MAREF_A2A_PEER_PUBLIC_KEYS"] = json.dumps(peer_keys)
    adapter = MockAgentAdapter()
    collector = ObservationCollector(adapter)
    monitor = CompositeMonitor()
    app = create_app(collector, monitor, None, federated=True, allow_unauthenticated=True)
    return TestClient(app)


def _auth_headers(key: ReportSigningKey, body: dict) -> dict[str, str]:
    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    timestamp = str(time.time())
    signed = f"{timestamp}.{body_bytes.decode('utf-8')}".encode()
    sig = key.sign_report(signed)
    return {
        "X-A2A-Agent-Id": "peer-1",
        "X-A2A-Signature": sig,
        "X-A2A-Timestamp": timestamp,
    }


def _send_body() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tasks/send",
        "params": {
            "id": "task-1",
            "message": {"parts": [{"text": "hello"}]},
            "metadata": {},
        },
    }


class TestPeerVerification:
    @pytest.fixture
    def peer_key(self) -> ReportSigningKey:
        return ReportSigningKey.generate()

    def test_send_without_signature_401(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        resp = client.post("/api/a2a/task/send", json=_send_body())
        assert resp.status_code == 401

    def test_send_valid_signature_ok(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        body = _send_body()
        resp = client.post("/api/a2a/task/send", json=body, headers=_auth_headers(peer_key, body))
        assert resp.status_code == 200
        task_id = resp.json()["result"]["id"]
        assert task_id.startswith("maref-task-")

    def test_cancel_without_signature_401(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        resp = client.post("/api/a2a/task/cancel", json={"task_id": "t1"})
        assert resp.status_code == 401

    def test_cancel_valid_signature_ok(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        body = _send_body()
        task_id = client.post(
            "/api/a2a/task/send", json=body, headers=_auth_headers(peer_key, body)
        ).json()["result"]["id"]
        cancel = {"task_id": task_id, "reason": "stop"}
        resp = client.post("/api/a2a/task/cancel", json=cancel, headers=_auth_headers(peer_key, cancel))
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_state_without_signature_401(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        resp = client.post("/api/a2a/task/state", json={"task_id": "t1", "state": "completed"})
        assert resp.status_code == 401

    def test_push_notification_without_signature_401(
        self, tmp_path: Path, peer_key: ReportSigningKey
    ):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        resp = client.post("/api/a2a/task/push_notification", json={"task_id": "t1", "event": {}})
        assert resp.status_code == 401

    def test_wrong_peer_401(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        body = _send_body()
        other = ReportSigningKey.generate()
        headers = _auth_headers(other, body)
        headers["X-A2A-Agent-Id"] = "peer-other"
        resp = client.post("/api/a2a/task/send", json=body, headers=headers)
        assert resp.status_code == 401

    def test_read_operations_unaffected(self, tmp_path: Path, peer_key: ReportSigningKey):
        client = _make_client(tmp_path, {"peer-1": peer_key.public_key_pem})
        body = _send_body()
        task_id = client.post(
            "/api/a2a/task/send", json=body, headers=_auth_headers(peer_key, body)
        ).json()["result"]["id"]
        resp = client.get(f"/api/a2a/task/{task_id}")
        assert resp.status_code == 200
        card = client.get("/.well-known/agent-card.json")
        assert card.status_code == 200
        assert "agentCard" in card.json()


class TestLegacyWithoutPeerKeys:
    def test_send_without_keys_allowed(self, tmp_path: Path):
        client = _make_client(tmp_path, None)
        resp = client.post("/api/a2a/task/send", json=_send_body())
        assert resp.status_code == 200

    def test_cancel_without_keys_allowed(self, tmp_path: Path):
        client = _make_client(tmp_path, None)
        body = _send_body()
        task_id = client.post("/api/a2a/task/send", json=body).json()["result"]["id"]
        resp = client.post("/api/a2a/task/cancel", json={"task_id": task_id})
        assert resp.status_code == 200
