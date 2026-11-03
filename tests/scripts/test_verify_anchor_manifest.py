"""离线锚点复核脚本回归测试.

锚点产物不含审计原文，第三方只能验证"根在某时刻已存在"。这里锁定
manifest/anchors/令牌三者的一致性检查，防止验证器在字段或目录约定
变化后静默放行。
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_anchor_manifest as verify  # noqa: E402


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build(root: Path, *, token_bytes: bytes = b"token-bytes") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    ca = b"ca-certificate"
    (root / "freetsa-cacert.pem").write_bytes(ca)

    anchors_dir = root / "batches"
    anchors_dir.mkdir()
    prefix = "a" * 16
    (anchors_dir / f"{prefix}.tsr").write_bytes(token_bytes)
    (anchors_dir / f"{prefix}.tsq").write_bytes(b"request")

    anchor = {
        "batch_start_id": "start",
        "batch_end_id": "end",
        "merkle_root": "a" * 64,
        "event_count": 3,
        "tsa_token": base64.b64encode(token_bytes).decode("ascii"),
        "anchored_at": 1.0,
    }
    anchors_path = root / "anchors.jsonl"
    anchors_path.write_text(json.dumps(anchor, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "audit_sha256": _sha256(b"audit"),
        "anchors_sha256": _sha256(anchors_path.read_bytes()),
        "tsa_ca_sha256": _sha256(ca),
        "batches": [
            {
                **anchor,
                "token_file": f"batches/{prefix}.tsr",
                "request_file": f"batches/{prefix}.tsq",
            }
        ],
    }
    (root / "ANCHOR_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _ok_openssl(monkeypatch) -> None:
    monkeypatch.setattr(
        verify.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="Verification: OK\n", stderr=""),
    )


class TestVerify:
    def test_complete_artifacts_pass(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)

        assert verify.verify(root, openssl="openssl") == []

    def test_audit_digest_checked_when_provided(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        audit = tmp_path / "audit.jsonl"
        audit.write_bytes(b"audit")

        assert verify.verify(root, audit=audit, openssl="openssl") == []

        audit.write_bytes(b"tampered")
        problems = verify.verify(root, audit=audit, openssl="openssl")
        assert any("audit.jsonl sha256 mismatch" in problem for problem in problems)

    def test_anchors_digest_mismatch_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        (root / "anchors.jsonl").write_text("{}\n", encoding="utf-8")

        problems = verify.verify(root, openssl="openssl")

        assert any("anchors.jsonl sha256 mismatch" in problem for problem in problems)

    def test_ca_digest_mismatch_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        (root / "freetsa-cacert.pem").write_bytes(b"other-ca")

        problems = verify.verify(root, openssl="openssl")

        assert any("freetsa-cacert.pem sha256 mismatch" in problem for problem in problems)

    def test_token_file_mismatch_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        (root / "batches" / ("a" * 16 + ".tsr")).write_bytes(b"different")

        problems = verify.verify(root, openssl="openssl")

        assert any("token file does not match anchor" in problem for problem in problems)

    def test_missing_token_file_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        (root / "batches" / ("a" * 16 + ".tsq")).unlink()

        problems = verify.verify(root, openssl="openssl")

        assert any("missing request/token file" in problem for problem in problems)

    def test_openssl_failure_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        monkeypatch.setattr(
            verify.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="bad signature"),
        )

        problems = verify.verify(root, openssl="openssl")

        assert any("timestamp verification failed" in problem for problem in problems)

    def test_batch_count_mismatch_reported(self, tmp_path, monkeypatch):
        root = _build(tmp_path)
        _ok_openssl(monkeypatch)
        manifest = json.loads((root / "ANCHOR_MANIFEST.json").read_text(encoding="utf-8"))
        manifest["batches"] = []
        (root / "ANCHOR_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")

        problems = verify.verify(root, openssl="openssl")

        assert any("batch count mismatch" in problem for problem in problems)
