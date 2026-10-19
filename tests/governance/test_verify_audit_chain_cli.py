from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from maref.governance.audit import AuditLogger

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "verify_audit_chain.py"


def _run_cli(path: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("MAREF_HMAC_SECRET_KEY", None)
    env.pop("MAREF_ED25519_PRIVATE_KEY", None)
    # isolate from a developer's ~/.maraf_hmac_key
    env["HOME"] = str(cwd)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--audit-file", str(path), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_signed_log(path: Path) -> None:
    logger = AuditLogger(path, hmac_key="test-key")
    logger.log("cli", "actor", "action")


def test_cli_exits_zero_when_signature_is_verified(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _write_signed_log(path)

    result = _run_cli(path, "--hmac-key", "test-key", cwd=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "authenticity verified: True" in result.stdout


def test_cli_fails_when_key_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _write_signed_log(path)

    result = _run_cli(path, cwd=tmp_path)

    assert result.returncode == 1
    assert "UNVERIFIED" in result.stdout
    assert "key status: missing" in result.stdout


def test_cli_allow_unverified_only_bypasses_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _write_signed_log(path)

    result = _run_cli(path, "--allow-unverified", cwd=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "unverified signatures allowed" in result.stdout


def test_cli_fails_when_key_is_wrong(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _write_signed_log(path)

    result = _run_cli(path, "--hmac-key", "wrong-key", cwd=tmp_path)

    assert result.returncode == 1
    assert "key status: rotated_or_wrong" in result.stdout


def test_cli_allow_unverified_does_not_bypass_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _write_signed_log(path)
    record = json.loads(path.read_text(encoding="utf-8").strip())
    record["details"] = "tampered"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = _run_cli(path, "--allow-unverified", cwd=tmp_path)

    assert result.returncode == 1
    assert "FAILED" in result.stdout
