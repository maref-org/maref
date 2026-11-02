"""RFC 3161 发布产物时间戳脚本回归测试.

回归点: 外部锚是发布前置条件，链路任一环失败都必须非零退出；
CA 指纹必须固定校验，防止根证书与令牌被同时替换。
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import rfc3161_stamp as stamp  # noqa: E402


def _artifact(tmp_path: Path, name: str = "maref-0.0.0.whl", content: bytes = b"wheel") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _fake_urlopen(payload: bytes, content_type: str = "application/timestamp-reply"):
    class _Response:
        def __init__(self) -> None:
            self.headers = {"Content-Type": content_type}

        def read(self) -> bytes:
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=None):  # noqa: ARG001
        return _Response()

    return opener


class TestManifest:
    def test_manifest_lists_sorted_sha256(self, tmp_path):
        first = _artifact(tmp_path, "b.whl", b"b")
        second = _artifact(tmp_path, "a.tar.gz", b"a")

        manifest = stamp.write_manifest([first, second], tmp_path)

        lines = manifest.read_text(encoding="utf-8").splitlines()
        assert lines == [
            f"{hashlib.sha256(b'a').hexdigest()}  a.tar.gz",
            f"{hashlib.sha256(b'b').hexdigest()}  b.whl",
        ]

    def test_generated_files_are_excluded_on_rerun(self, tmp_path):
        artifact = _artifact(tmp_path)
        (tmp_path / stamp.MANIFEST_NAME).write_text("", encoding="utf-8")
        (tmp_path / "freetsa-cacert.pem").write_text("", encoding="utf-8")

        selected = stamp.collect_artifacts(
            [artifact, tmp_path / stamp.MANIFEST_NAME, tmp_path / "freetsa-cacert.pem"],
            tmp_path,
        )

        assert selected == [artifact]

    def test_missing_artifact_fails(self, tmp_path):
        with pytest.raises(stamp.TimestampError):
            stamp.collect_artifacts([tmp_path / "missing.whl"], tmp_path)

    def test_empty_selection_fails(self, tmp_path):
        (tmp_path / stamp.MANIFEST_NAME).write_text("", encoding="utf-8")
        with pytest.raises(stamp.TimestampError):
            stamp.collect_artifacts([tmp_path / stamp.MANIFEST_NAME], tmp_path)


class TestPinnedCA:
    def test_matching_fingerprint_accepted(self, tmp_path, monkeypatch):
        payload = b"root-ca"
        monkeypatch.setattr(
            stamp.urllib.request, "urlopen", _fake_urlopen(payload, "application/x-pem-file")
        )
        out = tmp_path / "ca.pem"

        stamp.fetch_ca(
            "https://example.invalid/ca.pem", hashlib.sha256(payload).hexdigest(), out, 5
        )

        assert out.read_bytes() == payload

    def test_fingerprint_mismatch_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            stamp.urllib.request, "urlopen", _fake_urlopen(b"other-ca", "application/x-pem-file")
        )
        with pytest.raises(stamp.TimestampError, match="fingerprint mismatch"):
            stamp.fetch_ca("https://example.invalid/ca.pem", "0" * 64, tmp_path / "ca.pem", 5)


class TestTSAResponse:
    def test_empty_token_rejected(self, tmp_path, monkeypatch):
        tsq = tmp_path / "req.tsq"
        tsq.write_bytes(b"request")
        monkeypatch.setattr(
            stamp.urllib.request, "urlopen", _fake_urlopen(b"", "application/timestamp-reply")
        )
        with pytest.raises(stamp.TimestampError, match="empty token"):
            stamp.request_token(tsq, tmp_path / "resp.tsr", "https://tsa.invalid", 5)

    def test_wrong_content_type_rejected(self, tmp_path, monkeypatch):
        tsq = tmp_path / "req.tsq"
        tsq.write_bytes(b"request")
        monkeypatch.setattr(stamp.urllib.request, "urlopen", _fake_urlopen(b"token", "text/html"))
        with pytest.raises(stamp.TimestampError, match="unexpected TSA response"):
            stamp.request_token(tsq, tmp_path / "resp.tsr", "https://tsa.invalid", 5)


@pytest.mark.skipif(
    os.environ.get("MAREF_TSA_LIVE") != "1",
    reason="live TSA test; set MAREF_TSA_LIVE=1 to run",
)
def test_live_free_tsa_round_trip(tmp_path):
    artifact = _artifact(tmp_path)
    assert stamp.main(["--files", str(artifact), "--out-dir", str(tmp_path)]) == 0
    assert (tmp_path / stamp.MANIFEST_NAME).exists()
    assert (tmp_path / f"{stamp.MANIFEST_NAME}.tsr").stat().st_size > 0
    assert (tmp_path / "freetsa-cacert.pem").exists()
